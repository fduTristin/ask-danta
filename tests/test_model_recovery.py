import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.progress import Progress
from test_chat import call, completion, events, search_result
from test_quality import config, clean_config


def truncated():
    return httpx.Response(200, json={
        'choices': [{'finish_reason': 'length', 'message': {
            'role': 'assistant', 'content': None, 'reasoning_content': 'private-reasoning'}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 4096, 'total_tokens': 4196},
    })


@pytest.mark.parametrize('recovered', [True, False])
def test_review_truncation_retries_once_without_publishing_unchecked_content(recovered):
    requests = []

    def handler(request):
        if request.url.host == 'api.tavily.com':
            return search_result()
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return completion(None, [call()])
        if len(requests) == 2:
            return completion('候选答案 [W1]')
        if len(requests) == 3 or not recovered:
            return truncated()
        return completion('{"corrections": []}')

    with TestClient(create_app(config(model_thinking='enabled', model_reasoning_effort='high', model_max_tokens=4096), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        result = events(client, sid)
        final = result[-1]
        metrics = final['metrics']
        assert len(requests) == 4
        assert requests[0]['thinking']['type'] == requests[1]['thinking']['type'] == 'enabled'
        assert requests[2]['thinking']['type'] == 'disabled'
        assert requests[3]['thinking']['type'] == 'disabled'
        assert 'reasoning_effort' not in requests[3]
        assert requests[3]['max_tokens'] == requests[2]['max_tokens'] == 4096
        assert metrics['review_response_retries'] == 1
        assert metrics['review_response_finish_reason'] == 'length'
        assert metrics['review_calls'] == 2
        assert metrics['completion_tokens'] == 4096 * (1 if recovered else 2)
        assert metrics['usage_reported_calls'] == (1 if recovered else 2)
        assert metrics['review_completion_tokens'] == metrics['completion_tokens']
        assert 0 <= metrics['review_seconds'] <= metrics['model_seconds']
        assert any(event['type'] == 'review_retry' for event in result)
        assert 'private-reasoning' not in json.dumps(result)
        if recovered:
            assert final['message']['content'] == '候选答案 [W1]'
            assert final['message']['status'] == 'complete'
            assert not any(event['type'] == 'error' for event in result)
        else:
            assert final['message']['status'] == 'incomplete'
            assert '候选答案' not in json.dumps(result, ensure_ascii=False)
            assert '江湾窗口' not in final['message']['content']
            assert metrics['error_stage'] == 'review'
            assert metrics['error_finish_reason'] == 'length'
            assert metrics['error_code'] == 'model_output_truncated'
        saved = client.get(f'/api/sessions/{sid}').json()
        assert saved['sources'][0]['snippet'] == '请到江湾窗口办理。'
        assert saved['messages'][-1]['metrics'] == metrics


def test_review_auth_failure_does_not_retry():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return completion('你好') if count == 1 else httpx.Response(401, text='secret-body')

    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        result = events(client, sid, '你好')
        assert count == 2
        assert result[-1]['metrics']['error_stage'] == 'review'
        assert result[-1]['metrics']['error_code'] == 'model_auth_failed'
        assert 'secret-body' not in json.dumps(result)


def test_retry_step_marks_failed_review_and_keeps_fixed_public_copy():
    progress = Progress()
    progress.update({'type': 'review_start'})
    progress.update({'type': 'review_retry', 'message': 'private-output'})
    assert progress.value['steps'][0]['status'] == 'error'
    assert progress.value['steps'][1]['label'] == '重试答案核对'
    assert progress.value['status'] == 'running'
    progress.update({'type': 'review_start'})
    progress.update({'type': 'final', 'message': {'status': 'complete'}})
    assert progress.value['status'] == 'complete'
    assert 'private-output' not in json.dumps(progress.value)


def test_review_does_not_retry_when_little_time_remains():
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return completion('你好') if count == 1 else truncated()

    with TestClient(create_app(config(request_budget_seconds=0.5), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        result = events(client, sid, '你好')
        assert count == 2
        assert not any(event['type'] == 'review_retry' for event in result)
        assert result[-1]['metrics']['error_code'] == 'model_output_truncated'
