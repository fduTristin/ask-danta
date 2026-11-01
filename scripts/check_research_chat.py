"""Explicit paid live research check. Prints tool names/counts, not post bodies or credentials."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    session_id = None

    def request(path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        return urlopen(Request(base + path, data=data, method=method,
                              headers={"Content-Type": "application/json"}), timeout=130)

    def chat(question, mode):
        with request(f"/api/sessions/{session_id}/chat", "POST", {"message": question, "source_mode": mode}) as response:
            return [json.loads(frame[6:]) for frame in response.read().decode().strip().split("\n\n")]

    try:
        with request("/api/health") as response:
            health = json.load(response)
        if health.get("stage", 0) < 4 or not health["campus"].get("tools_enabled") or health["search"]["is_mock"]:
            print("NOT VERIFIED: stage 4, campus credentials and live web search are required.")
            return 1
        with request("/api/sessions", "POST") as response:
            session_id = json.load(response)["session_id"]
        events = chat("请对照复旦图书馆官网与树洞里的江湾图书馆自习体验。先列简短调研计划，查一条官网资料，在树洞搜索江湾图书馆并读取一个命中帖子的上下文，再用两三句话说明官方信息和个人体验的区别，附引用；不要引用个人身份信息或完整帖子。", "all")
        completed = [event for event in events if event["type"] == "tool_complete"]
        names = [event["name"] for event in completed]
        final = events[-1]
        sources = final.get("message", {}).get("sources", [])
        codes = [e["error"]["code"] for e in events if "error" in e]
        print(json.dumps({"tools": names, "error_codes": codes, "citation_ids": [s["id"] for s in sources],
                          "campus_pages": final.get("campus_pages"), "status": final.get("message", {}).get("status"),
                          "metrics": final.get("metrics")}, ensure_ascii=True))
        required = {"plan_research", "search_web", "search_campus_posts", "read_campus_thread"}
        if not required <= set(names) or not any(s.get("source") == "campus" for s in sources) or final.get("message", {}).get("status") != "complete":
            print("NOT VERIFIED: live tool chain or final citations incomplete; inspect sanitized errors.")
            return 1
        followup = chat("我现在改到枫林校区。只确认这个校区变更，不搜索，不使用此前树洞资料。", "web")
        assert followup[0]["allowed_sources"] == ["web"]
        assert not any(e.get("name") in ("search_campus_posts", "read_campus_thread") for e in followup)
        assert "枫林" in followup[-1]["message"]["content"]
        print("Live research tool chain and web-only followup passed. This is not a factual-quality score.")
        return 0
    except (HTTPError, URLError, OSError, ValueError, KeyError, AssertionError):
        print("NOT VERIFIED: service request, stream or followup check failed; no raw responses printed.")
        return 1
    finally:
        if session_id:
            try:
                request(f"/api/sessions/{session_id}", "DELETE").close()
            except (HTTPError, URLError, OSError):
                pass


if __name__ == "__main__":
    sys.exit(main())
