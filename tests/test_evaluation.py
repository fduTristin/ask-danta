"""Evaluation records must preserve evidence snapshots and distinguish cost gaps."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_quality import private_safe_report
from summarize_quality import summarize
from fastapi.testclient import TestClient
from app.config import Settings
import demo_failure


def test_live_report_omits_post_bodies_in_sources_events_and_fallback():
    body = "这是一段不应写入演示报告的真实帖子正文。"
    source = {"id": "C1", "source": "campus", "hole_id": 12, "floor_id": 1, "snippet": body}
    report = {"turns": [{"sources": [source], "answer": "资料未完成核对：" + body,
                         "events": [{"result": {"results": [source]}}]}]}
    clean = private_safe_report(report)
    assert body not in str(clean)
    assert clean["turns"][0]["sources"][0]["floor_id"] == 1
    assert report["turns"][0]["sources"][0]["snippet"] == body


def test_cost_estimate_distinguishes_reported_usage_cache_and_fixtures():
    case = {"case": "fixture", "model": "deepseek-flash", "retrieval": "synthetic fixture; real model",
            "settings": {"search_depth": "advanced"}, "turns": [
                {"model_calls": 1, "tool_calls": 1, "elapsed_seconds": 2, "events": [
                    {"type": "tool_complete", "name": "search_web"}], "metrics": {
                    "prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100,
                    "usage_reported_calls": 1, "cache_usage_reported_calls": 1,
                    "prompt_cache_hit_tokens": 800, "prompt_cache_miss_tokens": 200}}]}
    result = summarize(case)
    assert result["model_usd_range_on_reported_tokens"] == [0.0000924, 0.0001848]
    assert result["usage_complete"] and result["cache_complete"]
    assert result["search_credits_estimate"] == 0
    case["retrieval"] = "live Tavily"
    case["turns"][0]["metrics"].pop("usage_reported_calls")
    result = summarize(case)
    assert not result["usage_complete"] and not result["cache_complete"]
    assert result["search_credits_estimate"] == 2
    assert result["model_usd_range_on_reported_tokens"] == [0.000063, 0.00042]


def test_failure_demo_never_reads_or_changes_project_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(demo_failure, "ROOT", tmp_path)
    dist = tmp_path / "frontend/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>test app</body></html>")
    (dist / "danta-logo.webp").write_bytes(b"synthetic-logo")
    real_path = tmp_path / "real-tokens.json"
    real_path.write_text("not valid credentials; must never be loaded")
    real_history = tmp_path / "real-history" / "chat.sqlite3"
    config = Settings(_env_file=None, campus_auth_file=real_path, model_api_key="test", session_db_file=real_history)
    with TestClient(demo_failure.build_demo(config, tmp_path / "demo-tokens.json")) as client:
        assert "模拟认证失效演示" in client.get("/").text
        assert client.get("/danta-logo.webp").content == b"synthetic-logo"
        assert not real_history.exists()
        assert client.get("/api/health").json()["campus"]["auth_state"] == "configured"
        response = client.post("/api/campus/search", json={"query": "demo"})
        assert response.json()["error"]["code"] == "campus_auth_failed"
        assert client.get("/api/health").json()["campus"]["auth_state"] == "expired"
    assert real_path.read_text() == "not valid credentials; must never be loaded"
