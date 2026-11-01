"""Synthetic FDUHole contracts only: no local credentials or external requests."""

import asyncio
import json
import os
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from app.campus import AUTH_BASE, CampusBudget, CampusService
from app.campus_auth import CampusError, Tokens, TokenStore
from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def settings(tmp_path, **kwargs):
    return Settings(_env_file=None, campus_auth_file=tmp_path / "tokens.json", **kwargs)


def seed(config, access="old-access", refresh="old-refresh"):
    # Synthetic tokens only. Real owner-only persistence is tested separately.
    config.auth_path.write_text(json.dumps({"access": access, "refresh": refresh}), encoding="utf-8")


def floor(id=1, hole_id=12, **kwargs):
    return {"id": id, "hole_id": hole_id, "content": "合成帖子", "time_created": "2026-11-01T09:00:00+08:00", **kwargs}


def run_service(config, handler, action):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await action(CampusService(config, client))
    return asyncio.run(run())


def test_login_persists_only_tokens_with_owner_permissions(tmp_path):
    config = settings(tmp_path)
    def handler(request):
        assert str(request.url) == AUTH_BASE + "/login"
        assert json.loads(request.content) == {"email": "synthetic@example.invalid", "password": "synthetic-password"}
        return httpx.Response(200, json={"access": "new-access", "refresh": "new-refresh", "email": "private"})
    run_service(config, handler, lambda service: service.login("synthetic@example.invalid", "synthetic-password"))
    assert json.loads(config.auth_path.read_text()) == {"access": "new-access", "refresh": "new-refresh"}
    assert "new-access" not in repr(TokenStore(config.auth_path).load())
    if os.name == "nt":
        output = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$a = [System.IO.File]::GetAccessControl($env:CAMPUS_TEST_PATH); "
            "[bool]($a.AreAccessRulesProtected -and @($a.Access).Count -eq 1 -and "
            "$a.Access[0].IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]) -eq "
            "[System.Security.Principal.WindowsIdentity]::GetCurrent().User)"],
            env={**os.environ, "CAMPUS_TEST_PATH": str(config.auth_path)}, capture_output=True, text=True, check=True)
        assert output.stdout.strip() == "True"
    else:
        assert config.auth_path.stat().st_mode & 0o777 == 0o600


def test_search_encoding_projection_truncation_and_pagination(tmp_path):
    config = settings(tmp_path, campus_max_content_chars=100)
    seed(config)
    query = "图书馆 & offset=999 + # ? 中文"
    def handler(request):
        assert request.url.host == "forum.fduhole.com"
        assert request.url.params["search"] == query
        assert request.url.params["size"] == "3"
        offset = int(request.url.params["offset"])
        item = floor(content="synthetic@example.invalid 13800138000 " + "文" * 150,
                     user_id=999, anonyname="private-name", mention=[{"content": "private-mention"}])
        return httpx.Response(200, json=[item, item, floor(2)] if offset == 0 else [floor(2), floor(3)])
    async def action(service):
        budget = CampusBudget(3)
        first = await service.search_campus_posts(query, limit=3, budget=budget)
        second = await service.search_campus_posts(query, offset=first.next_offset, limit=3, budget=budget)
        assert [item.floor_id for item in first.results] == [1, 2]
        assert [item.floor_id for item in second.results] == [3]
        assert first.raw_count == 3 and first.next_offset == 3
        assert second.next_offset is None and second.has_more is None and not second.complete
        assert first.results[0].truncated and first.results[0].redacted
        assert len(first.results[0].content) == 100
        for private in ("user_id", "private-name", "private-mention", "13800138000", "synthetic@example.invalid"):
            assert private not in first.model_dump_json()
    run_service(config, handler, action)


def test_thread_metadata_floors_and_deleted_filter(tmp_path):
    config = settings(tmp_path)
    seed(config)
    def handler(request):
        if request.url.path == "/api/holes/12":
            return httpx.Response(200, json={"id": 12, "time_created": "2026-11-01T00:00:00Z", "reply": 4, "user_id": "secret"})
        assert request.url.path == "/api/holes/12/floors"
        assert dict(request.url.params) == {"offset": "20", "size": "20"}
        return httpx.Response(200, json=[floor(), floor(2, deleted=True)])
    result = run_service(config, handler, lambda service: service.read_campus_thread(12, offset=20))
    assert result.thread.id == 12 and result.thread.reply == 4
    assert len(result.results) == 1 and result.raw_count == 2
    assert "secret" not in result.model_dump_json()


