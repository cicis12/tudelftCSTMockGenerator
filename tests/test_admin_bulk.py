import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import generation
from app.database import SessionLocal
from app.models import Generation, Question
from app.schemas import QuestionBatch, fingerprint
from app.seed import seed_questions


def add_question(db, index, section='math', status='draft'):
    template = next(q for q in seed_questions() if q.section == section)
    data = template.model_copy(update={'prompt': f'Bulk review question number {index}: {template.prompt}'})
    question = Question(**data.model_dump(), fingerprint=fingerprint(data.prompt), status=status, origin='test')
    db.add(question)
    db.flush()
    return question.id


def test_approve_all_requires_admin_and_csrf(client):
    assert client.post('/api/admin/questions/approve-all').status_code == 401
    client.post('/api/admin/login', json={'password': 'test-admin-password'})
    assert client.post('/api/admin/questions/approve-all', headers={'X-CST-Request': ''}).status_code == 403
    assert client.post('/api/admin/questions/approve-all?section=invalid').status_code == 422


def test_approve_all_respects_section_and_status_and_is_repeatable(admin_client):
    with SessionLocal() as db:
        math_id = add_question(db, 1)
        logic_id = add_question(db, 2, section='logic')
        rejected_id = add_question(db, 3, status='rejected')
        db.commit()
    assert admin_client.post('/api/admin/questions/approve-all?section=math').json() == {'approved': 1}
    with SessionLocal() as db:
        assert db.get(Question, math_id).status == 'published'
        assert db.get(Question, logic_id).status == 'draft'
        assert db.get(Question, rejected_id).status == 'rejected'
    assert admin_client.post('/api/admin/questions/approve-all?section=math').json() == {'approved': 0}
    assert admin_client.post('/api/admin/questions/approve-all').json() == {'approved': 1}
    assert admin_client.get('/api/admin/questions?status=rejected').json()[0]['id'] == rejected_id
    counts = admin_client.get('/api/admin/status').json()['counts']
    published = {c['section']: c['count'] for c in counts if c['status'] == 'published'}
    assert published == {'math': 62, 'logic': 30}


def test_approve_all_includes_drafts_beyond_visible_list(admin_client):
    with SessionLocal() as db:
        for i in range(503):
            add_question(db, i)
        db.commit()
    assert len(admin_client.get('/api/admin/questions').json()) == 500
    assert admin_client.post('/api/admin/questions/approve-all').json() == {'approved': 503}
    assert admin_client.get('/api/admin/questions').json() == []


def test_approve_all_validation_is_atomic(admin_client):
    with SessionLocal() as db:
        add_question(db, 1)
        invalid_id = add_question(db, 2)
        db.get(Question, invalid_id).options = ['invalid']
        db.commit()
    response = admin_client.post('/api/admin/questions/approve-all')
    assert response.status_code == 422
    with SessionLocal() as db:
        assert len(db.scalars(select(Question).where(Question.status == 'draft')).all()) == 2


@pytest.mark.parametrize('count,expected_batches', [(100, [10] * 10), (23, [10, 10, 3])])
def test_large_generation_is_batched_with_progress(admin_client, monkeypatch, count, expected_batches):
    calls = []
    template = seed_questions()[0]

    class FakeOpenAI:
        def __init__(self, **kwargs): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            n = int(re.search(r'Generate exactly (\d+)', kwargs['input'])[1])
            with SessionLocal() as db:
                job = db.scalar(select(Generation))
                assert f'Generating batch {len(calls) + 1} of {len(expected_batches)}' in job.message
                assert db.scalar(select(Question).where(Question.status == 'draft')) is None
            if calls:
                assert 'Generated test question number 0:' in kwargs['input']
            offset = sum(calls)
            calls.append(n)
            assert kwargs['store'] is False
            questions = [template.model_copy(update={'prompt': f'Generated test question number {offset + i}: {template.prompt}'}) for i in range(n)]
            return SimpleNamespace(status='completed', output=[], output_text=QuestionBatch(questions=questions).model_dump_json())

    monkeypatch.setattr(generation, 'OpenAI', FakeOpenAI)
    assert admin_client.get('/api/admin/status').json()['generation_limit'] == 100
    assert admin_client.post('/api/admin/generate', json={'section': 'math', 'count': count, 'api_key': 'test-key'}).status_code == 202
    assert calls == expected_batches
    assert len(admin_client.get('/api/admin/questions').json()) == count
    job = admin_client.get('/api/admin/generations').json()[0]
    assert job['status'] == 'completed'
    assert f'{count} draft questions added' in job['message']
    assert admin_client.post('/api/admin/generate', json={'section': 'math', 'count': 101, 'api_key': 'test-key'}).status_code == 422


def test_later_batch_failure_leaves_no_partial_drafts(admin_client, monkeypatch):
    calls = []
    template = seed_questions()[0]

    class FakeOpenAI:
        def __init__(self, **kwargs): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise ValueError('provider-private-content')
            questions = [template.model_copy(update={'prompt': f'Partial batch question {i}: {template.prompt}'}) for i in range(10)]
            return SimpleNamespace(status='completed', output=[], output_text=QuestionBatch(questions=questions).model_dump_json())

    monkeypatch.setattr(generation, 'OpenAI', FakeOpenAI)
    assert admin_client.post('/api/admin/generate', json={'section': 'math', 'count': 11, 'api_key': 'test-key'}).status_code == 202
    assert len(calls) == 2
    assert admin_client.get('/api/admin/questions').json() == []
    job = admin_client.get('/api/admin/generations').json()[0]
    assert job['status'] == 'failed' and 'No drafts were saved' in job['message']
    assert 'provider-private-content' not in str(job)


def test_generation_deduplicates_across_batches(admin_client, monkeypatch):
    template = seed_questions()[0]

    class FakeOpenAI:
        def __init__(self, **kwargs): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def create(self, **kwargs):
            questions = [template.model_copy(update={'prompt': f'Repeated generated question {i}: {template.prompt}'}) for i in range(10)]
            return SimpleNamespace(status='completed', output=[], output_text=QuestionBatch(questions=questions).model_dump_json())

    monkeypatch.setattr(generation, 'OpenAI', FakeOpenAI)
    admin_client.post('/api/admin/generate', json={'section': 'math', 'count': 20, 'api_key': 'test-key'})
    assert len(admin_client.get('/api/admin/questions').json()) == 10
    assert '10 duplicates skipped' in admin_client.get('/api/admin/generations').json()[0]['message']
