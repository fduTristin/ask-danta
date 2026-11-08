import json

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.sessions import fork_session
from app.agent import Session


def test_fork_preserves_original_and_excludes_later_context(tmp_path):
    calls = []

    def completion(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "合成回答"}, "finish_reason": "stop"}]})

    settings = Settings(_env_file=None, model_api_key="synthetic", answer_review_enabled=False,
                        campus_auth_file=tmp_path / "no-auth")
    with TestClient(create_app(settings, httpx.MockTransport(completion))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        for question in ['第一轮', '待编辑的问题', '后续问题']:
            client.post(f'/api/sessions/{sid}/chat', json={'message': question, 'source_mode': 'web'})
        original = client.get(f'/api/sessions/{sid}').json()
        result = client.post(f'/api/sessions/{sid}/fork', json={'message_index': 2, 'expected_message_count': 6})
        assert result.status_code == 201
        branch = result.json()
        assert branch['messages'] == original['messages'][:2]
        assert client.get(f'/api/sessions/{sid}').json() == original
        client.post(f"/api/sessions/{branch['session_id']}/chat", json={'message': '修改的问题', 'source_mode': 'web'})
        context = json.dumps(calls[-1], ensure_ascii=False)
        assert '第一轮' in context and '修改的问题' in context
        assert '待编辑的问题' not in context and '后续问题' not in context
        assert client.post(f'/api/sessions/{sid}/fork', json={'message_index': 1, 'expected_message_count': 6}).status_code == 422
        assert client.post(f'/api/sessions/{sid}/fork', json={'message_index': 8, 'expected_message_count': 6}).status_code == 422
        assert client.post(f'/api/sessions/{sid}/fork', json={'message_index': 0, 'expected_message_count': 4}).status_code == 409
        client.app.state.sessions[sid].busy = True
        assert client.post(f'/api/sessions/{sid}/fork', json={'message_index': 0, 'expected_message_count': 6}).status_code == 409


def test_fork_preserves_web_isolation_and_tool_pairs():
    first = [{'role': 'user', 'content': '第一轮'},
             {'role': 'assistant', 'tool_calls': [{'id': 'call-1'}]},
             {'role': 'tool', 'tool_call_id': 'call-1', 'content': '{"id":"C1"}'},
             {'role': 'assistant', 'content': '树洞回答 [C1]'}]
    second = [{'role': 'user', 'content': '下一轮'}, {'role': 'assistant', 'content': '之后的 [C2]'}]
    safe = [{'role': 'user', 'content': '第一轮'}, {'role': 'assistant', 'content': '省略树洞资料'}]
    session = Session(history=first + second, web_history=safe + second,
                      messages=[first[0], first[-1], *second],
                      sources=[{'id': 'C1'}, {'id': 'C2'}])
    branch = fork_session(session, 2)
    assert branch.history == first
    assert branch.web_history == safe
    assert branch.sources == [{'id': 'C1'}]
    assert fork_session(session, 0).history == []
    branch.sources[0]['id'] = 'changed'
    assert session.sources[0]['id'] == 'C1'
