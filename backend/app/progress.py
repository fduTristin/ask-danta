"""Public execution milestones, deliberately excluding model reasoning and tool payloads."""

import time


TOOLS = {
    "plan_research": "规划资料检索",
    "search_web": "搜索公开网页",
    "read_web": "读取网页正文",
    "search_campus_posts": "搜索树洞讨论",
    "read_campus_thread": "读取帖子上下文",
}


class Progress:
    def __init__(self):
        self.started = time.monotonic()
        self.value = {"started_at": int(time.time() * 1000), "elapsed_ms": 0,
                      "status": "running", "steps": []}

    def update(self, event: dict) -> bool:
        kind = event["type"]
        if kind not in {"model_start", "review_start", "tool_start", "tool_complete",
                        "tool_error", "source_notice", "budget", "error", "final", "interrupted"}:
            return False
        elapsed = round((time.monotonic() - self.started) * 1000)
        self.value["elapsed_ms"] = elapsed
        steps = self.value["steps"]

        def finish(step, status="complete"):
            step.update(status=status, duration_ms=max(0, elapsed - step["started_ms"]))

        if kind in {"tool_complete", "tool_error"}:
            step = next((s for s in reversed(steps) if s.get("call_id") == event.get("call_id") and s["status"] == "running"), None)
            if step:
                finish(step, "error" if kind == "tool_error" else "complete")
                result = event.get("result", {})
                if kind == "tool_error":
                    step["detail"] = "本次调用未完成，将根据已有资料继续处理。"
                elif isinstance(result.get("results"), list):
                    step["detail"] = f"返回 {len(result['results'])} 条资料" + ("（合成样例）" if result.get("is_mock") else "")
                elif event.get("name") == "read_web":
                    step["detail"] = "已读取部分网页文本" if result.get("truncated") else "已读取网页文本"
            return True

        if kind in {"source_notice", "budget"}:
            # Fixed copy only: raw results, arguments and model text never enter the trace.
            steps.append({"id": str(len(steps)), "label": "资料来源提示" if kind == "source_notice" else "检索额度提示",
                          "detail": "部分来源不可用，使用当前可用资料。" if kind == "source_notice" else "已达到检索限制，正在整理已有资料。",
                          "status": "notice", "started_ms": elapsed, "duration_ms": 0})
            return True

        for step in steps:
            if step["status"] == "running":
                finish(step, "error" if kind == "error" else "interrupted" if kind == "interrupted" else "complete")
        if kind in {"final", "error", "interrupted"}:
            status = "interrupted" if kind == "interrupted" else "error" if kind == "error" else "complete"
            if kind == "final" and event.get("message", {}).get("status") == "incomplete":
                status = "incomplete"
            self.value["status"] = status
            return True

        label = ("核对答案与引用" if kind == "review_start" else
                 TOOLS.get(event.get("name"), "调用资料工具") if kind == "tool_start" else
                 "整理资料与回答" if any(s.get("tool") for s in steps) else "理解问题与已有资料")
        step = {"id": str(len(steps)), "label": label, "status": "running", "started_ms": elapsed}
        if kind == "tool_start":
            step.update(call_id=event.get("call_id"), tool=event.get("name") if event.get("name") in TOOLS else "unknown")
        steps.append(step)
        return True
