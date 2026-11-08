"""Explicit live-search acceptance check. Prints no keys or result bodies."""
import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--query", default="复旦大学 官方网站")
args = parser.parse_args()
try:
    request = Request(
        f"http://127.0.0.1:{args.port}/api/search",
        data=json.dumps({"query": args.query}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=130) as response:
        result = json.load(response)
    if result["is_mock"]:
        sys.exit("NOT VERIFIED: mock results. Select Tavily and save its API Key in Settings > Web search.")
    if not result["results"]:
        sys.exit("Live service responded, but no results. Retry with a broader query; source acceptance is incomplete.")
    print(f"Live search passed: provider={result['provider']}, results={len(result['results'])}")
    for item in result["results"]:
        print(item["url"])
except HTTPError as exc:
    sys.exit(f"Search failed (HTTP {exc.code}); inspect the workbench for the sanitized error.")
except (URLError, OSError, ValueError, KeyError) as exc:
    sys.exit(f"Search check failed ({type(exc).__name__}); confirm the local backend is running.")
