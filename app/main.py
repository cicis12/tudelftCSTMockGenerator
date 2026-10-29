import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.concurrency import run_in_threadpool

from .config import ROOT, settings
from .accounts import current_learner, guest_owner, password_hash, profile_key, rate_limit, sign_in, sign_out, verify_password
from .database import Base, SessionLocal, engine, get_db
from .exams import add_practice_item, advance, all_items, enforce_deadline, finish, serialize_attempt, start_attempt
from .generation import generate_questions
from .models import Attempt, Generation, Item, Learner, Question
from .progress import progress_summary, record_results
from .question_archives import MAX_ZIP_BYTES, export_questions, import_questions
from .schemas import AnswerInput, DURATIONS, GenerateInput, LearnerCredentials, LoginInput, MAX_GENERATED_QUESTIONS, QuestionInput, StartInput, TOPICS, fingerprint
from .seed import seed_database

# SQLite is a local development fallback; PostgreSQL is the deployment default.
# Row locks protect deployed attempts. The lock also serializes SQLite writes in this single-worker app.
write_lock = threading.RLock()
login_failures = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    if len(settings.secret_key) < 32 or len(settings.admin_password) < 12:
        raise RuntimeError('Set SECRET_KEY (at least 32 characters) and ADMIN_PASSWORD (at least 12 characters). Run ./deploy.sh or follow README.md.')
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_database(db)
        db.execute(update(Generation).where(Generation.status == 'running').values(status='failed', message='Server restarted during generation. Please retry.'))
        db.commit()
    yield


app = FastAPI(title='CST Studio', lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key or secrets.token_hex(32),
                   same_site='strict', https_only=settings.cookie_secure, max_age=60*60*24*30)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # FastAPI's default errors can echo input, including passwords and API keys.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(error['loc']), 'msg': error['msg'], 'type': error['type']}
        for error in exc.errors()
    ]})


