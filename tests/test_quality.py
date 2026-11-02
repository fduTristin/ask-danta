import asyncio
import json
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import Agent, Session
from app.config import Settings
from app.main import create_app
from app.model import ModelService
from app.reader import PageReader, public_address
from app.search import SearchError, SearchService
from test_chat import call, completion, events, search_result


@pytest.fixture(autouse=True)
def clean_config(monkeypatch, tmp_path):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    monkeypatch.setenv("CAMPUS_AUTH_FILE", str(tmp_path / "absent-tokens.json"))


def config(**kwargs):
    return Settings(_env_file=None, model_api_key="test-key", search_provider="tavily", search_api_key="search-key", **kwargs)


def test_review_can_correct_draft_and_sources_are_only_citations():
    requests = []

    def handler(request):
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": [
                {"title": "指南", "url": "https://example.org/a", "content": "材料齐全后3个工作日。"},
                {"title": "导航", "url": "https://example.org/b", "content": "首页导航，无办理时间。"},
            ]})
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return completion(None, [call()])
        if len(requests) == 2:
            return completion("保证24小时 [W2]")
        if len(requests) == 5:
            assert json.loads(body["messages"][-1]["content"])["draft"] == "材料齐全后3个工作日 [W1]"
            assert "tools" not in body
            return completion('{"corrections": []}')
        assert "保证24小时" in body["messages"][-1]["content"]
        assert "发布前核对" in body["messages"][0]["content"]
        assert json.loads(body["messages"][-1]["content"])["evidence"][0]["id"] == "W1"
        if len(requests) == 3:
            return completion(json.dumps({"corrections": ["24小时承诺无依据，改用材料齐全后3个工作日并引用W1。"]}))
        return completion("材料齐全后3个工作日 [W1]")

    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert any(event["type"] == "review_start" for event in result)
        assert "保证24小时" not in json.dumps(result, ensure_ascii=False)
        assert [s["id"] for s in result[-1]["message"]["sources"]] == ["W1"]
        assert len(result[-1]["session_sources"]) == 2
        assert result[-1]["metrics"]["model_calls"] == 5
        assert "保证24小时" not in json.dumps(client.app.state.sessions[id].history, ensure_ascii=False)


def test_review_can_request_additional_search_within_same_budget():
    n = 0

    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            return search_result()
        n += 1
        if n in (1, 3):
            return completion(None, [call(str(n), arguments=json.dumps({"query": "初查" if n == 1 else "补查"}))])
        if n == 4:
            assert "核对触发补查后的回答" in json.loads(request.content)["messages"][-1]["content"]
            return completion("补查后仍猜测24小时办结 [W1]")
        if n == 5:
            body = json.loads(request.content)
            assert "补查后仍猜测24小时" in body["messages"][-1]["content"]
            assert "tools" in body
            return completion(json.dumps({"corrections": ["删去无依据的24小时断言。"]}))
        if n == 7:
            return completion('{"corrections": []}')
        return completion("窗口 [W1]")

    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert n == 7 and result[-1]["tool_calls"] == 2
        assert result[-1]["message"]["status"] == "complete"
        assert sum(e["type"] == "review_start" for e in result) == 4
        assert "24小时" not in result[-1]["message"]["content"]


