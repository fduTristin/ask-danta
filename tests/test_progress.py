import json

from app.progress import Progress


def test_progress_pairs_calls_and_only_keeps_public_metadata():
    progress = Progress()
    assert not progress.update({"type": "start"})
    progress.update({"type": "model_start", "message": "private-reasoning"})
    progress.update({"type": "tool_start", "call_id": "a", "name": "search_web", "arguments": "private-token"})
    progress.update({"type": "tool_complete", "call_id": "a", "name": "search_web",
                     "result": {"query": "private-query", "results": [{"text": "private-body"}], "is_mock": True}})
    progress.update({"type": "tool_start", "call_id": "b", "name": "read_web"})
    progress.update({"type": "tool_error", "call_id": "b", "error": {"message": "private-token"}})
    progress.update({"type": "review_start"})
    progress.update({"type": "final", "message": {"status": "incomplete"}})
    steps = progress.value["steps"]
    assert [step["status"] for step in steps] == ["complete", "complete", "error", "complete"]
    assert steps[1]["detail"] == "返回 1 条资料（合成样例）"
    assert progress.value["status"] == "incomplete"
    assert all(step["duration_ms"] >= 0 for step in steps)
    assert "private-" not in json.dumps(progress.value)


def test_notices_do_not_finish_active_tools_and_stop_does_not_claim_success():
    progress = Progress()
    progress.update({"type": "tool_start", "call_id": "a", "name": "read_campus_thread"})
    progress.update({"type": "source_notice", "message": "private-source"})
    progress.update({"type": "budget"})
    assert progress.value["steps"][0]["status"] == "running"
    progress.update({"type": "interrupted"})
    assert progress.value["status"] == "interrupted"
    assert progress.value["steps"][0]["status"] == "interrupted"
    assert "private-source" not in json.dumps(progress.value)
