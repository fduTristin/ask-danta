import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import httpx
from fastapi.testclient import TestClient

from app.agent import Session
from app.config import Settings
from app.main import create_app
from app.sessions import SessionStore, SessionStorageError
from app.progress import Progress


def settings(tmp_path):
    return Settings(_env_file=None, model_api_key="synthetic-model-key", search_api_key="synthetic-search-key",
                    campus_auth_file=tmp_path / "no-tokens", session_db_file=tmp_path / "history" / "test.sqlite3",
                    answer_review_enabled=False)


def completion(request):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "你好，有什么校园问题？"}, "finish_reason": "stop"}]})


def test_restart_history_preferences_rename_and_delete(tmp_path):
    config = settings(tmp_path)
    with TestClient(create_app(config, httpx.MockTransport(completion))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        assert client.get('/api/sessions').json() == {'sessions': []}
        result = client.post(f'/api/sessions/{sid}/chat', json={'message': '你好', 'source_mode': 'web', 'source_preference': 'web'})
        assert '"type": "final"' in result.text
        original = client.get(f'/api/sessions/{sid}').json()
        final = [json.loads(frame[6:]) for frame in result.text.strip().split('\n\n')][-1]
        assert original['messages'][-1]['metrics'] == final['metrics']
        assert final['metrics']['model_calls'] == 1
        assert final['metrics']['tool_calls'] == final['metrics']['campus_pages'] == 0
        assert final['metrics']['budget_reasons'] == []
        progress = original['messages'][-1]['progress']
        assert progress == final['message']['progress']
        assert progress['status'] == 'complete'
        assert progress['steps'][0]['label'] == '理解问题与已有资料'
        assert progress['steps'][0]['status'] == 'complete'
        frames = [json.loads(frame[6:]) for frame in result.text.strip().split('\n\n')]
        assert next(frame for frame in frames if frame['type'] == 'model_start')['progress']['steps'][0]['status'] == 'running'
        assert original['source_preference'] == 'web'
        assert client.patch(f'/api/sessions/{sid}', json={'title': '江湾办事'}).status_code == 200
        assert client.patch(f'/api/sessions/{sid}', json={'title': '  '}).status_code == 422
    with TestClient(create_app(config, httpx.MockTransport(completion))) as client:
        restored = client.get(f'/api/sessions/{sid}').json()
        assert restored['messages'] == original['messages']
        assert restored['title'] == '江湾办事'
        assert restored['source_preference'] == 'web'
        assert not restored['busy']
        assert len(client.get('/api/sessions').json()['sessions']) == 1
        assert client.delete(f'/api/sessions/{sid}').status_code == 204
    with TestClient(create_app(config, httpx.MockTransport(completion))) as client:
        assert client.get(f'/api/sessions/{sid}').status_code == 404
        assert client.get('/api/sessions').json()['sessions'] == []


def test_atomic_sources_web_isolation_and_no_reasoning_on_disk(tmp_path):
    config = settings(tmp_path)
    with TestClient(create_app(config, httpx.MockTransport(completion))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        session = client.app.state.sessions[sid]
        session.history = [{'role': 'user', 'content': '查询'}, {'role': 'assistant', 'content': '校内片段', 'reasoning_content': 'private-reasoning'}]
        session.web_history = [{'role': 'user', 'content': '查询'}, {'role': 'assistant', 'content': '仅网页占位'}]
        session.sources = [{'id': 'C1', 'source': 'campus', 'snippet': '合成摘录', 'is_mock': False}]
        session.messages = [{'role': 'assistant', 'content': '回答 [C1]', 'sources': session.sources}]
        client.app.state.store.save(session)
    model_requests = []
    def record(request):
        model_requests.append(json.loads(request.content))
        return completion(request)
    with TestClient(create_app(config, httpx.MockTransport(record))) as client:
        restored = client.get(f'/api/sessions/{sid}').json()
        assert restored['messages'][0]['sources'] == restored['sources']
        client.post(f'/api/sessions/{sid}/chat', json={'message': '你好', 'source_mode': 'web'})
        assert '校内片段' not in json.dumps(model_requests, ensure_ascii=False)
        assert client.post(f'/api/sessions/{sid}/clear').json()['messages'] == []
    assert b'private-reasoning' not in config.sessions_path.read_bytes()
    assert b'synthetic-model-key' not in config.sessions_path.read_bytes()
    with TestClient(create_app(config)) as client:
        restored = client.get(f'/api/sessions/{sid}').json()
        assert restored['messages'] == restored['sources'] == []


def test_interrupted_turn_restores_without_fabricating_answer(tmp_path):
    config = settings(tmp_path)
    store = SessionStore(config.sessions_path)
    session = Session(title='未完成的问题', pending_question='帮我查一下', busy=True)
    progress = Progress()
    progress.update({'type': 'model_start'})
    session.progress = progress.value
    store.save(session)
    store.close()
    with TestClient(create_app(config)) as client:
        restored = client.get(f'/api/sessions/{session.id}').json()
        assert not restored['busy'] and restored['interrupted']
        assert restored['pending_question'] == '帮我查一下'
        assert restored['messages'] == []
        assert restored['progress']['status'] == 'interrupted'
        assert restored['progress']['steps'][0]['status'] == 'interrupted'


def test_restore_missing_lowercase_sources_without_crossing_source_permissions(tmp_path):
    store = SessionStore(settings(tmp_path).sessions_path)
    source = {'id': 'C121', 'source': 'campus', 'is_mock': False, 'snippet': '合成历史资料'}
    session = Session(sources=[source, {'id': 'W2', 'source': 'web', 'is_mock': True}])
    session.messages = [
        {'role': 'assistant', 'content': '已有经验[c121]，不存在[c999]，合成[w2]', 'sources': [], 'source_mode': 'all'},
        {'role': 'assistant', 'content': '不能补入校内内容[c121]', 'sources': [], 'source_mode': 'web'},
        {'role': 'assistant', 'content': '已有关联[c121]', 'sources': [{**source, 'snippet': '保留当时的摘录'}]},
    ]
    store.save(session)
    restored = store.load()[session.id]
    assert restored.messages[0]['sources'] == [source]
    assert restored.messages[1]['sources'] == []
    assert restored.messages[2]['sources'][0]['snippet'] == '保留当时的摘录'
    assert session.messages[0]['sources'] == []
    store.save(restored)
    assert store.load()[session.id].messages == restored.messages
    store.close()


def test_failed_final_save_does_not_claim_success(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path), httpx.MockTransport(completion))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        store = client.app.state.store
        original = store.save
        def fail_final(session):
            if session.messages:
                raise SessionStorageError('合成磁盘写入失败')
            original(session)
        monkeypatch.setattr(store, 'save', fail_final)
        response = client.post(f'/api/sessions/{sid}/chat', json={'message': '你好'})
        assert '"type": "final"' not in response.text
        assert '合成磁盘写入失败' in response.text
        restored = client.get(f'/api/sessions/{sid}').json()
        assert restored['messages'] == [] and restored['interrupted']


def test_cancel_releases_and_delete_cannot_be_resurrected(tmp_path):
    entered = threading.Event()
    cancelled = threading.Event()
    async def delayed(request):
        entered.set()
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()
        return completion(request)
    with TestClient(create_app(settings(tmp_path), httpx.MockTransport(delayed))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        with ThreadPoolExecutor() as pool:
            turn = pool.submit(client.post, f'/api/sessions/{sid}/chat', json={'message': '你好'})
            assert entered.wait(5)
            running = client.get(f'/api/sessions/{sid}').json()['progress']
            assert running['status'] == 'running'
            assert running['steps'][0]['status'] == 'running'
            assert client.delete(f'/api/sessions/{sid}').status_code == 409
            assert client.patch(f'/api/sessions/{sid}', json={'title': '忙碌时修改'}).status_code == 409
            assert client.post(f'/api/sessions/{sid}/cancel').status_code == 202
            assert cancelled.wait(5)
            turn.result(timeout=5)
        stopped = client.get(f'/api/sessions/{sid}').json()
        assert not stopped['busy']
        assert stopped['progress']['status'] == 'interrupted'
        assert stopped['progress']['steps'][0]['status'] == 'interrupted'
        assert client.delete(f'/api/sessions/{sid}').status_code == 204
        assert client.get(f'/api/sessions/{sid}').status_code == 404