def test_empty_is_success_but_not_proof_of_exhaustion(tmp_path):
    config = settings(tmp_path)
    seed(config)
    page = run_service(config, lambda r: httpx.Response(200, json=[]), lambda s: s.search_campus_posts("合成"))
    assert page.results == [] and page.has_more is None and not page.complete


@pytest.mark.parametrize("payload", [{}, {"data": []}, [floor(id="1")], [floor(time_created="yesterday")], [floor(content=None)]])
def test_schema_drift_is_not_empty_results(tmp_path, payload):
    config = settings(tmp_path)
    seed(config)
    with pytest.raises(CampusError) as exc:
        run_service(config, lambda r: httpx.Response(200, json=payload), lambda s: s.search_campus_posts("合成"))
    assert exc.value.code == "campus_invalid_response"


@pytest.mark.parametrize("status,code,count", [(403, "campus_forbidden", 1), (404, "campus_not_found", 1),
    (429, "campus_rate_limited", 2), (503, "campus_upstream_error", 2), (500, "campus_upstream_error", 1),
    (302, "campus_upstream_error", 1)])
def test_http_errors_redaction_and_bounded_retries(tmp_path, status, code, count, monkeypatch):
    config = settings(tmp_path)
    seed(config)
    calls = []
    async def no_sleep(_):
        pass
    monkeypatch.setattr("app.campus.asyncio.sleep", no_sleep)
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private-body old-access", headers={"Location": "https://example.invalid"})
    with TestClient(create_app(config, httpx.MockTransport(handler))) as client:
        response = client.post("/api/campus/search", json={"query": "合成"})
        assert response.json()["error"]["code"] == code
        assert "private-body" not in response.text and "old-access" not in response.text
    assert len(calls) == count


@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout, "campus_timeout"), (httpx.ConnectError, "campus_unreachable")])
def test_network_errors(tmp_path, exception, code, monkeypatch):
    config = settings(tmp_path)
    seed(config)
    calls = 0
    async def no_sleep(_):
        pass
    monkeypatch.setattr("app.campus.asyncio.sleep", no_sleep)
    def handler(request):
        nonlocal calls
        calls += 1
        raise exception("old-access private-body", request=request)
    with pytest.raises(CampusError) as exc:
        run_service(config, handler, lambda s: s.search_campus_posts("合成"))
    assert exc.value.code == code and "old-access" not in str(exc.value)
    assert calls == 2


def test_concurrent_401_refreshes_once_and_persists_pair(tmp_path):
    config = settings(tmp_path)
    seed(config)
    refreshes = 0
    old_requests = 0
    async def action(service):
        nonlocal refreshes, old_requests
        both_started = asyncio.Event()
        async def handler(request):
            nonlocal refreshes, old_requests
            if request.url.path == "/api/refresh":
                refreshes += 1
                assert request.headers["Authorization"] == "Bearer old-refresh"
                return httpx.Response(200, json={"access": "new-access", "refresh": "new-refresh"})
            if request.headers["Authorization"] == "Bearer old-access":
                old_requests += 1
                if old_requests == 2:
                    both_started.set()
                await both_started.wait()
                return httpx.Response(401)
            assert request.headers["Authorization"] == "Bearer new-access"
            return httpx.Response(200, json=[floor()])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service.client = client
            pages = await asyncio.gather(service.search_campus_posts("one"), service.search_campus_posts("two"))
        assert all(len(page.results) == 1 for page in pages)
    run_service(config, lambda r: pytest.fail("unexpected network"), action)
    assert refreshes == 1 and old_requests == 2
    assert TokenStore(config.auth_path).load().refresh.get_secret_value() == "new-refresh"


@pytest.mark.parametrize("refresh_status", [401, 403])
def test_failed_refresh_requires_relogin_without_refresh_storm(tmp_path, refresh_status):
    config = settings(tmp_path)
    seed(config)
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(refresh_status if request.method == "POST" else 401, text="private")
    async def action(service):
        for _ in range(2):
            with pytest.raises(CampusError, match="登录") as exc:
                await service.search_campus_posts("合成")
            assert exc.value.code == "campus_auth_failed"
        seed(config, access="relogged-access", refresh="relogged-refresh")
        with pytest.raises(CampusError):
            await service.search_campus_posts("合成")
    run_service(config, handler, action)
    assert paths.count("/api/refresh") == 2  # one per login, not per failed request


def test_second_401_never_refreshes_again(tmp_path):
    config = settings(tmp_path)
    seed(config)
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"access": "new-access", "refresh": "new-refresh"}) if request.method == "POST" else httpx.Response(401)
    with pytest.raises(CampusError) as exc:
        run_service(config, handler, lambda s: s.search_campus_posts("合成"))
    assert exc.value.code == "campus_auth_failed"
    assert paths == ["/api/floors/search", "/api/refresh", "/api/floors/search"]


