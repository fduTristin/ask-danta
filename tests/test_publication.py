"""Task completion, campus provenance, quotation and fee evidence regressions."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.answer import AnswerAudit, audit_fact_errors, copied_posts, model_history, model_view, retrieval_forbidden, review_payload, requested_actions
from app.main import create_app
from test_chat import completion, call, events, search_result
from test_quality import config, clean_config
from test_research import config as campus_config


def test_model_context_hides_database_floor_ids_without_changing_sources():
    source = dict(id='C2', source='campus', hole_id=42, floor_id=9021,
                  title='树洞 #42 · 楼层 ID 9021', snippet='这条是检索得到的个人办理经验。')
    history = [{'role': 'tool', 'content': json.dumps({'results': [source]})}]*2
    view = model_history(history)
    assert '9021' not in json.dumps(view) and 'floor_id' not in json.dumps(view)
    assert 'snippet' not in json.loads(view[0]['content'])['results'][0]
    assert json.loads(view[1]['content'])['results'][0]['snippet'] == source['snippet']
    assert '9021' in json.dumps(history) and source['floor_id'] == 9021
    assert model_view(source)['id'] == 'C2'


def test_whole_post_check_ignores_punctuation_but_not_short_common_words():
    sources = [dict(id='C1', source='campus', snippet='请先填写申请表，再到服务窗口提交。'),
               dict(id='C2', source='campus', snippet='谢谢')]
    assert copied_posts('有人说：请先填写申请表\n再到服务窗口提交 [C1]。', sources) == ['C1']
    assert not copied_posts('同学建议先备齐表格后去窗口。谢谢。[C1]', sources)


@pytest.mark.parametrize('succeed', [True, False])
def test_copy_guard_repairs_or_fails_without_reproducing_post_in_fallback(tmp_path, succeed):
    body = '先在网上填写申请表再去服务窗口交材料'
    n = 0
    def handler(request):
        nonlocal n
        n += 1
        if n > 1:
            payload = json.loads(json.loads(request.content)['messages'][-1]['content'])
            assert payload['validation_errors'][0]['code'] == 'whole_post_copy'
        return completion('同学建议先在线准备，再到窗口办理。[C1]' if succeed and n == 2 else body+'[C1]')
    with TestClient(create_app(campus_config(tmp_path), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        client.app.state.sessions[sid].sources = [dict(id='C1', source='campus', is_mock=False,
            hole_id=12, floor_id=99, title='树洞 #12 · 楼层 ID 99', snippet=body)]
        final = events(client, sid, '概括已有帖子，不复制原文')[-1]
        assert final['message']['status'] == ('complete' if succeed else 'incomplete')
        assert body not in final['message']['content']
        assert n <= 5


def test_required_action_cannot_be_replaced_by_prose_correction():
    n = 0
    def handler(request):
        nonlocal n
        if request.url.host == 'api.tavily.com':
            return search_result()
        n += 1
        if n == 1:
            return completion('不知道官网名称。')
        if n == 2:
            return completion('{"required_actions":["search_web"],"corrections":[]}')
        if n == 3:
            payload = json.loads(json.loads(request.content)['messages'][-1]['content'])
            assert payload['missing_actions'] == ['search_web']
            return completion(None, [call()])
        if n == 4:
            return completion('官方通知[W1]')
        return completion('{"required_actions":["search_web"],"corrections":[]}')
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        final = events(client, sid, '请查官网名称')[-1]
        assert final['tool_calls'] == 1 and final['message']['status'] == 'complete'


def test_persistently_skipped_required_action_is_not_marked_complete():
    n = 0
    def handler(request):
        nonlocal n
        n += 1
        return completion('我可以解释查询方法。' if n == 1 else '{"required_actions":["read_campus_thread"],"corrections":[]}')
    # Use web retrieval to keep the test independent of credentials.
    def web_handler(request):
        response = handler(request)
        return httpx.Response(200, content=response.content.replace(b'read_campus_thread', b'read_web'))
    with TestClient(create_app(config(), httpx.MockTransport(web_handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        final = events(client, sid, '请读取命中网页')[-1]
        assert final['message']['status'] == 'incomplete' and n <= 5


@pytest.mark.parametrize('question', ['不要再搜索，最多100字', '只依据已有资料说明', '不用检索，确认校区'])
def test_explicit_no_retrieval_constraints(question):
    assert retrieval_forbidden(question)


def test_model_cannot_execute_search_when_user_forbids_it():
    n = 0
    def handler(request):
        nonlocal n
        assert request.url.host != 'api.tavily.com'
        assert 'tools' not in json.loads(request.content)
        n += 1
        return completion(None, [call()]) if n == 1 else completion('本轮没有检索。')
    with TestClient(create_app(config(answer_review_enabled=False), httpx.MockTransport(handler))) as client:
        sid = client.post('/api/sessions').json()['session_id']
        result = events(client, sid, '不要再搜索，只确认条件')
        assert any(e.get('error', {}).get('code') == 'retrieval_not_allowed' for e in result)


def test_fee_audit_must_ground_its_quote_in_actual_evidence():
    payload = dict(draft='电子证明8元[W1]', evidence=[dict(id='W1', snippet='纸质证明8元，电子证明免费。')])
    assert audit_fact_errors(AnswerAudit(corrections=[]), payload)
    audit = AnswerAudit.model_validate(dict(corrections=['电子版费用不应写成8元'], facts=[dict(
        claim='电子证明8元', source_id='W1', quote='纸质证明8元，电子证明免费。', qualification='8元仅纸质；电子免费')]))
    assert not audit_fact_errors(audit, payload)
    audit.facts[0].quote = '电子证明8元'
    assert not audit_fact_errors(audit, payload)
    assert audit.facts[0].quote == '纸质证明8元，电子证明免费。'
    audit.facts[0].source_id = 'W99'
    assert audit_fact_errors(audit, payload)


def test_review_preserves_reply_metadata_without_claiming_complete_read():
    source = dict(id='C1', source='campus', is_mock=False, hole_id=12, floor_id=456, snippet='合成经验')
    history = [dict(role='tool', content=json.dumps(dict(thread=dict(id=12, reply=9),
        raw_count=1, offset=0, complete=False, has_more=None, results=[source])))]
    payload = review_payload('只读取一层是否代表全部？', history, [source], 0, '未提供回复数[C1]', None)
    page = payload['thread_reads'][0]
    assert page['reported_reply_count'] == 9 and page['raw_count'] == 1 and not page['complete']
    assert page['source_ids'] == ['C1'] and 'floor_id' not in json.dumps(payload)


@pytest.mark.parametrize('question,expected', [
    ('请搜索相关帖子并读取上下文', {'search_campus_posts', 'read_campus_thread'}),
    ('请查官网资料，再读取网页正文', {'search_web', 'read_web'}),
    ('只用已有资料，不要再搜索', set()),
    ('解释如何读取网页，不用实际操作', set()),
    ('请解释“请搜索官网”这句话', set()),
    ('不要读取网页，先确认我的校区', set()),
])
def test_explicit_actions_do_not_treat_negations_or_quoted_instructions_as_commands(question, expected):
    assert requested_actions(question) == expected
