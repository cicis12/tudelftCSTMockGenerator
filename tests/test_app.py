import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import generation
from app.database import SessionLocal
from app.main import app
from app.models import Attempt, Generation, Item, Question
from app.schemas import QuestionBatch, QuestionInput, TOPICS
from app.seed import seed_questions


def start(client, section='math', mode='timed'):
    response = client.post('/api/attempts', json={'section': section, 'mode': mode, 'accepted_rules': True})
    assert response.status_code == 200, response.text
    return response.json()


def correct_for(item_id):
    with SessionLocal() as db:
        return db.get(Item, item_id).snapshot['correct_index']


def expire(attempt_id, seconds=1):
    with SessionLocal() as db:
        db.get(Attempt, attempt_id).deadline = time.time() - seconds
        db.commit()


def test_seed_covers_syllabus_and_no_duplicates(client):
    rows = seed_questions()
    assert len(rows) == 90
    assert len({q.prompt for q in rows}) == 90
    for section, topics in TOPICS.items():
        assert {q.topic for q in rows if q.section == section} == set(topics)
    with SessionLocal() as db:
        assert len(db.scalars(select(Question)).all()) == 90
    assert client.get('/formula-sheet.pdf').headers['content-type'] == 'application/pdf'


def test_rules_must_be_accepted(client):
    assert client.post('/api/attempts', json={'section': 'math', 'mode': 'timed', 'accepted_rules': False}).status_code == 422


def test_timed_answers_hidden_saved_and_reviewed(client):
    a = start(client)
    assert len(a['items']) == 24
    assert {i['topic'] for i in a['items']} == set(TOPICS['math'])
    q = a['items'][0]
    assert 'correct_index' not in q and 'explanation' not in q
    correct = correct_for(q['id'])
    response = client.put(f"/api/attempts/{a['id']}/items/{q['id']}", json={'answer': correct, 'flagged': True})
    assert response.status_code == 200
    assert 'correct_index' not in response.json()['items'][0]
    refreshed = client.get(f"/api/attempts/{a['id']}").json()
    assert refreshed['deadline'] == a['deadline']
    assert refreshed['items'][0]['answer'] == correct
    assert refreshed['items'][0]['flagged']
    result = client.post(f"/api/attempts/{a['id']}/finish").json()
    assert result['scores']['math'] == {'correct': 1, 'total': 24}
    assert all('correct_index' in i and 'explanation' in i for i in result['items'])
    assert client.put(f"/api/attempts/{a['id']}/items/{q['id']}", json={'answer': 0}).status_code == 409


def test_sections_are_sequential_and_late_answers_rejected(client):
    a = start(client, 'both')
    old = a['items'][0]
    expire(a['id'])
    assert client.put(f"/api/attempts/{a['id']}/items/{old['id']}", json={'answer': 0}).status_code == 409
    next_a = client.get(f"/api/attempts/{a['id']}").json()
    assert next_a['section'] == 'logic'
    assert len(next_a['items']) == 20
    assert all(i['section'] == 'logic' and 'correct_index' not in i for i in next_a['items'])
    assert 2690 < next_a['deadline'] - next_a['server_time'] <= 2700
    # A retried math submission must not end logic.
    assert client.post(f"/api/attempts/{a['id']}/section?section=math").json()['status'] == 'active'
    result = client.post(f"/api/attempts/{a['id']}/section?section=logic").json()
    assert result['status'] == 'finished' and len(result['items']) == 44


def test_long_absence_expires_both_sections(client):
    a = start(client, 'both')
    expire(a['id'], 2800)
    result = client.get(f"/api/attempts/{a['id']}").json()
    assert result['status'] == 'finished'
    assert len(result['items']) == 44


