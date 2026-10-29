import os
import tempfile
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tempfile.mkdtemp(prefix='cst-tests-')) / 'test.db')
os.environ['SECRET_KEY'] = 'test-only-secret-' * 4
os.environ['ADMIN_PASSWORD'] = 'test-admin-password'
os.environ['OPENAI_API_KEY'] = ''
os.environ['COOKIE_SECURE'] = 'false'

import pytest
from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app, login_failures
from app.accounts import auth_attempts


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    login_failures.clear()
    auth_attempts.clear()
    with TestClient(app, headers={'X-CST-Request': '1'}) as client:
        yield client


@pytest.fixture
def admin_client(client):
    response = client.post('/api/admin/login', json={'password': 'test-admin-password'})
    assert response.status_code == 200
    return client
