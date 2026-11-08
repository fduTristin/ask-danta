import json

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from test_chat import call, completion, events
from test_quality import config, clean_config


def test_fast_review_preserves_full_evidence_and_rechecks_repairs():
    count = 0
    evidence = '纸质证明每份8元；电子证明免费。'

    def handler(request):
        nonlocal count
        if request.url.host == 'api.tavily.com':
            return httpx.Response(200, json={'results': [{'title': '合成服务说明', 'url': 'https://example.org/notice', 'content': evidence}]})
        count += 1
        body = json.loads(request.content)
        if count < 3:
            assert body['thinking']['type'] == 'enabled'
            assert body['reasoning_effort'] == 'high'
        else:
            assert body['thinking']['type'] == 'disabled'
            assert 'reasoning_effort' not in body
            payload = json.loads(body['messages'][-1]['content'])
            assert payload['evidence'][0]['snippet'] == evidence
            assert payload['allowed_citation_ids'] == ['W1']
        if count == 1:
            response = completion(None, [call()])
        elif count == 2:
            response = completion('电子证明每份8元。[W1]')
        elif count == 3:
            response = completion(json.dumps({'corrections': ['8元仅适用于纸质，电子证明免费。'], 'facts': [{
                'claim': '电子证明8元', 'source_id': 'W1', 'qualification': '8元仅适用于纸质，电子证明免费。'}]}))
        elif count == 4:
            assert len(payload['fact_checks']) == 1
            assert 'quote' not in payload['fact_checks'][0]
            assert payload['fact_checks'][0]['qualification'] == '8元仅适用于纸质，电子证明免费。'
            response = completion('电子证明免费。[W1]')
        else:
            assert count == 5 and payload['draft'] == '电子证明免费。[W1]'
            response = completion(json.dumps({'corrections': [], 'facts': [{
                'claim': '电子证明免费', 'source_id': 'W1', 'qualification': '电子证明免费。'}]}))
        result = response.json()
        result['usage'] = {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}
        return httpx.Response(200, json=result)

    with TestClient(create_app(config(model_thinking='enabled', model_reasoning_effort='high'), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        final = events(client, sid, '请查官网电子证明收费吗？')[-1]
        assert count == 5
        assert final['message']['content'] == '电子证明免费。[W1]'
        assert final['message']['status'] == 'complete'
        assert final['metrics']['review_calls'] == 3
        assert final['metrics']['answer_repairs'] == 1
        assert final['metrics']['review_prompt_tokens'] == 30
        assert final['metrics']['review_completion_tokens'] == 6
        assert final['metrics']['total_tokens'] == 60
        assert 0 <= final['metrics']['review_seconds'] <= final['metrics']['model_seconds']
