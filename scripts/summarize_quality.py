"""Compare recorded runs without assigning factual-quality scores or claiming bills."""

import argparse
import json
from pathlib import Path

# Official public rates checked 2026-11-02. Estimates are USD and deliberately
# span off-peak/peak; account discounts, free credit and failed calls are unknown.
PRICING = {
    "checked_on": "2026-11-02",
    "model": "deepseek-flash",
    "model_source": "https://api-docs.deepseek.com/quick_start/pricing/",
    "search_source": "https://docs.tavily.com/documentation/api-credits",
    "off_peak_per_million": {"hit": 0.003, "miss": 0.15, "output": 0.6},
    "peak_multiplier": 2,
    "search_payg_per_credit": 0.008,
}


def summarize(case: dict) -> dict:
    turns = case["turns"]
    metrics = [turn.get("metrics") or {} for turn in turns]
    totals = {key: sum(metric.get(key, 0) for metric in metrics) for key in
              ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")}
    calls = sum(turn["model_calls"] for turn in turns)
    usage_complete = sum(m.get("usage_reported_calls", 0) for m in metrics) == calls
    cache_complete = usage_complete and sum(m.get("cache_usage_reported_calls", 0) for m in metrics) == calls
    rates = PRICING["off_peak_per_million"]
    if cache_complete:
        input_low = input_high = totals["prompt_cache_hit_tokens"] * rates["hit"] + totals["prompt_cache_miss_tokens"] * rates["miss"]
    else:
        input_low, input_high = totals["prompt_tokens"] * rates["hit"], totals["prompt_tokens"] * rates["miss"]
    output = totals["completion_tokens"] * rates["output"]
    live = case["retrieval"].startswith("live")
    successes = sum(turn.get("search_successes", sum(e["type"] == "tool_complete" and e.get("name") == "search_web"
                    for e in turn["events"])) for turn in turns) if live else 0
    attempts = sum(turn.get("search_requests", 0) for turn in turns) if live else 0
    credits = successes * (2 if case["settings"]["search_depth"] == "advanced" else 1)
    return {
        "case": case["case"], "seconds": round(sum(t["elapsed_seconds"] for t in turns), 2),
        "model_calls": calls, "tool_calls": sum(t["tool_calls"] for t in turns), **totals,
        "model_usd_range_on_reported_tokens": [round((input_low + output) / 1e6, 8),
                                               round((input_high + output) * 2 / 1e6, 8)] if case["model"] == PRICING["model"] else None,
        "usage_complete": usage_complete, "cache_complete": cache_complete,
        "search_successes": successes, "search_failed_or_unobserved": max(0, attempts - successes),
        "search_credits_estimate": credits, "search_payg_usd_equivalent": round(credits * 0.008, 4),
        "note": "仅观测用量估算，非账单；未报告/失败调用、免费额度、折扣及其他服务费用不确定。",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({"pricing": PRICING, "runs": {path.stem: [summarize(case) for case in json.loads(path.read_text(encoding="utf-8"))]
                                                for path in args.reports}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
