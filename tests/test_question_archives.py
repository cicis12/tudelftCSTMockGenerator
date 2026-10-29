import io
import json
import zipfile

import pytest
from sqlalchemy import delete, func, select

from app import question_archives
from app.database import SessionLocal
from app.models import Question
from app.schemas import fingerprint
from app.seed import seed_questions


def archive_payload(questions, version=1, filename='questions.json'):
    document = {'format': 'cst-studio-questions', 'version': version, 'exported_at': 1234.0, 'questions': questions}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, json.dumps(document))
    return buffer.getvalue()


def row(prompt='An original imported practice question: find the correct domain.'):
    return {**seed_questions()[0].model_dump(), 'prompt': prompt, 'status': 'draft', 'origin': 'archive test', 'created_at': 1234.0}


def upload(client, payload):
    return client.post('/api/admin/questions/import', content=payload, headers={'Content-Type': 'application/zip'})


def count():
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Question))


def test_archives_require_admin_and_csrf(client):
    assert client.get('/api/admin/questions/export').status_code == 401
    assert upload(client, archive_payload([])).status_code == 401
    client.post('/api/admin/login', json={'password': 'test-admin-password'})
    assert client.post('/api/admin/questions/import', content=archive_payload([]), headers={'Content-Type': 'application/zip', 'X-CST-Request': ''}).status_code == 403


def test_full_export_roundtrip_includes_all_statuses(admin_client):
    with SessionLocal() as db:
        questions = db.scalars(select(Question).order_by(Question.id)).all()
        questions[0].status = 'draft'
        questions[-1].status = 'rejected'
        db.commit()
    response = admin_client.get('/api/admin/questions/export')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/zip'
    assert 'attachment;' in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ['questions.json']
        original = json.loads(archive.read('questions.json'))
    assert len(original['questions']) == 90
    assert {q['section'] for q in original['questions']} == {'math', 'logic'}
    assert {q['status'] for q in original['questions']} == {'published', 'draft', 'rejected'}
    assert all('id' not in q and 'fingerprint' not in q for q in original['questions'])
    with SessionLocal() as db:
        db.execute(delete(Question))
        db.commit()
    result = upload(admin_client, response.content)
    assert result.json() == {'imported': 90, 'skipped': 0, 'total': 90}
    with zipfile.ZipFile(io.BytesIO(admin_client.get('/api/admin/questions/export').content)) as archive:
        restored = json.loads(archive.read('questions.json'))
    assert restored['questions'] == original['questions']


def test_import_skips_existing_and_internal_duplicates(admin_client):
    new = row()
    duplicate = {**new, 'prompt': new['prompt'].upper(), 'status': 'published'}
    result = upload(admin_client, archive_payload([new, duplicate]))
    assert result.json() == {'imported': 1, 'skipped': 1, 'total': 2}
    result = upload(admin_client, archive_payload([duplicate]))
    assert result.json() == {'imported': 0, 'skipped': 1, 'total': 1}
    with SessionLocal() as db:
        saved = db.scalar(select(Question).where(Question.fingerprint == fingerprint(new['prompt'])))
        assert saved.status == 'draft' and saved.prompt == new['prompt']
    assert count() == 91


def test_invalid_question_rejects_whole_archive(admin_client):
    valid = row()
    invalid = row('Another question with a malformed list of answer options.')
    invalid['options'] = ['same', 'same', 'two', 'three']
    response = upload(admin_client, archive_payload([valid, invalid]))
    assert response.status_code == 422
    assert 'questions.1' in response.json()['detail']
    assert count() == 90


@pytest.mark.parametrize('payload', [b'not a ZIP', archive_payload([], version=2), archive_payload([], filename='../questions.json'), archive_payload([dict(row(), status='unknown')])])
def test_invalid_archives_are_rejected(admin_client, payload):
    assert upload(admin_client, payload).status_code == 422
    assert count() == 90


def test_uncompressed_limit_and_extra_members(admin_client, monkeypatch):
    monkeypatch.setattr(question_archives, 'MAX_JSON_BYTES', 100)
    assert upload(admin_client, archive_payload([row()])).status_code == 413
    buffer = io.BytesIO(archive_payload([]))
    with zipfile.ZipFile(buffer, 'a') as archive:
        archive.writestr('extra.txt', 'not part of the format')
    assert upload(admin_client, buffer.getvalue()).status_code == 422
    assert count() == 90


def test_upload_limit_enforced_without_content_length(admin_client, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, 'MAX_ZIP_BYTES', 20)
    response = admin_client.post('/api/admin/questions/import', content=iter([b'x'*15, b'x'*15]), headers={'Content-Type': 'application/zip'})
    assert response.status_code == 413
    assert count() == 90


def test_export_is_not_limited_to_library_page(admin_client):
    with SessionLocal() as db:
        for n in range(420):
            question = row(f'Additional exported question {n}: choose the correct domain.')
            db.add(Question(**question, fingerprint=fingerprint(question['prompt'])))
        db.commit()
    result = admin_client.get('/api/admin/questions/export')
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert len(json.loads(archive.read('questions.json'))['questions']) == 510


def test_empty_archive_and_wrong_content_type(admin_client):
    assert upload(admin_client, archive_payload([])).json() == {'imported': 0, 'skipped': 0, 'total': 0}
    assert admin_client.post('/api/admin/questions/import', json={}).status_code == 415
