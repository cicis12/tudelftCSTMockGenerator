"""Exercise the installed OpenAI SDK with simulated HTTP, not a stubbed parser."""
import json

import httpx
import pytest
from openai import OpenAI

from app import generation
from app.schemas import TOPICS
from app.seed import seed_questions


def response_body(text, status='completed', reason=None, refusal=False):
    content = [{'type': 'refusal', 'refusal': 'private-provider-text'}] if refusal else [
        {'type': 'output_text', 'text': text, 'annotations': []}]
    return {'id': 'resp_test', 'object': 'response', 'created_at': 1, 'model': 'gpt-4.1-mini',
            'status': status, 'error': None,
            'incomplete_details': {'reason': reason} if reason else None,
            'output': [{'type': 'message', 'id': 'msg_test', 'status': status, 'role': 'assistant', 'content': content}]}


def install_transport(monkeypatch, handler):
    def client(**kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(generation, 'OpenAI', client)


def question(index=0):
    row = seed_questions()[0].model_dump()
    row['prompt'] = f'HTTP generation question {index}: {row["prompt"]}'
    return row


def run(admin_client, count=1):
    result = admin_client.post('/api/admin/generate', json={
        'section': 'math', 'count': count, 'model': 'gpt-4.1-mini', 'api_key': 'private-test-key'})
    assert result.status_code == 202
    return admin_client.get('/api/admin/generations').json()[0]


def test_twenty_questions_through_real_sdk(admin_client, monkeypatch):
    calls = []
    def handler(request):
        data = json.loads(request.content)
        assert data['model'] == 'gpt-4.1-mini'
        assert data['store'] is False
        schema = data['text']['format']['schema']
        assert data['text']['format']['strict'] is True
        item_schema = next(iter(schema['$defs'].values()))
        assert item_schema['properties']['topic']['enum'] == TOPICS['math']
        assert item_schema['properties']['section']['const'] == 'math'
        assert schema['properties']['questions']['minItems'] == 10
        assert schema['properties']['questions']['maxItems'] == 10
        offset = len(calls) * 10
        calls.append(data)
        return httpx.Response(200, json=response_body(json.dumps({'questions': [question(i) for i in range(offset, offset+10)]})))
    install_transport(monkeypatch, handler)
    assert run(admin_client, 20)['status'] == 'completed'
    assert len(calls) == 2
    assert len(admin_client.get('/api/admin/questions').json()) == 20


@pytest.mark.parametrize('bad', ['topic', 'count', 'options', 'json', 'empty', 'tokens'])
def test_invalid_response_recovers_on_one_retry(admin_client, monkeypatch, bad):
    calls = []
    def handler(request):
        data = json.loads(request.content)
        calls.append(data)
        row = question()
        if len(calls) == 1:
            if bad == 'topic': row['topic'] = 'Differentiation'
            if bad == 'options': row['options'] = ['A', 'A', 'C', 'D']
            text = json.dumps({'questions': [] if bad == 'count' else [row]})
            if bad == 'json': text = '{"questions": [{"prompt": "bad \\sqrt JSON"}]}'
            if bad == 'empty': text = ''
            if bad == 'tokens':
                return httpx.Response(200, json=response_body('{"questions": [', 'incomplete', 'max_output_tokens'))
            return httpx.Response(200, json=response_body(text))
        assert 'previous response could not be used' in data['input']
        assert data['max_output_tokens'] == (32000 if bad == 'tokens' else 16000)
        return httpx.Response(200, json=response_body(json.dumps({'questions': [row]})))
    install_transport(monkeypatch, handler)
    assert run(admin_client)['status'] == 'completed'
    assert len(calls) == 2
    assert len(admin_client.get('/api/admin/questions').json()) == 1


def test_invalid_output_gives_safe_specific_error(admin_client, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        row = question()
        row['topic'] = 'private-provider-text private-test-key'
        return httpx.Response(200, json=response_body(json.dumps({'questions': [row]})))
    install_transport(monkeypatch, handler)
    job = run(admin_client)
    assert len(calls) == 2
    assert job['status'] == 'failed'
    assert 'questions.0.topic: value outside the allowed choices' in job['message']
    assert 'Automatic retry also failed' in job['message']
    assert 'private-' not in str(job)
    assert admin_client.get('/api/admin/questions').json() == []


@pytest.mark.parametrize('kind,expected', [('refusal', 'declined'), ('tokens', 'token limit'), ('filter', 'filtered')])
def test_output_failures_are_distinguished(admin_client, monkeypatch, kind, expected):
    calls = []
    def handler(request):
        calls.append(request)
        payload = response_body('', refusal=True) if kind == 'refusal' else response_body(
            '{"questions": [', 'incomplete', 'max_output_tokens' if kind == 'tokens' else 'content_filter')
        return httpx.Response(200, json=payload)
    install_transport(monkeypatch, handler)
    job = run(admin_client)
    assert job['status'] == 'failed' and expected in job['message']
    assert len(calls) == (2 if kind == 'tokens' else 1)
    assert 'private-' not in str(job)
    assert admin_client.get('/api/admin/questions').json() == []


@pytest.mark.parametrize('status,code,expected', [
    (401, 'invalid_api_key', 'rejected the API key'),
    (403, 'permission_denied', 'denied access'),
    (404, 'model_not_found', 'model or endpoint'),
    (429, 'insufficient_quota', 'quota is exhausted'),
    (429, 'rate_limit_exceeded', 'rate limit'),
    (400, 'invalid_json_schema', 'Responses JSON-schema'),
    (500, 'server_error', 'temporarily unavailable'),
])
def test_api_errors_are_specific_and_redacted(admin_client, monkeypatch, status, code, expected):
    def handler(request):
        return httpx.Response(status, json={'error': {'message': 'private-test-key private-provider-text',
                                                   'type': 'test_error', 'code': code}})
    install_transport(monkeypatch, handler)
    job = run(admin_client)
    assert job['status'] == 'failed' and expected in job['message']
    assert 'private-' not in str(job)
