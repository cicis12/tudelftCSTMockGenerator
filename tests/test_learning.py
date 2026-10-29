import time

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Attempt, AttemptProfile, Item, Learner, LearnerSession, Question, QuestionResult

PASSWORD = 'a-long-test-password'


def start(client, section='math', mode='infinite'):
    result = client.post('/api/attempts', json={'section':section,'mode':mode,'accepted_rules':True})
    assert result.status_code == 200, result.text
    return result.json()


def submit(client, attempt, correct=True):
    item = attempt['items'][-1]
    with SessionLocal() as db:
        record = db.get(Item, item['id'])
        answer = record.snapshot['correct_index']
        qid = record.question_id
    if not correct:
        answer = (answer + 1) % 4
    result = client.put(f"/api/attempts/{attempt['id']}/items/{item['id']}", json={'answer':answer})
    assert result.status_code == 200, result.text
    return qid, result.json()


def sign_up(client, username='learner_one'):
    result = client.post('/api/account/register', json={'username':username,'password':PASSWORD})
    assert result.status_code == 200, result.text
    return result.json()


def keep_one_per_section():
    with SessionLocal() as db:
        for section in ['math','logic']:
            rows = db.scalars(select(Question).where(Question.section==section).order_by(Question.id)).all()
            for q in rows[1:]:
                q.status='draft'
        db.commit()


def test_guest_correct_answers_rest_across_modes_and_refreshes(client):
    attempt = start(client)
    qid, answered = submit(client, attempt)
    prompt = answered['items'][0]['prompt']
    state = client.get('/api/account').json()
    assert state['account'] is None
    assert state['progress']['answered'] == state['progress']['correct_answers'] == 1
    assert state['progress']['sections']['math']['resting'] == 1
    with SessionLocal() as db:
        timestamp = db.get(QuestionResult, attempt['items'][0]['id']).recorded_at
    for _ in range(3):
        client.get('/api/account')
        client.get(f"/api/attempts/{attempt['id']}")
    with SessionLocal() as db:
        assert db.get(QuestionResult, attempt['items'][0]['id']).recorded_at == timestamp
    mock = start(client, mode='timed')
    assert prompt not in {i['prompt'] for i in mock['items']}
    with SessionLocal() as db:
        assert qid not in set(db.scalars(select(Item.question_id).where(Item.attempt_id==mock['id'])))


def test_timed_answers_not_leaked_and_only_final_choice_recorded(client):
    attempt = start(client, 'both', 'timed')
    submit(client, attempt)
    assert client.get('/api/account').json()['progress']['answered'] == 0
    submit(client, attempt, correct=False)
    logic = client.post(f"/api/attempts/{attempt['id']}/section?section=math").json()
    assert logic['section'] == 'logic'
    assert client.get('/api/account').json()['progress']['answered'] == 0
    submit(client, logic)
    finished = client.post(f"/api/attempts/{attempt['id']}/finish").json()
    assert finished['progress']['answered'] == 2
    assert finished['progress']['correct_answers'] == 1
    assert finished['progress']['sections']['math']['resting'] == 0
    assert finished['progress']['sections']['logic']['resting'] == 1


def test_cooldown_exhaustion_never_repeats_early_and_expiry_restores(client):
    keep_one_per_section()
    attempt = start(client)
    submit(client, attempt)
    finished = client.post(f"/api/attempts/{attempt['id']}/next").json()
    assert finished['status'] == 'finished' and len(finished['items']) == 1
    assert client.get('/api/config').json()['question_counts']['math'] == 0
    result = client.post('/api/attempts', json={'section':'math','mode':'timed','accepted_rules':True})
    assert result.status_code == 409 and 'resting' in result.json()['detail']
    with SessionLocal() as db:
        row = db.get(QuestionResult, attempt['items'][0]['id'])
        row.recorded_at = time.time() - settings.correct_answer_cooldown_days * 86400 - 1
        db.commit()
    assert client.get('/api/config').json()['question_counts']['math'] == 1
    assert start(client)['items'][0]['prompt'] == attempt['items'][0]['prompt']


def test_combined_infinite_moves_to_other_eligible_section(client):
    keep_one_per_section()
    attempt = start(client, 'both')
    submit(client, attempt)
    logic = client.post(f"/api/attempts/{attempt['id']}/next").json()
    assert logic['status'] == 'active' and logic['section'] == 'logic'
    submit(client, logic)
    finished = client.post(f"/api/attempts/{attempt['id']}/next").json()
    assert finished['status'] == 'finished' and len(finished['items']) == 2


def test_incorrect_questions_remain_eligible(client):
    keep_one_per_section()
    attempt = start(client)
    submit(client, attempt, correct=False)
    next_attempt = client.post(f"/api/attempts/{attempt['id']}/next").json()
    assert next_attempt['items'][-1]['prompt'] == attempt['items'][0]['prompt']
    state = client.get('/api/account').json()
    assert state['progress']['answered'] == 1
    assert state['progress']['sections']['math']['resting'] == 0


def test_guest_merge_cross_device_sync_and_attempt_privacy(client):
    attempt = start(client)
    qid, answered = submit(client, attempt)
    joined = sign_up(client, 'Learner_One')
    assert joined['account']['username'] == 'learner_one'
    assert joined['progress']['correct_questions'] == 1
    with SessionLocal() as db:
        learner = db.scalar(select(Learner))
        assert learner.password_hash.startswith('scrypt$') and PASSWORD not in learner.password_hash
        assert db.get(AttemptProfile, attempt['id']).profile == f'user:{learner.id}'
        assert db.scalar(select(LearnerSession)).token_hash
    with TestClient(app, headers={'X-CST-Request':'1'}) as second:
        assert second.get('/api/account').json()['progress']['answered'] == 0
        signed = second.post('/api/account/login', json={'username':'LEARNER_ONE','password':PASSWORD})
        assert signed.status_code == 200
        assert signed.json()['progress']['correct_questions'] == 1
        assert second.get(f"/api/attempts/{attempt['id']}").status_code == 404
        new = start(second, mode='timed')
        assert answered['items'][0]['prompt'] not in {i['prompt'] for i in new['items']}
        assert second.get('/api/history').json() == []
    assert client.get('/api/account').json()['progress']['answered'] == 1