@pytest.mark.parametrize("body", [{"query": " "}, {"query": "x", "offset": -1}, {"query": "x", "limit": 51},
    {"query": "x", "limit": True}, {"query": "x", "offset": "1"}, {"query": "x", "url": "https://example.invalid"}])
def test_invalid_api_input_never_requests_upstream(tmp_path, body):
    with TestClient(create_app(settings(tmp_path), httpx.MockTransport(lambda r: pytest.fail("network")))) as client:
        assert client.post("/api/campus/search", json=body).status_code == 422
        assert client.post("/api/campus/thread", json={"hole_id": "../users"}).status_code == 422


def test_missing_and_malformed_credentials(tmp_path):
    config = settings(tmp_path)
    with TestClient(create_app(config, httpx.MockTransport(lambda r: pytest.fail("network")))) as client:
        assert client.post("/api/campus/search", json={"query": "x"}).json()["error"]["code"] == "campus_login_required"
        config.auth_path.write_text('{"access":"private", "refresh":""}')
        response = client.post("/api/campus/search", json={"query": "x"})
        assert response.json()["error"]["code"] == "campus_credentials_invalid"
        assert "private" not in response.text


def test_page_budget_shared_across_search_and_read(tmp_path):
    config = settings(tmp_path)
    seed(config)
    async def action(service):
        budget = CampusBudget(1)
        await service.search_campus_posts("合成", budget=budget)
        with pytest.raises(CampusError) as exc:
            await service.read_campus_thread(12, budget=budget)
        assert exc.value.code == "campus_page_budget_exhausted"
    run_service(config, lambda r: httpx.Response(200, json=[]), action)


def test_fixed_endpoint_guard_and_no_redirects(tmp_path):
    async def action(service):
        for method, url in [("GET", "https://example.invalid"), ("POST", "https://forum.fduhole.com/api/holes/1/floors")]:
            with pytest.raises(CampusError) as exc:
                await service._request(method, url)
            assert exc.value.code == "campus_endpoint_forbidden"
    run_service(settings(tmp_path), lambda r: pytest.fail("network"), action)


def test_atomic_write_failure_preserves_old_credentials(tmp_path, monkeypatch):
    config = settings(tmp_path)
    seed(config)
    def fail(_):
        raise OSError("private path")
    monkeypatch.setattr("app.campus_auth.restrict_file", fail)
    with pytest.raises(CampusError) as exc:
        TokenStore(config.auth_path).save(Tokens(access="new", refresh="new"))
    assert exc.value.code == "campus_credentials_write_failed"
    assert TokenStore(config.auth_path).load().access.get_secret_value() == "old-access"
    assert list(tmp_path.glob(".campus-*.tmp")) == []


def test_search_then_read_keeps_context_with_shared_budget(tmp_path):
    config = settings(tmp_path)
    seed(config)
    def handler(request):
        if request.url.path == "/api/holes/12":
            return httpx.Response(200, json={"id": 12, "time_created": "2026-11-01T00:00:00Z"})
        return httpx.Response(200, json=[floor()])
    async def action(service):
        budget = CampusBudget(3)
        search = await service.search_campus_posts("合成", budget=budget)
        thread = await service.read_campus_thread(12, budget=budget)
        assert search.results[0].floor_id == thread.results[0].floor_id
        assert budget.pages == 2
    run_service(config, handler, action)


@pytest.mark.parametrize("payload", [[floor(), floor(2)], [floor(hole_id=99)]])
def test_thread_rejects_oversized_or_mismatched_pages(tmp_path, payload):
    config = settings(tmp_path)
    seed(config)
    def handler(request):
        if request.url.path == "/api/holes/12":
            return httpx.Response(200, json={"id": 12, "time_created": "2026-11-01T00:00:00Z"})
        return httpx.Response(200, json=payload)
    with pytest.raises(CampusError) as exc:
        run_service(config, handler, lambda s: s.read_campus_thread(12, limit=1))
    assert exc.value.code == "campus_invalid_response"


def test_retry_after_long_delay_is_not_retried(tmp_path):
    config = settings(tmp_path)
    seed(config)
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "60"})
    with pytest.raises(CampusError) as exc:
        run_service(config, handler, lambda s: s.search_campus_posts("合成"))
    assert exc.value.code == "campus_rate_limited" and calls == 1


def test_transient_get_can_recover_once(tmp_path, monkeypatch):
    config = settings(tmp_path)
    seed(config)
    calls = 0
    async def no_sleep(_):
        pass
    monkeypatch.setattr("app.campus.asyncio.sleep", no_sleep)
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls == 1 else httpx.Response(200, json=[floor()])
    page = run_service(config, handler, lambda s: s.search_campus_posts("合成"))
    assert len(page.results) == 1 and calls == 2