def test_infinite_immediate_feedback_and_no_rewrites(client):
    a = start(client, 'logic', 'infinite')
    item = a['items'][0]
    assert 'correct_index' not in item
    url = f"/api/attempts/{a['id']}/items/{item['id']}"
    result = client.put(url, json={'answer': correct_for(item['id'])}).json()
    assert result['items'][0]['correct'] is True
    assert result['items'][0]['explanation']
    assert client.put(url, json={'answer': 0}).status_code == 409
    second = client.post(f"/api/attempts/{a['id']}/next").json()
    assert len(second['items']) == 2
    assert second['items'][-1]['prompt'] != item['prompt']
    assert 'correct_index' not in second['items'][-1]
    # Retry is idempotent while an unanswered question exists.
    assert len(client.post(f"/api/attempts/{a['id']}/next").json()['items']) == 2
    result = client.post(f"/api/attempts/{a['id']}/finish").json()
    assert len(result['items']) == 2
    assert result['scores']['logic'] == {'correct': 1, 'total': 2}


def test_infinite_timeout_switches_sections_and_preserves_review(client):
    a = start(client, 'both', 'infinite')
    expire(a['id'])
    result = client.get(f"/api/attempts/{a['id']}").json()
    assert result['section'] == 'logic' and result['block'] == 1
    assert len(result['items']) == 1
    assert result['scores']['math']['total'] == 1
    result = client.post(f"/api/attempts/{a['id']}/finish").json()
    assert len(result['items']) == 2
    assert result['items'][0]['answer'] is None


def test_infinite_can_continue_after_full_bank(client):
    a = start(client, 'logic', 'infinite')
    seen = set()
    for _ in range(31):
        item = a['items'][-1]
        seen.add(item['prompt'])
        assert client.put(f"/api/attempts/{a['id']}/items/{item['id']}", json={'answer': 0}).status_code == 200
        a = client.post(f"/api/attempts/{a['id']}/next").json()
    assert len(seen) == 29
    assert a['status'] == 'active'


def test_infinite_long_absence_fast_forwards(client):
    a = start(client, 'both', 'infinite')
    expire(a['id'], 365*86400)
    result = client.get(f"/api/attempts/{a['id']}").json()
    assert result['status'] == 'active' and result['deadline'] > time.time()
    assert result['block'] > 1000 and len(result['items']) == 1


def test_sessions_cannot_be_read_by_another_browser(client):
    a = start(client)
    with TestClient(app, headers={'X-CST-Request': '1'}) as stranger:
        assert stranger.get(f"/api/attempts/{a['id']}").status_code == 404
        assert stranger.post(f"/api/attempts/{a['id']}/finish").status_code == 404


def test_csrf_and_admin_protection(client):
    assert client.get('/api/admin/questions').status_code == 401
    assert client.post('/api/admin/login', json={'password':'test-admin-password'}, headers={'Origin':'https://evil.invalid'}).status_code == 403
    with TestClient(app) as unprotected:
        assert unprotected.post('/api/admin/login', json={'password':'test-admin-password'}).status_code == 403
    for _ in range(8):
        assert client.post('/api/admin/login', json={'password':'wrong'}).status_code == 401
    assert client.post('/api/admin/login', json={'password':'test-admin-password'}).status_code == 429


def test_admin_edit_and_publish_preserves_attempt_snapshots(admin_client):
    c = admin_client
    a = start(c)
    item = a['items'][0]
    with SessionLocal() as db:
        qid = db.get(Item, item['id']).question_id
    q = next(q for q in c.get('/api/admin/questions?status=published').json() if q['id'] == qid)
    old_prompt = q['prompt']
    q['prompt'] += ' Choose the single correct answer.'
    assert c.put(f'/api/admin/questions/{qid}', json=q).status_code == 200
    assert any(x['id'] == qid for x in c.get('/api/admin/questions').json())
    assert c.post(f'/api/admin/questions/{qid}/publish').status_code == 200
    refreshed = c.get(f"/api/attempts/{a['id']}").json()
    assert refreshed['items'][0]['prompt'] == old_prompt
    q['options'] = ['a','a','b','c']
    assert c.put(f'/api/admin/questions/{qid}', json=q).status_code == 422