def test_logout_revokes_token_and_isolates_new_guest(client):
    sign_up(client)
    attempt = start(client)
    submit(client, attempt)
    old_cookie = client.cookies.get('session')
    out = client.delete('/api/account/session')
    assert out.json()['account'] is None and out.json()['progress']['answered'] == 0
    assert client.get(f"/api/attempts/{attempt['id']}").status_code == 404
    with TestClient(app, headers={'X-CST-Request':'1'}) as stolen:
        stolen.cookies.set('session', old_cookie)
        assert stolen.get('/api/account').json()['account'] is None
        assert stolen.get(f"/api/attempts/{attempt['id']}").status_code == 404
    signed = client.post('/api/account/login', json={'username':'learner_one','password':PASSWORD})
    assert signed.json()['progress']['correct_questions'] == 1
    assert client.get('/api/admin/status').status_code == 401


def test_expired_sessions_cannot_access_old_history(client):
    sign_up(client)
    attempt = start(client)
    submit(client, attempt)
    with SessionLocal() as db:
        for session in db.scalars(select(LearnerSession)):
            session.expires_at = time.time() - 1
        db.commit()
    assert client.get('/api/account').json()['account'] is None
    assert client.get('/api/account').json()['progress']['answered'] == 0
    assert client.get(f"/api/attempts/{attempt['id']}").status_code == 404


def test_login_validation_and_rate_limit(client):
    assert client.post('/api/account/register', json={'username':'valid','password':'short'}).status_code == 422
    assert client.post('/api/account/register', json={'username':'../bad','password':PASSWORD}).status_code == 422
    sign_up(client)
    assert client.post('/api/account/register', json={'username':'someone_else','password':PASSWORD}).status_code == 409
    client.delete('/api/account/session')
    assert client.post('/api/account/register', json={'username':'LEARNER_ONE','password':PASSWORD}).status_code == 409
    wrong = client.post('/api/account/login', json={'username':'learner_one','password':'wrong-but-long-password'})
    unknown = client.post('/api/account/login', json={'username':'nobody','password':PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    for _ in range(15):
        response = client.post('/api/account/login', json={'username':'nobody','password':PASSWORD})
    assert response.status_code == 429


def test_old_completed_attempts_are_backfilled_without_duplicates(client):
    attempt = start(client, mode='timed')
    submit(client, attempt)
    client.post(f"/api/attempts/{attempt['id']}/finish")
    with SessionLocal() as db:
        db.execute(delete(QuestionResult))
        db.execute(delete(AttemptProfile))
        db.commit()
    for _ in range(2):
        state = client.get('/api/account').json()
        assert state['progress']['answered'] == 1
        assert state['progress']['sections']['math']['resting'] == 1


def test_late_timed_expiry_uses_actual_deadline(client):
    attempt = start(client, mode='timed')
    submit(client, attempt)
    with SessionLocal() as db:
        db.get(Attempt, attempt['id']).deadline = time.time() - 8*86400
        db.commit()
    state = client.get('/api/account').json()
    assert state['progress']['correct_questions'] == 1
    assert state['progress']['sections']['math']['resting'] == 0


def test_question_zip_contains_no_account_or_progress_records(client):
    sign_up(client)
    attempt = start(client)
    submit(client, attempt)
    client.post('/api/admin/login', json={'password':'test-admin-password'})
    import io, zipfile
    exported = client.get('/api/admin/questions/export')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        content = archive.read('questions.json').decode()
    assert 'learner_one' not in content and 'scrypt$' not in content and PASSWORD not in content


def test_existing_account_merges_another_guest_without_double_counting(client):
    sign_up(client)
    attempt = start(client)
    submit(client, attempt)
    with TestClient(app, headers={'X-CST-Request':'1'}) as second:
        guest = start(second, 'logic')
        submit(second, guest)
        login = second.post('/api/account/login', json={'username':'learner_one','password':PASSWORD})
        assert login.status_code == 200
        assert login.json()['progress']['answered'] == 2
        second.delete('/api/account/session')
        again = second.post('/api/account/login', json={'username':'learner_one','password':PASSWORD})
        assert again.json()['progress']['answered'] == 2
        second.delete('/api/account/session')
        other = sign_up(second, 'another_person')
        assert other['progress']['answered'] == 0
    assert client.get('/api/account').json()['progress']['answered'] == 2


def test_startup_adds_learning_tables_to_existing_database(client):
    attempt = start(client, mode='timed')
    submit(client, attempt)
    client.post(f"/api/attempts/{attempt['id']}/finish")
    from app.database import engine
    # Simulate the previous release: question/attempt data exists, learning tables do not.
    for model in [QuestionResult, AttemptProfile, LearnerSession, Learner]:
        model.__table__.drop(engine)
    with TestClient(app, headers={'X-CST-Request':'1'}) as restarted:
        restarted.cookies.update(client.cookies)
        state = restarted.get('/api/account').json()
        assert state['progress']['answered'] == 1
        assert state['progress']['correct_questions'] == 1
        assert restarted.get(f"/api/attempts/{attempt['id']}").status_code == 200