@app.middleware('http')
async def security(request: Request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if request.headers.get('x-cst-request') != '1':
            return JSONResponse({'detail': 'Missing request protection header.'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and urlparse(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail': 'Cross-origin requests are not accepted.'}, status_code=403)
        try:
            content_length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail': 'Invalid content length.'}, status_code=400)
        limit = MAX_ZIP_BYTES if request.url.path == '/api/admin/questions/import' else 100_000
        if content_length > limit:
            return JSONResponse({'detail': 'Request too large.'}, status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def owner(request, db):
    current_learner(db, request)
    return guest_owner(request)


def sync_browser_progress(db, request):
    for attempt in db.scalars(select(Attempt).where(Attempt.owner == owner(request, db))):
        enforce_deadline(db, attempt)
        record_results(db, attempt)


def learner_state(db, request):
    learner = current_learner(db, request)
    return {'account': {'username': learner.username} if learner else None,
            'progress': progress_summary(db, profile_key(db, request))}


@app.get('/api/account')
def account_state(request: Request, db: Session = Depends(get_db)):
    with write_lock:
        sync_browser_progress(db, request)
        result = learner_state(db, request)
        db.commit()
        return result


@app.post('/api/account/{action}')
def authenticate(action: Literal['register', 'login'], data: LearnerCredentials, request: Request, db: Session = Depends(get_db)):
    with write_lock:
        rate_limit(request)
        if current_learner(db, request):
            raise HTTPException(409, 'Sign out before switching accounts.')
        username = data.username.lower()
        learner = db.scalar(select(Learner).where(Learner.username == username))
        if action == 'register':
            if learner:
                raise HTTPException(409, 'That username is already taken. Choose another or sign in.')
            learner = Learner(username=username, password_hash=password_hash(data.password))
            db.add(learner)
            db.flush()
        elif not learner:
            password_hash(data.password)  # Keep unknown-user and wrong-password work comparable.
            raise HTTPException(401, 'Incorrect username or password.')
        elif not verify_password(data.password, learner.password_hash):
            raise HTTPException(401, 'Incorrect username or password.')
        sync_browser_progress(db, request)
        sign_in(db, request, learner)
        return learner_state(db, request)


@app.delete('/api/account/session')
def logout_learner(request: Request, db: Session = Depends(get_db)):
    with write_lock:
        sync_browser_progress(db, request)
        sign_out(db, request)
        return learner_state(db, request)


def admin(request: Request):
    if not request.session.get('admin_until', 0) > time.time():
        raise HTTPException(401, 'Please sign in to the admin panel.')


def get_attempt(db, request, attempt_id):
    attempt = db.scalar(select(Attempt).where(Attempt.id == attempt_id, Attempt.owner == owner(request, db)).with_for_update())
    if not attempt:
        raise HTTPException(404, 'Practice session not found in this browser.')
    enforce_deadline(db, attempt)
    record_results(db, attempt)
    return attempt


@app.get('/health')
def health(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok'}


@app.get('/api/config')
def config(request: Request, db: Session = Depends(get_db)):
    with write_lock:
        sync_browser_progress(db, request)
        learner = learner_state(db, request)
        counts = dict(db.execute(select(Question.section, func.count()).where(Question.status == 'published').group_by(Question.section)).all())
        active = db.scalar(select(Attempt).where(Attempt.owner == request.session['owner'], Attempt.status == 'active').order_by(Attempt.created_at.desc()).limit(1))
        db.commit()
        return {'counts': counts, 'topics': TOPICS, 'durations': DURATIONS, **learner,
                'question_counts': {s: min(max(1, getattr(settings, f'{s}_question_count')), learner['progress']['sections'][s]['available']) for s in TOPICS},
                'active_attempt': active.id if active else None}


@app.post('/api/attempts')
def create_attempt(data: StartInput, request: Request, db: Session = Depends(get_db)):
    if not data.accepted_rules:
        raise HTTPException(422, 'Read and accept the rules before starting.')
    with write_lock:
        # A new session explicitly replaces this browser's active session.
        sync_browser_progress(db, request)
        for old in db.scalars(select(Attempt).where(Attempt.owner == owner(request, db), Attempt.status == 'active')):
            finish(db, old)
        attempt = start_attempt(db, request.session['owner'], data, profile_key(db, request))
        return serialize_attempt(db, attempt)


@app.get('/api/attempts/{attempt_id}')
def read_attempt(attempt_id: str, request: Request, db: Session = Depends(get_db)):
    with write_lock:
        attempt = get_attempt(db, request, attempt_id)
        result = serialize_attempt(db, attempt)
        db.commit()
        return result


@app.put('/api/attempts/{attempt_id}/items/{item_id}')
def answer(attempt_id: str, item_id: int, data: AnswerInput, request: Request, db: Session = Depends(get_db)):
    with write_lock:
        attempt = get_attempt(db, request, attempt_id)
        item = db.get(Item, item_id)
        if not item or item.attempt_id != attempt.id:
            raise HTTPException(404, 'Question not found.')
        if attempt.status != 'active' or item.section != attempt.sections[attempt.active_section] or (attempt.mode == 'infinite' and item.block != attempt.block):
            db.commit()
            raise HTTPException(409, 'This section has ended. Your earlier saved answers are safe.')
        if attempt.mode == 'infinite' and item.submitted:
            raise HTTPException(409, 'This answer has already been submitted.')
        item.answer, item.flagged = data.answer, data.flagged
        if attempt.mode == 'infinite':
            if data.answer is None:
                raise HTTPException(422, 'Select an answer first.')
            item.submitted = True
            record_results(db, attempt)
        db.commit()
        return serialize_attempt(db, attempt)


@app.post('/api/attempts/{attempt_id}/next')
def next_question(attempt_id: str, request: Request, db: Session = Depends(get_db)):
    with write_lock:
        attempt = get_attempt(db, request, attempt_id)
        if attempt.status == 'active' and attempt.mode == 'infinite':
            current = all_items(db, attempt)[-1]
            if current.submitted:
                add_practice_item(db, attempt)
        else:
            raise HTTPException(409, 'This action is only available in active infinite practice.')
        result = serialize_attempt(db, attempt)
        db.commit()
        return result


@app.post('/api/attempts/{attempt_id}/section')
def finish_section(attempt_id: str, request: Request, section: Literal['math', 'logic'], db: Session = Depends(get_db)):
    with write_lock:
        attempt = get_attempt(db, request, attempt_id)
        # Expected section makes retries harmless and prevents submitting the next section after expiry.
        if attempt.status == 'active' and attempt.mode == 'timed' and attempt.sections[attempt.active_section] == section:
            advance(db, attempt, time.time())
        result = serialize_attempt(db, attempt)
        db.commit()
        return result


@app.post('/api/attempts/{attempt_id}/finish')
def finish_attempt(attempt_id: str, request: Request, db: Session = Depends(get_db)):
    with write_lock:
        attempt = get_attempt(db, request, attempt_id)
        if attempt.status == 'active':
            finish(db, attempt)
        result = serialize_attempt(db, attempt)
        db.commit()
        return result


@app.get('/api/history')
def history(request: Request, db: Session = Depends(get_db)):
    attempts = db.scalars(select(Attempt).where(Attempt.owner == owner(request, db), Attempt.status == 'finished').order_by(Attempt.created_at.desc()).limit(20)).all()
    return [{'id': a.id, 'mode': a.mode, 'sections': a.sections, 'created_at': a.created_at} for a in attempts]


@app.post('/api/admin/login')
def login(data: LoginInput, request: Request):
    address = request.client.host if request.client else 'unknown'
    with write_lock:
        failures = login_failures[address]
        now = time.time()
        while failures and failures[0] < now - 600:
            failures.popleft()
        if len(failures) >= 8:
            raise HTTPException(429, 'Too many attempts. Try again in ten minutes.')
        if not secrets.compare_digest(data.password.encode(), settings.admin_password.encode()):
            failures.append(now)
            raise HTTPException(401, 'Incorrect admin password.')
        failures.clear()
    request.session['admin_until'] = time.time() + 8*3600
    return {'ok': True}


@app.post('/api/admin/logout')
def logout(request: Request):
    request.session.pop('admin_until', None)
    return {'ok': True}


@app.get('/api/admin/status', dependencies=[Depends(admin)])
def admin_status(db: Session = Depends(get_db)):
    counts = db.execute(select(Question.section, Question.status, func.count()).group_by(Question.section, Question.status)).all()
    return {'counts': [{'section': s, 'status': st, 'count': n} for s, st, n in counts],
            'has_key': bool(settings.openai_api_key), 'model': settings.openai_model, 'topics': TOPICS,
            'generation_limit': MAX_GENERATED_QUESTIONS}


@app.get('/api/admin/questions', dependencies=[Depends(admin)])
def questions(status: Literal['draft', 'published', 'rejected'] = 'draft', section: Literal['math', 'logic', 'all'] = 'all', db: Session = Depends(get_db)):
    query = select(Question).where(Question.status == status)
    if section != 'all':
        query = query.where(Question.section == section)
    return [{'id': q.id, 'status': q.status, 'origin': q.origin, **{k: getattr(q, k) for k in QuestionInput.model_fields}}
            for q in db.scalars(query.order_by(Question.id.desc()).limit(500))]


@app.get('/api/admin/questions/export', dependencies=[Depends(admin)])
def export_question_bank(db: Session = Depends(get_db)):
    return Response(export_questions(db), media_type='application/zip', headers={
        'Content-Disposition': 'attachment; filename="cst-studio-questions.zip"',
    })


def import_question_bank(payload):
    with write_lock, SessionLocal() as db:
        return import_questions(db, payload)


@app.post('/api/admin/questions/import', dependencies=[Depends(admin)])
async def upload_question_bank(request: Request):
    if request.headers.get('content-type', '').split(';', 1)[0].lower() not in ('application/zip', 'application/octet-stream'):
        raise HTTPException(415, 'Upload the ZIP file as application/zip.')
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > MAX_ZIP_BYTES:
            raise HTTPException(413, 'ZIP files must be no larger than 10 MiB.')
        payload.extend(chunk)
    return await run_in_threadpool(import_question_bank, bytes(payload))


@app.post('/api/admin/questions/approve-all', dependencies=[Depends(admin)])
def approve_all_questions(section: Literal['math', 'logic', 'all'] = 'all', db: Session = Depends(get_db)):
    with write_lock:
        query = select(Question).where(Question.status == 'draft')
        if section != 'all':
            query = query.where(Question.section == section)
        drafts = db.scalars(query.with_for_update()).all()
        # Validate the complete selection before changing any publication status.
        try:
            for q in drafts:
                QuestionInput(**{k: getattr(q, k) for k in QuestionInput.model_fields})
        except ValueError:
            raise HTTPException(422, 'A draft failed validation. Edit or reject invalid drafts before approving all.')
        for q in drafts:
            q.status = 'published'
        db.commit()
        return {'approved': len(drafts)}


@app.put('/api/admin/questions/{question_id}', dependencies=[Depends(admin)])
def edit_question(question_id: int, data: QuestionInput, db: Session = Depends(get_db)):
    with write_lock:
        q = db.get(Question, question_id)
        if not q:
            raise HTTPException(404, 'Question not found.')
        fp = fingerprint(data.prompt)
        if db.scalar(select(Question.id).where(Question.fingerprint == fp, Question.id != question_id)):
            raise HTTPException(409, 'A question with this prompt already exists.')
        for k, v in data.model_dump().items():
            setattr(q, k, v)
        q.fingerprint, q.status = fp, 'draft'
        db.commit()
        return {'ok': True}


@app.post('/api/admin/questions/{question_id}/{action}', dependencies=[Depends(admin)])
def publish_question(question_id: int, action: Literal['publish', 'reject'], db: Session = Depends(get_db)):
    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(404, 'Question not found.')
    QuestionInput(**{k: getattr(q, k) for k in QuestionInput.model_fields})
    q.status = 'published' if action == 'publish' else 'rejected'
    db.commit()
    return {'ok': True}


@app.post('/api/admin/generate', dependencies=[Depends(admin)], status_code=202)
def generate(data: GenerateInput, background: BackgroundTasks, db: Session = Depends(get_db)):
    key = data.api_key.strip() or settings.openai_api_key
    if not key:
        raise HTTPException(422, 'Enter an OpenAI API key or configure OPENAI_API_KEY on the server.')
    with write_lock:
        if db.scalar(select(Generation).where(Generation.status == 'running')):
            raise HTTPException(409, 'A generation is already running. Wait for it to finish.')
        job = Generation(section=data.section, model=data.model, count=data.count)
        db.add(job)
        db.commit()
        background.add_task(generate_questions, job.id, data.model_copy(update={'api_key': ''}), key)
    return {'id': job.id, 'status': job.status}


@app.get('/api/admin/generations', dependencies=[Depends(admin)])
def generations(db: Session = Depends(get_db)):
    return [{'id': j.id, 'section': j.section, 'status': j.status, 'message': j.message, 'created_at': j.created_at}
            for j in db.scalars(select(Generation).order_by(Generation.created_at.desc()).limit(10))]


@app.get('/api/admin/context/{section}', dependencies=[Depends(admin)])
def generation_context(section: Literal['math', 'logic']):
    return {'system': (ROOT / 'context/generation-system.md').read_text(),
            'context': (ROOT / 'context' / f'{section}.md').read_text()}


@app.get('/')
@app.get('/admin')
def index():
    return FileResponse(ROOT / 'app/static/index.html')


@app.get('/formula-sheet.pdf')
def formulas():
    return FileResponse(ROOT / 'sources/formulas.pdf', media_type='application/pdf')


app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')