def test_repeated_query_does_not_call_upstream_twice():
    model_calls, search_calls = 0, 0

    def handler(request):
        nonlocal model_calls, search_calls
        if request.url.host == "api.tavily.com":
            search_calls += 1
            return search_result()
        model_calls += 1
        if model_calls <= 2:
            return completion(None, [call(str(model_calls))])
        if model_calls == 4:
            return completion('{"corrections": []}')
        return completion("请去窗口 [W1]")

    with TestClient(create_app(config(), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert search_calls == 1
        assert any(e.get("error", {}).get("code") == "duplicate_tool_call" for e in result)


def test_unknown_citation_is_not_published_after_review():
    with TestClient(create_app(config(), httpx.MockTransport(lambda r: completion("虚构结论 [W99]")))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert "虚构结论" not in result[-1]["message"]["content"]
        assert result[-1]["message"]["status"] == "incomplete"
        assert result[-1]["message"]["sources"] == []


def test_thinking_protocol_usage_and_independent_timeouts():
    n = 0

    def handler(request):
        nonlocal n
        if request.url.host == "api.tavily.com":
            assert request.extensions["timeout"]["read"] == 2
            return search_result()
        n += 1
        body = json.loads(request.content)
        assert body["thinking"]["type"] == "enabled"
        assert body["max_tokens"] == 6000
        assert body["reasoning_effort"] == "low"
        assert request.extensions["timeout"]["read"] == 35
        response = completion(None, [call()]) if n == 1 else completion("窗口 [W1]" if n == 2 else '{"corrections": []}')
        payload = json.loads(response.content)
        if n == 1:
            payload["choices"][0]["message"]["reasoning_content"] = "private-model-reasoning"
        elif n == 2:
            assert any(m.get("reasoning_content") == "private-model-reasoning" for m in body["messages"])
        else:
            # Independent evidence review does not reuse model reasoning.
            assert "private-model-reasoning" not in json.dumps(body)
        payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        return httpx.Response(200, json=payload)

    with TestClient(create_app(config(model_thinking="enabled", model_max_tokens=6000,
        model_timeout_seconds=35, search_timeout_seconds=2), httpx.MockTransport(handler))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert result[-1]["metrics"]["total_tokens"] == 45
        assert "private-model-reasoning" not in json.dumps(result)
        assert "private-model-reasoning" not in client.get(f"/api/sessions/{id}").text


def test_read_web_requires_existing_source_id():
    with TestClient(create_app(config(max_tool_calls=1), httpx.MockTransport(
        lambda r: completion(None, [call(name="read_web", arguments='{"source_id":"W99"}')])
        if "tools" in json.loads(r.content) else completion("没有该来源。")))) as client:
        id = client.post("/api/sessions").json()["session_id"]
        result = events(client, id)
        assert any(e.get("error", {}).get("code") == "unknown_source" for e in result)


SOURCE = {"id": "W1", "url": "https://example.org/page", "title": "测试网页", "is_mock": False}


def dns_records(addresses):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]
    return resolve


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.1.1.1"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "192.168.1.1"], ["::ffff:8.8.8.8"]])
def test_reader_rejects_nonpublic_and_mixed_dns(addresses, monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_records(addresses))
        with pytest.raises(SearchError, match="不允许访问"):
            await public_address(httpx.URL(SOURCE["url"]))
    asyncio.run(run())


@pytest.mark.parametrize("url", ["http://user:pass@example.org", "http://example.org:8000", "file:///etc/passwd"])
def test_reader_rejects_url_credentials_ports_schemes(url):
    with pytest.raises(SearchError):
        asyncio.run(public_address(httpx.URL(url)))


def test_reader_pins_validated_ip_and_rechecks_redirect(monkeypatch):
    async def run():
        lookups = []
        requests = []

        async def dns(host, *args, **kwargs):
            lookups.append(host)
            return await dns_records(["127.0.0.1"] if host == "localhost" else ["8.8.8.8"] )()

        def handler(request):
            requests.append(request)
            assert request.url.host == "8.8.8.8"
            assert request.headers["host"] == "example.org"
            assert request.extensions["sni_hostname"] == "example.org"
            return httpx.Response(302, headers={"location": "http://localhost/private"})

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
        with pytest.raises(SearchError, match="不允许访问"):
            await PageReader(config(), httpx.MockTransport(handler)).read(SOURCE)
        assert len(requests) == 1 and lookups == ["example.org", "localhost"]
    asyncio.run(run())


def test_reader_extracts_bounds_and_closes_stream(monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_records(["8.8.8.8"]))
        closed = False

        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"<html><script>ignore me</script><p>" + b"x" * 1_000_010

            async def aclose(self):
                nonlocal closed
                closed = True

        reader = PageReader(config(), httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, stream=Body())))
        result = await reader.read(SOURCE)
        assert result["truncated"] and len(result["text"]) == 12000
        assert "ignore me" not in result["text"] and closed
    asyncio.run(run())


def test_reader_invalid_redirect_returns_sanitized_error(monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_records(["8.8.8.8"]))
        reader = PageReader(config(), httpx.MockTransport(lambda r: httpx.Response(
            302, headers={"location": "http://example.org:invalid/private-token"})))
        with pytest.raises(SearchError) as error:
            await reader.read(SOURCE)
        assert error.value.code == "page_unreachable"
        assert "private-token" not in error.value.message
    asyncio.run(run())


def test_cancel_during_review_discards_entire_turn():
    async def run():
        reviewing = asyncio.Event()
        cancelled = asyncio.Event()
        n = 0

        async def handler(request):
            nonlocal n
            if request.url.host == "api.tavily.com":
                return search_result()
            n += 1
            if n == 1:
                return completion(None, [call()])
            if n == 2:
                return completion("窗口 [W1]")
            reviewing.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

        cfg = config()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = Agent(cfg, ModelService(cfg, client), SearchService(cfg, client))
            session = Session(busy=True)

            async def consume():
                return [e async for e in agent.events(session, "查窗口")]

            task = asyncio.create_task(consume())
            await reviewing.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set() and not session.busy
            assert session.history == session.sources == session.messages == []
    asyncio.run(run())
