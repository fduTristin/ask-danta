"""Retry the last incomplete turn without branching or losing prior context."""
import json

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sessions import SessionStorageError


def test_retry_keeps_identity_and_recovers_pending_after_restart(tmp_path):
    requests = []

    def upstream(request):
        requests.append(json.loads(request.content))
        if len(requests) == 2:
            return httpx.Response(500)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "合成成功回答"}}]})

    settings = Settings(model_api_key="synthetic", answer_review_enabled=False,
                        session_db_file=tmp_path / "chat.sqlite3", campus_auth_file=tmp_path / "no-auth")
    transport = httpx.MockTransport(upstream)
    with TestClient(create_app(settings, transport)) as client:
        sid = client.post('/api/sessions').json()['session_id']
        for text in ('先前问题', '失败问题'):
            client.post(f'/api/sessions/{sid}/chat', json={'message': text, 'source_mode': 'web'})
        original = client.get(f'/api/sessions/{sid}').json()
        assert original['messages'][-1]['status'] == 'incomplete'
        body = {'message_index': 2, 'expected_message_count': 4}
        assert client.post(f'/api/sessions/{sid}/retry', json={**body, 'expected_message_count': 2}).status_code == 409
        assert client.post(f'/api/sessions/{sid}/retry', json={**body, 'message_index': 0}).status_code == 422
        session = client.app.state.sessions[sid]
        session.busy = True
        assert client.post(f'/api/sessions/{sid}/retry', json=body).status_code == 409
        session.busy = False
        result = client.post(f'/api/sessions/{sid}/retry', json=body)
        assert result.status_code == 200
        retry = result.json()
        assert retry['session_id'] == sid and retry['title'] == original['title']
        assert retry['created_at'] == original['created_at']
        assert retry['messages'] == original['messages'][:2]
        assert retry['pending_question'] == '失败问题' and retry['interrupted']
        assert len(client.get('/api/sessions').json()['sessions']) == 1
        assert client.post(f'/api/sessions/{sid}/retry', json=body).status_code == 409

    with TestClient(create_app(settings, transport)) as client:
        assert client.get(f'/api/sessions/{sid}').json()['pending_question'] == '失败问题'
        client.post(f'/api/sessions/{sid}/chat', json={'message': '失败问题', 'source_mode': 'web'})
        final = client.get(f'/api/sessions/{sid}').json()
        assert len(final['messages']) == 4 and final['messages'][-1]['status'] == 'complete'
        assert final['pending_question'] is None
        assert [m['content'] for m in requests[-1]['messages'] if m['role'] == 'user'] == ['先前问题', '失败问题']
        assert 'HTTP 500' not in json.dumps(requests[-1], ensure_ascii=False)
        assert len(client.get('/api/sessions').json()['sessions']) == 1
        assert client.post(f'/api/sessions/{sid}/retry', json=body).status_code == 422


def test_retry_storage_failure_keeps_failed_answer(tmp_path, monkeypatch):
    settings = Settings(model_api_key="synthetic", answer_review_enabled=False,
                        session_db_file=tmp_path / "chat.sqlite3", campus_auth_file=tmp_path / "no-auth")
    with TestClient(create_app(settings, httpx.MockTransport(lambda request: httpx.Response(500)))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        client.post(f'/api/sessions/{sid}/chat', json={'message': '失败问题'})
        original = client.get(f'/api/sessions/{sid}').json()

        def fail_save(session):
            raise SessionStorageError('synthetic save failure')

        monkeypatch.setattr(client.app.state.store, 'save', fail_save)
        result = client.post(f'/api/sessions/{sid}/retry', json={'message_index': 0, 'expected_message_count': 2})
        assert result.status_code == 503
        assert client.get(f'/api/sessions/{sid}').json() == original
