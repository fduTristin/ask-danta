import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import ROOT, Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    # Tests must never depend on the developer's real .env or environment keys.
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def config(**kwargs):
    return Settings(_env_file=None, **kwargs)


def client_for(handler, **kwargs):
    return TestClient(create_app(
        config(search_provider="tavily", search_api_key="test-secret", **kwargs),
        httpx.MockTransport(handler),
    ))


def test_no_credentials_startup_and_explicit_mock(tmp_path):
    def no_network(request):
        pytest.fail("Mock mode must not access the network")

    with TestClient(create_app(config(campus_auth_file=tmp_path / "absent.json"), httpx.MockTransport(no_network))) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["campus"] == {"credentials_present": False, "available": False, "auth_state": "missing", "tools_enabled": False}
        assert health["model"]["configured"] is False
        result = client.post("/api/search", json={"query": "校内办事"}).json()
        assert result["is_mock"] is True
        assert "固定样例" in result["notice"]


def test_health_never_exposes_secrets_or_auth_path(tmp_path):
    auth = tmp_path / "private-location.json"
    auth.write_text("malformed credentials", encoding="utf-8")
    with TestClient(create_app(config(model_api_key="model-secret", search_api_key="search-secret", campus_auth_file=auth))) as client:
        response = client.get("/api/health")
        assert response.json()["campus"] == {"credentials_present": True, "available": False, "auth_state": "invalid", "tools_enabled": False}
        for secret in ("model-secret", "search-secret", str(auth), "malformed credentials"):
            assert secret not in response.text


@pytest.mark.parametrize("query", ["", "   ", "x" * 501, None, 123])
def test_reject_bad_query(query):
    with TestClient(create_app(config())) as client:
        assert client.post("/api/search", json={"query": query}).status_code == 422


def test_missing_search_key_does_not_prevent_startup_or_fake_results():
    with TestClient(create_app(config(search_provider="tavily"))) as client:
        assert client.get("/api/health").status_code == 200
        response = client.post("/api/search", json={"query": "test"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "search_not_configured"


def test_live_adapter_normalizes_deduplicates_and_preserves_dates():
    def handler(request):
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["query"] == "校园通知"
        assert body["max_results"] == 2
        assert body["include_answer"] is False
        item = {"title": "通知", "url": "https://example.org/notice", "content": "x" * 120, "published_date": "2026-10-01"}
        return httpx.Response(200, json={"results": [item, item, {"title": "指南", "url": "https://example.org/guide", "content": "摘要"}]})

    with client_for(handler, search_max_results=2, search_max_snippet_chars=100) as client:
        response = client.post("/api/search", json={"query": "  校园通知  "})
        assert response.status_code == 200
        result = response.json()
        assert result["is_mock"] is False
        assert len(result["results"]) == 2
        assert result["results"][0]["truncated"] is True
        assert len(result["results"][0]["snippet"]) == 100
        assert result["results"][0]["published_at"] == "2026-10-01"
        assert result["results"][1]["published_at"] is None


def test_empty_results_are_success():
    with client_for(lambda request: httpx.Response(200, json={"results": []})) as client:
        response = client.post("/api/search", json={"query": "test"})
        assert response.status_code == 200
        assert response.json()["results"] == []
        assert response.json()["is_mock"] is False


@pytest.mark.parametrize("status,expected", [(401, "search_auth_failed"), (403, "search_auth_failed"), (429, "search_rate_limited"), (432, "search_rate_limited"), (500, "search_upstream_error")])
def test_upstream_errors_are_sanitized(status, expected):
    with client_for(lambda request: httpx.Response(status, text="test-secret private body")) as client:
        response = client.post("/api/search", json={"query": "test"})
        assert response.json()["error"]["code"] == expected
        assert "test-secret" not in response.text
        assert "private body" not in response.text
        assert "results" not in response.json()


@pytest.mark.parametrize("payload", [{}, {"results": None}, {"results": [{"title": "bad", "url": "javascript:alert(1)", "content": "bad"}]}])
def test_malformed_upstream(payload):
    with client_for(lambda request: httpx.Response(200, json=payload)) as client:
        response = client.post("/api/search", json={"query": "test"})
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "search_invalid_response"


def test_non_json_upstream():
    with client_for(lambda request: httpx.Response(200, text="not json")) as client:
        assert client.post("/api/search", json={"query": "test"}).json()["error"]["code"] == "search_invalid_response"


@pytest.mark.parametrize("exception,code", [(httpx.ReadTimeout, "search_timeout"), (httpx.ConnectError, "search_unreachable")])
def test_network_failures(exception, code):
    def handler(request):
        raise exception("test-secret", request=request)
    with client_for(handler) as client:
        response = client.post("/api/search", json={"query": "test"})
        assert response.json()["error"]["code"] == code
        assert "test-secret" not in response.text


def test_config_paths_env_priority_and_budget_validation(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("MODEL_NAME=file-model\nMODEL_API_KEY=file-secret\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_NAME", "environment-model")
    settings = Settings(_env_file=dotenv)
    assert settings.model_name == "environment-model"
    assert settings.auth_path == ROOT / ".private/campus-tokens.json"
    assert "file-secret" not in repr(settings)
    with pytest.raises(ValidationError):
        config(max_tool_calls=0)
    with pytest.raises(ValidationError):
        config(backend_port=5173)