def test_api_deadline_cancels_upstream(tmp_path):
    config = settings(tmp_path, request_budget_seconds=0.02)
    seed(config)
    cancelled = []
    async def handler(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    with TestClient(create_app(config, httpx.MockTransport(handler))) as client:
        response = client.post("/api/campus/search", json={"query": "合成"})
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "campus_request_budget_exhausted"
    assert cancelled == [True]


def test_refresh_cancellation_releases_lock(tmp_path):
    config = settings(tmp_path)
    seed(config)
    async def action(service):
        refreshing = asyncio.Event()
        async def handler(request):
            if request.method == "POST":
                refreshing.set()
                await asyncio.sleep(10)
            return httpx.Response(401)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service.client = client
            pending = asyncio.create_task(service.search_campus_posts("合成"))
            await refreshing.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert not service._refresh_lock.locked()
            assert TokenStore(config.auth_path).load().access.get_secret_value() == "old-access"
    run_service(config, lambda r: pytest.fail("network"), action)


def test_invalid_json_and_auth_response_are_sanitized(tmp_path):
    config = settings(tmp_path)
    seed(config)
    with pytest.raises(CampusError) as exc:
        run_service(config, lambda r: httpx.Response(200, text="private-body"), lambda s: s.search_campus_posts("合成"))
    assert exc.value.code == "campus_invalid_response" and "private-body" not in str(exc.value)
    with pytest.raises(CampusError) as exc:
        run_service(config, lambda r: httpx.Response(200, json={"access": "secret"}), lambda s: s.login("test", "test"))
    assert exc.value.code == "campus_invalid_response" and "secret" not in str(exc.value)
    assert TokenStore(config.auth_path).load().access.get_secret_value() == "old-access"


def test_web_login_saves_tokens_without_exposing_secrets_or_chat_history(tmp_path):
    config = settings(tmp_path)
    def handler(request):
        assert request.url == AUTH_BASE + "/login"
        assert json.loads(request.content) == {"email": "synthetic@example.invalid", "password": " password-with-spaces "}
        return httpx.Response(200, json={"access": "synthetic-access", "refresh": "synthetic-refresh"})
    with TestClient(create_app(config, httpx.MockTransport(handler))) as client:
        session = client.post("/api/sessions").json()["session_id"]
        response = client.post("/api/campus/login", json={"email": " synthetic@example.invalid ", "password": " password-with-spaces "})
        assert response.status_code == 200 and response.json()["authenticated"] is True
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/api/health").json()["campus"]["credentials_present"] is True
        assert client.get(f"/api/sessions/{session}").json()["messages"] == []
        for secret in ("synthetic-access", "synthetic-refresh", "password-with-spaces", "synthetic@example.invalid"):
            assert secret not in response.text
        assert "password" not in config.auth_path.read_text()


@pytest.mark.parametrize("body", [
    {"email": "private-email", "password": "private-password"},
    {"email": "synthetic@example.invalid", "password": ""},
    {"email": "synthetic@example.invalid", "password": "private-password", "extra": "private-value"},
    {"email": "synthetic@example.invalid", "password": {"private-password": "bad-type"}},
])
def test_web_login_validation_never_echoes_input(tmp_path, body):
    with TestClient(create_app(settings(tmp_path), httpx.MockTransport(lambda r: pytest.fail("network")))) as client:
        response = client.post("/api/campus/login", json=body)
        assert response.status_code == 422 and response.json()["error"]["code"] == "campus_invalid_login"
        assert "private" not in response.text and "synthetic" not in response.text


def test_web_login_malformed_json_never_echoes_body(tmp_path):
    with TestClient(create_app(settings(tmp_path), httpx.MockTransport(lambda r: pytest.fail("network")))) as client:
        response = client.post("/api/campus/login", content='{"password":"private-password", BROKEN',
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 422 and "private-password" not in response.text


@pytest.mark.parametrize("status", [400, 401, 403])
def test_web_login_failure_keeps_existing_credentials_and_redacts(tmp_path, status):
    config = settings(tmp_path)
    seed(config)
    with TestClient(create_app(config, httpx.MockTransport(lambda r: httpx.Response(status, text="private-password")))) as client:
        response = client.post("/api/campus/login", json={"email": "synthetic@example.invalid", "password": "private-password"})
        assert response.status_code == 401 and response.json()["error"]["code"] == "campus_login_failed"
        assert "private-password" not in response.text
    assert TokenStore(config.auth_path).load().access.get_secret_value() == "old-access"
