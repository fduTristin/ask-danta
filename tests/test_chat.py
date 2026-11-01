import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import Agent, Session
from app.config import Settings
from app.main import create_app
from app.model import ModelService
from app.search import SearchService


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def settings(**kwargs):
    return Settings(_env_file=None, model_api_key="model-secret", search_provider="tavily", search_api_key="search-secret", **kwargs)


def completion(content="回答", calls=None):
    return httpx.Response(200, json={"choices": [{
        "finish_reason": "tool_calls" if calls else "stop",
        "message": {"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})},
    }]})


def call(id="call-1", name="search_web", arguments='{"query":"官方通知"}'):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


def search_result():
    return httpx.Response(200, json={"results": [{"title": "官方通知", "url": "https://example.org/notice", "content": "请到江湾窗口办理。"}]})


def events(client, session_id, message="请查找官方通知，我在江湾校区"):
    response = client.post(f"/api/sessions/{session_id}/chat", json={"message": message})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(frame[6:]) for frame in response.text.strip().split("\n\n")]


def test_tool_roundtrip_followup_clear_and_isolation():
    requests = []

    def handler(request):
        if request.url.host == "api.tavily.com":
            return search_result()
        body = json.loads(request.content)
        requests.append(body)
        assert body["thinking"] == {"type": "disabled"}
        assert "model-secret" not in json.dumps(body)
        if len(requests) == 1:
            return completion(None, [call()])
        if len(requests) == 2:
            tool = body["messages"][-1]
            assert tool["role"] == "tool" and tool["tool_call_id"] == "call-1"
            assert json.loads(tool["content"])["results"][0]["id"] == "W1"
        return completion("江湾窗口 [W1]")

    with TestClient(create_app(settings(), httpx.MockTransport(handler))) as client:
        first = client.post("/api/sessions").json()["session_id"]
        result = events(client, first)
        assert [e["type"] for e in result] == ["start", "model_start", "tool_start", "tool_complete", "model_start", "final"]
        assert result[-1]["message"]["sources"][0]["published_at"] is None
        events(client, first, "沿用上面的校区，简短说明")
        assert "江湾校区" in requests[-1]["messages"][1]["content"]
        assert any(m["role"] == "tool" for m in requests[-1]["messages"])
        other = client.post("/api/sessions").json()["session_id"]
        events(client, other, "你好")
        assert len(requests[-1]["messages"]) == 2
        assert client.get(f"/api/sessions/{first}").json()["sources"]
        cleared = client.post(f"/api/sessions/{first}/clear").json()
        assert cleared["messages"] == cleared["sources"] == []
        events(client, first, "新问题")
        assert len(requests[-1]["messages"]) == 2
        assert client.delete(f"/api/sessions/{other}").status_code == 204
        assert client.get(f"/api/sessions/{other}").status_code == 404


