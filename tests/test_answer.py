"""Publication constraints, bounded recovery and isolation of review evidence."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import Agent, Session
from app.answer import character_limit, review_payload
from app.main import create_app
from app.model import ModelService
from app.search import SearchService
from test_chat import call, completion, events, search_result
from test_quality import clean_config, config


@pytest.mark.parametrize("question,expected", [
    ("最多100字，说明各渠道费用", 100), ("请不超过 80 字", 80),
    ("用120字以内回答", 120), ("刚才最多100字，现在最多200字", 200),
    ("费用100元，办理3天", None), ("详细说明", None),
])
def test_explicit_character_caps_do_not_confuse_other_numbers(question, expected):
    assert character_limit(question) == expected


def test_failed_campus_citation_is_repaired_without_new_tools():
    n = 0

    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            return search_result()
        n += 1
        if n == 1:
            return completion(None, [call()])
        if n == 2:
            return completion("官网说明到江湾窗口 [W1]。")
        body = json.loads(request.content)
        payload = json.loads(body["messages"][-1]["content"])
        assert payload["allowed_citation_ids"] == ["W1"]
        if n == 3:
            return completion('{"corrections": ["精简答案"]}')
        if n == 4:
            # Even an editor can introduce a fabricated citation; validate it too.
            return completion("树洞不可用 [C1]，官网说明到江湾窗口 [W1]。")
        if n == 6:
            assert not payload["validation_errors"]
            return completion('{"corrections": []}')
        assert "tools" not in body
        assert payload["validation_errors"] == [{"code": "unknown_citations", "ids": ["C1"]}]
        return completion("官网说明到江湾窗口 [W1]。")

    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session = client.post("/api/sessions").json()["session_id"]
        final = events(client, session)[-1]
        assert final["message"]["status"] == "complete"
        assert final["tool_calls"] == 1 and n == 6
        assert "C1" not in json.dumps(client.app.state.sessions[session].history)


@pytest.mark.parametrize("repairs_succeed", [True, False])
def test_overlong_answer_has_bounded_repairs_and_never_gets_cut_mid_sentence(repairs_succeed):
    n = 0
    long = "这是很长的答复。" * 30

    def handler(request):
        nonlocal n
        n += 1
        if n > 1:
            body = json.loads(request.content)
            payload = json.loads(body["messages"][-1]["content"])
            assert "tools" not in body
            assert payload["output_constraints"] == {"max_characters": 40, "draft_characters": len(long)}
            assert payload["validation_errors"][0]["code"] == "answer_too_long"
        return completion("按你的要求简要说明。" if n == 3 and repairs_succeed else long)

    with TestClient(create_app(config(answer_review_enabled=False), httpx.MockTransport(handler))) as client:
        session = client.post("/api/sessions").json()["session_id"]
        final = events(client, session, "请简要解释你的用途，最多40字")[-1]
        assert n == (3 if repairs_succeed else 5) and final["tool_calls"] == 0
        assert len(final["message"]["content"]) <= 40
        assert final["message"]["status"] == ("complete" if repairs_succeed else "incomplete")
        assert long not in json.dumps(client.app.state.sessions[session].history, ensure_ascii=False)


def test_review_uses_actual_read_text_and_never_promotes_assistant_claims():
    source = {"id": "W1", "is_mock": False, "title": "渠道说明", "snippet": "纸质收费，电子渠道另有规则。"}
    history = [{"role": "user", "content": "原来在甲校区"},
               {"role": "assistant", "content": "旧答案猜测所有渠道都收费"},
               {"role": "tool", "tool_call_id": "read", "content": json.dumps({
                   "source_id": "W1", "text": "纸质申请每份8元。未说明电子版价格。", "truncated": False})},
               {"role": "user", "content": "改到乙校区，问电子版价格"}]
    payload = review_payload(history[-1]["content"], history, [source], 3, "电子版8元 [W1]", 50)
    assert "旧答案猜测" not in json.dumps(payload["evidence"], ensure_ascii=False)
    assert payload["previous_answer_for_reference_only"] == "旧答案猜测所有渠道都收费"
    assert payload["evidence"][0]["page_text"] == "纸质申请每份8元。未说明电子版价格。"
    assert payload["evidence"][0]["page_read"] is True
    assert payload["user_turns"] == ["原来在甲校区", "改到乙校区，问电子版价格"]
    assert "page_text" not in source


def test_web_only_review_does_not_receive_old_campus_evidence_or_answer():
    n = 0
    def handler(request):
        nonlocal n
        n += 1
        assert "private-campus" not in request.content.decode()
        if n == 1:
            return completion("请到网页列出的窗口 [W1]。")
        payload = json.loads(json.loads(request.content)["messages"][-1]["content"])
        assert payload["allowed_citation_ids"] == ["W1"]
        assert all(s["id"] != "C1" for s in payload["evidence"])
        return completion('{"corrections": []}')

    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        session = client.app.state.sessions[session_id]
        session.sources = [
            {"id": "C1", "source": "campus", "snippet": "private-campus-evidence", "is_mock": False},
            {"id": "W1", "source": "web", "snippet": "官网窗口", "is_mock": False},
        ]
        session.history = [{"role": "assistant", "content": "private-campus-answer"}]
        session.web_history = [{"role": "user", "content": "我在甲校区"}]
        response = client.post(f"/api/sessions/{session_id}/chat", json={"message": "仅用网页说明", "source_mode": "web"})
        assert response.status_code == 200 and n == 2


def test_invalid_audit_does_not_publish_the_unchecked_draft():
    n = 0
    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            return search_result()
        n += 1
        if n == 1:
            return completion(None, [call()])
        return completion("未经核对的猜测 [W1]" if n == 2 else '{"corrections": [42]}')
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        result = events(client, session_id)
        assert any(e.get("error", {}).get("code") == "model_invalid_review" for e in result)
        assert result[-1]["message"]["status"] == "incomplete"
        assert result[-1]["metrics"]["review_calls"] == 4 and n == 6
        assert "未经核对的猜测" not in json.dumps(result, ensure_ascii=False)


def test_invalid_audit_can_retry_and_edit_within_the_same_review_budget():
    n = 0
    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            return search_result()
        n += 1
        if n == 1:
            return completion(None, [call()])
        if n == 2:
            return completion("保证当天办好 [W1]")
        if n == 3:
            return completion("错误格式的核对输出，不应进入历史")
        body = json.loads(request.content)
        assert "tools" not in body
        assert "错误格式的核对输出" not in json.dumps(body, ensure_ascii=False)
        payload = json.loads(body["messages"][-1]["content"])
        assert payload["audit_format_error"]
        if n == 4:
            return completion('{"corrections": ["资料未说明办结时限，删去当天承诺。"]}')
        if n == 6:
            return completion('{"corrections": []}')
        return completion("已查资料未说明办结时限 [W1]。")
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        final = events(client, session_id)[-1]
        assert final["message"]["status"] == "complete" and n == 6
        assert final["metrics"]["review_calls"] == 4
        assert final["metrics"]["review_format_retries"] == 1
        assert "保证当天" not in final["message"]["content"]


def test_audit_can_recover_a_skipped_lookup_without_question_specific_routing():
    n = 0
    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            return search_result()
        n += 1
        if n == 1:
            return completion("你要查哪个名称？")
        body = json.loads(request.content)
        if n == 2:
            payload = json.loads(body["messages"][-1]["content"])
            assert not payload["evidence"] and not payload["current_tool_actions"]
            assert "tools" in body
            return completion(None, [call()])
        if n == 3:
            return completion("官网窗口说明 [W1]")
        payload = json.loads(body["messages"][-1]["content"])
        assert payload["current_tool_actions"] == [{"tool": "search_web", "status": "complete"}]
        return completion('{"corrections": []}')
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        final = events(client, session_id, "请查官网窗口名称并引用")[-1]
        assert n == 4 and final["tool_calls"] == 1
        assert final["message"]["content"] == "官网窗口说明 [W1]"
        assert final["message"]["status"] == "complete"


def test_audit_of_simple_chat_does_not_require_retrieval():
    n = 0
    def handler(request):
        nonlocal n
        n += 1
        return completion("你好。" if n == 1 else '{"corrections": []}')
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        final = events(client, session_id, "你好")[-1]
        assert final["message"]["content"] == "你好。" and final["message"]["status"] == "complete"
        assert n == 2 and final["tool_calls"] == 0


def test_final_audit_can_repair_a_new_unsupported_claim_introduced_by_editing():
    n = 0
    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            return search_result()
        n += 1
        if n == 1:
            return completion(None, [call()])
        if n == 2:
            return completion("官网说明到江湾窗口 [W1]。" * 10)
        if n == 3:
            return completion('{"corrections": ["精简答案，资料未提及其他校区。"]}')
        if n == 4:
            return completion("其他校区禁止办理 [W1]。")
        if n == 6:
            return completion("资料未说明其他校区的适用情况 [W1]。")
        body = json.loads(request.content)
        assert "tools" not in body
        assert json.loads(body["messages"][-1]["content"])["draft"] == "其他校区禁止办理 [W1]。"
        return completion('{"corrections": ["资料未说明其他校区，不支持禁止办理。"]}')
    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        session_id = client.post("/api/sessions").json()["session_id"]
        final = events(client, session_id)[-1]
        assert n == 6 and final["metrics"]["review_calls"] == 4
        assert final["message"]["status"] == "complete"
        assert final["message"]["content"] == "资料未说明其他校区的适用情况 [W1]。"
        assert "其他校区禁止办理" not in json.dumps(client.app.state.sessions[session_id].history, ensure_ascii=False)


def test_review_correction_cannot_extend_total_deadline_or_commit_partial_turn():
    async def run():
        n = 0
        cancelled = []
        async def handler(request):
            nonlocal n
            n += 1
            if n == 1:
                return completion("无关长文。" * 30)
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)
        cfg = config(request_budget_seconds=.1)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = Agent(cfg, ModelService(cfg, client), SearchService(cfg, client))
            session = Session(busy=True)
            final = [e async for e in agent.events(session, "最多30字回答你的用途")][-1]
            assert cancelled and not session.busy
            assert len(final["message"]["content"]) <= 30
            assert final["message"]["status"] == "incomplete"
            assert "无关长文" not in json.dumps(session.history, ensure_ascii=False)
    asyncio.run(run())
