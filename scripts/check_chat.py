"""Live DeepSeek + Tavily acceptance; uses quota, prints no keys or full messages."""
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
        return urlopen(Request(base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"}), timeout=620)

    def chat(message):
        received = []
        with request(f"/api/sessions/{session_id}/chat", "POST", {"message": message}) as response:
            for line in response:
                if line.startswith(b"data: "):
                    event = json.loads(line[6:])
                    received.append(event)
                    print("event=" + event["type"], flush=True)
        if not received or received[-1]["type"] != "final":
            raise ValueError("Missing final event")
        if any(e["type"] in ("error", "tool_error") for e in received):
            raise ValueError("Upstream failure; not verified")
        return received

    try:
        with request("/api/health") as response:
            health = json.load(response)
        if not health["model"]["configured"] or health["search"]["is_mock"] or not health["search"]["configured"]:
            print("NOT VERIFIED: configure DeepSeek and real Tavily search first.")
            return 1
        with request("/api/sessions", "POST") as response:
            session_id = json.load(response)["session_id"]
        first = chat("请搜索复旦大学研究生院的官方网站，给出官网名称并引用来源，回答不超过80字。记住本次测试校区条件为江湾。")
        sources = first[-1]["message"]["sources"]
        if not any(e["type"] == "tool_complete" for e in first) or not sources or any(s["is_mock"] for s in sources):
            raise ValueError("No actual tool results")
        if not any(f"[{s['id']}]" in first[-1]["message"]["content"] for s in sources):
            raise ValueError("No source citation in answer")
        followup = chat("不用搜索，只回答我刚才给出的校区条件，20字以内。")
        if "江湾" not in followup[-1]["message"]["content"]:
            raise ValueError("Follow-up did not preserve campus condition")
        print(f"Live chat passed: model={health['model']['name']}, sources={len(sources)}, followup=passed")
        for source in sources:
            print(source["id"] + " " + source["url"])
        return 0
    except (HTTPError, URLError, OSError, ValueError, KeyError) as exc:
        print(f"NOT VERIFIED ({type(exc).__name__}); inspect sanitized errors in the workbench.")
        return 1
    finally:
        if session_id:
            try:
                with request(f"/api/sessions/{session_id}", "DELETE"):
                    pass
            except (HTTPError, URLError, OSError):
                print("Test session cleanup failed; restart backend to clear memory.")


if __name__ == "__main__":
    sys.exit(main())