@pytest.mark.parametrize("name,arguments,code", [
    ("read_url", '{"url":"http://localhost"}', "unknown_tool"),
    ("search_web", "not json", "invalid_tool_arguments"),
    ("search_web", '{"query":" "}', "invalid_tool_arguments"),
    ("search_web", '{"query":"test","url":"http://localhost"}', "invalid_tool_arguments"),
])
def test_invalid_tools_rejected_and_budget_ends_loop(name, arguments, code):
    attempts = []

    def handler(request):
        assert request.url.host != "api.tavily.com"
        body = json.loads(request.content)
        attempts.append(body)
        if len(attempts) == 1:
            return completion(None, [call(name=name, arguments=arguments)])
        assert "tools" not in body
        assert json.loads(body["messages"][-2]["content"])["error"]["code"] == code
        return completion("资料不足。")

    with TestClient(create_app(settings(max_tool_calls=1), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert any(e["type"] == "tool_error" for e in result)
        assert result[-1]["message"]["limited"] is True
        assert "预算" in result[-1]["message"]["content"]
        assert len(attempts) == 2


def test_multi_call_budget_pairs_all_ids_and_limits_actual_searches():
    searches = []
    model_calls = []

    def handler(request):
        if request.url.host == "api.tavily.com":
            searches.append(request)
            return search_result()
        body = json.loads(request.content)
        model_calls.append(body)
        if len(model_calls) == 1:
            return completion(None, [call("a"), call("b"), call("c")])
        assert [m["tool_call_id"] for m in body["messages"] if m["role"] == "tool"] == ["a", "b", "c"]
        return completion("已查到部分信息 [W1]")

    with TestClient(create_app(settings(max_tool_calls=1), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert len(searches) == 1
        assert len(result[-1]["message"]["sources"]) == 1
        assert sum(e["type"] == "tool_error" for e in result) == 2


@pytest.mark.parametrize("status,code", [(401, "model_auth_failed"), (429, "model_rate_limited"), (500, "model_upstream_error")])
def test_model_errors_are_sanitized_and_session_reusable(status, code):
    with TestClient(create_app(settings(), httpx.MockTransport(lambda request: httpx.Response(status, text="model-secret private body")))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert result[-2]["error"]["code"] == code
        assert "model-secret" not in json.dumps(result)
        assert "private body" not in json.dumps(result)
        assert client.get(f"/api/sessions/{id}").json()["busy"] is False
        assert client.post(f"/api/sessions/{id}/clear").status_code == 200


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{"finish_reason": "length", "message": {"role": "assistant", "content": "截断"}}]}, {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": ""}}]}])
def test_invalid_model_response(payload):
    with TestClient(create_app(settings(), httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert result[-2]["error"]["code"] == "model_invalid_response"
        assert result[-1]["type"] == "final"


def test_timeout_preserves_acquired_sources():
    count = 0

    def handler(request):
        nonlocal count
        if request.url.host == "api.tavily.com":
            return search_result()
        count += 1
        if count == 1:
            return completion(None, [call()])
        raise httpx.ReadTimeout("model-secret", request=request)

    with TestClient(create_app(settings(), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert result[-2]["error"]["code"] == "model_timeout"
        assert "江湾窗口" in result[-1]["message"]["content"]
        assert "尚未完成综合核对" in result[-1]["message"]["content"]


def test_search_failure_is_returned_to_model_not_hidden():
    count = 0

    def handler(request):
        nonlocal count
        if request.url.host == "api.tavily.com":
            return httpx.Response(401, text="search-secret")
        count += 1
        if count == 1:
            return completion(None, [call()])
        body = json.loads(request.content)
        assert json.loads(body["messages"][-1]["content"])["error"]["code"] == "search_auth_failed"
        return completion("搜索认证失败，无法核实。")

    with TestClient(create_app(settings(), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert any(e["type"] == "tool_error" for e in result)
        assert result[-1]["message"]["sources"] == []


def test_missing_key_input_validation_and_busy_session():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        for message in ["", " ", None, 123, "a" * 8001]:
            assert client.post(f"/api/sessions/{id}/chat", json={"message": message}).status_code == 422
        assert client.post(f"/api/sessions/{id}/chat", json={"message": "hi"}).status_code == 503
        session = client.app.state.sessions[id]
        session.busy = True
        for path in ["chat", "clear"]:
            assert client.post(f"/api/sessions/{id}/{path}", json={"message": "hi"}).status_code == 409
        assert client.delete(f"/api/sessions/{id}").status_code == 409


def test_total_deadline_and_cancellation_cleanup():
    async def run():
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def handler(request):
            started.set()
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.set()
            return completion()

        config = settings(request_budget_seconds=.03)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = Agent(config, ModelService(config, client), SearchService(config, client))
            session = Session(busy=True)
            result = [event async for event in agent.events(session, "测试")]
            assert result[-2]["error"]["code"] == "request_budget_exhausted"
            assert not session.busy and cancelled.is_set()
            started.clear(); cancelled.clear()
            session = Session(busy=True)
            stream = agent.events(session, "不要保留")

            async def consume():
                return [event async for event in stream]

            task = asyncio.create_task(consume())
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set() and not session.busy
            assert session.history == session.messages == session.sources == []

    asyncio.run(run())


def test_slow_search_stops_before_reserved_answer_time():
    async def run():
        count = 0
        search_cancelled = False

        async def handler(request):
            nonlocal count, search_cancelled
            if request.url.host == "api.tavily.com":
                try:
                    await asyncio.sleep(1)
                finally:
                    search_cancelled = True
                return search_result()
            count += 1
            body = json.loads(request.content)
            if count == 1:
                return completion(None, [call()])
            assert "tools" not in body
            assert json.loads(body["messages"][-2]["content"])["error"]["code"] == "tool_budget_exhausted"
            return completion("未能及时获取资料。")

        config = settings(request_budget_seconds=.15)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = Agent(config, ModelService(config, client), SearchService(config, client))
            result = [event async for event in agent.events(Session(busy=True), "查询")]
            assert search_cancelled
            assert result[-1]["type"] == "final"
            assert result[-1]["message"]["limited"]
            assert result[-1]["message"]["content"].startswith("未能及时获取资料。")

    asyncio.run(run())


def test_mock_sources_remain_labelled_in_tool_context_and_final():
    count = 0

    def handler(request):
        nonlocal count
        assert request.url.host == "api.deepseek.com"
        count += 1
        if count == 1:
            return completion(None, [call()])
        tool = json.loads(json.loads(request.content)["messages"][-1]["content"])
        assert tool["is_mock"] and tool["results"][0]["is_mock"]
        return completion("这是合成样例，无法核实。")

    config = Settings(_env_file=None, model_api_key="model-secret", search_provider="mock")
    with TestClient(create_app(config, httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)[-1]
        assert result["session_sources"][0]["is_mock"]
        assert result["message"]["sources"] == []