def test_missing_key_and_context(admin_client):
    assert admin_client.post('/api/admin/generate', json={'section':'logic'}).status_code == 422
    ctx = admin_client.get('/api/admin/context/logic').json()
    assert '2.3.4' in ctx['context'] and 'EXCLUDED' in ctx['context']
    assert admin_client.get('/api/admin/context/../../.env').status_code != 200


def test_generation_mocked_and_key_not_stored(admin_client, monkeypatch):
    q = seed_questions()[0].model_copy(update={'prompt':'For the function f(x) = √(x − 12), what is its real domain?'})
    calls = {}
    class FakeOpenAI:
        def __init__(self, **kwargs): calls['key'] = kwargs['api_key']; self.responses=self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def create(self, **kwargs): calls.update(kwargs); return SimpleNamespace(status='completed', output=[], output_text=QuestionBatch(questions=[q]).model_dump_json())
    monkeypatch.setattr(generation, 'OpenAI', FakeOpenAI)
    response = admin_client.post('/api/admin/generate', json={'section':'math','count':1,'api_key':'test-secret-api-key'})
    assert response.status_code == 202
    assert calls['store'] is False
    assert 'Functions and graphs' in calls['input']
    drafts = admin_client.get('/api/admin/questions').json()
    assert len(drafts) == 1 and drafts[0]['status'] == 'draft'
    jobs = admin_client.get('/api/admin/generations').json()
    assert jobs[0]['status'] == 'completed'
    assert 'test-secret-api-key' not in str(jobs) + str(drafts)


def test_generation_failure_is_sanitized(admin_client, monkeypatch):
    class FakeOpenAI:
        def __init__(self, **kwargs): raise RuntimeError('private-key-must-not-leak')
    monkeypatch.setattr(generation, 'OpenAI', FakeOpenAI)
    admin_client.post('/api/admin/generate', json={'section':'math','count':1,'api_key':'test-key'})
    jobs = admin_client.get('/api/admin/generations').json()
    assert jobs[0]['status'] == 'failed'
    assert 'private-key' not in str(jobs)


def test_validation_never_echoes_credentials(admin_client):
    secret = 'sensitive-secret-' * 100
    response = admin_client.post('/api/admin/generate', json={'section': 'math', 'api_key': secret})
    assert response.status_code == 422
    assert 'sensitive-secret' not in response.text
    response = admin_client.post('/api/admin/login', json={'password': secret})
    assert response.status_code == 422 and 'sensitive-secret' not in response.text


def test_unpublished_questions_excluded_and_empty_pool_reported(admin_client):
    with SessionLocal() as db:
        for q in db.scalars(select(Question).where(Question.section == 'logic')):
            q.status = 'draft'
        db.commit()
    response = admin_client.post('/api/attempts', json={'section': 'logic', 'mode': 'timed', 'accepted_rules': True})
    assert response.status_code == 409
    assert 'No published logic questions' in response.text
    assert admin_client.get('/api/config').json()['question_counts']['logic'] == 0


def test_cross_attempt_item_submission_is_rejected(client):
    first = start(client)
    second = start(client)
    assert client.put(f"/api/attempts/{second['id']}/items/{first['items'][0]['id']}", json={'answer': 0}).status_code == 404
    assert client.get(f"/api/attempts/{first['id']}").json()['status'] == 'finished'


def test_generation_wrong_section_is_rejected_atomically(admin_client, monkeypatch):
    question = next(q for q in seed_questions() if q.section == 'logic')
    class FakeOpenAI:
        def __init__(self, **kwargs): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs): return SimpleNamespace(status='completed', output=[], output_text=QuestionBatch(questions=[question]).model_dump_json())
    monkeypatch.setattr(generation, 'OpenAI', FakeOpenAI)
    admin_client.post('/api/admin/generate', json={'section': 'math', 'count': 1, 'api_key': 'test-key'})
    assert admin_client.get('/api/admin/generations').json()[0]['status'] == 'failed'
    assert admin_client.get('/api/admin/questions').json() == []
