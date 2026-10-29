import hashlib
import secrets
import time
from collections import defaultdict, deque

from fastapi import HTTPException
from sqlalchemy import delete, select, update

from .models import AttemptProfile, Learner, LearnerSession, QuestionResult

auth_attempts = defaultdict(deque)
SESSION_SECONDS = 30 * 86400


def password_hash(password, salt=None):
    # OWASP scrypt profile: N=2^15, r=8, p=3 (32 MiB), with a unique random salt.
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**15, r=8, p=3, maxmem=64*1024*1024).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, encoded):
    return secrets.compare_digest(password_hash(password, encoded.split('$')[1]), encoded)


def guest_owner(request):
    if 'owner' not in request.session:
        request.session['owner'] = secrets.token_hex(24)
    return request.session['owner']


def current_learner(db, request):
    if hasattr(request.state, 'learner'):
        return request.state.learner
    token = request.session.get('learner_token')
    learner = None
    if token:
        session = db.get(LearnerSession, hashlib.sha256(token.encode()).hexdigest())
        if session and session.expires_at > time.time():
            learner = db.get(Learner, session.learner_id)
        if not learner:
            request.session.pop('learner_token', None)
            request.session['owner'] = secrets.token_hex(24)
    request.state.learner = learner
    return learner


def profile_key(db, request):
    learner = current_learner(db, request)
    return f'user:{learner.id}' if learner else f'guest:{guest_owner(request)}'


def rate_limit(request):
    address = request.client.host if request.client else 'unknown'
    attempts = auth_attempts[address]
    now = time.time()
    while attempts and attempts[0] <= now - 600:
        attempts.popleft()
    if len(attempts) >= 15:
        raise HTTPException(429, 'Too many sign-in attempts. Try again in ten minutes.')
    attempts.append(now)


def sign_in(db, request, learner):
    guest = f'guest:{guest_owner(request)}'
    profile = f'user:{learner.id}'
    # Move guest events, rather than copy them, so repeated logins never double-count.
    db.execute(update(QuestionResult).where(QuestionResult.profile == guest).values(profile=profile))
    db.execute(update(AttemptProfile).where(AttemptProfile.profile == guest).values(profile=profile))
    token = secrets.token_urlsafe(32)
    db.execute(delete(LearnerSession).where(LearnerSession.expires_at <= time.time()))
    db.add(LearnerSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), learner_id=learner.id,
                         expires_at=time.time() + SESSION_SECONDS))
    db.commit()
    request.session['learner_token'] = token
    request.state.learner = learner


def sign_out(db, request):
    token = request.session.pop('learner_token', None)
    if token:
        db.execute(delete(LearnerSession).where(LearnerSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        db.commit()
    # A shared browser must not expose the previous learner's history or attach it to another account.
    request.session['owner'] = secrets.token_hex(24)
    request.state.learner = None
