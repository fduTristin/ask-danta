"""Explicit paid model evaluation. Fixture retrieval and live retrieval are labelled separately.

Run with the project Python. Reports contain only fixed public/synthetic questions,
answers and source evidence, never keys, raw reasoning or request headers.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from app.agent import Agent, Session
from app.config import Settings
from app.model import ModelService
from app.search import SearchResponse, SearchResult, SearchService
from app.reader import PageReader

CASES = [
    {"id": "greeting", "questions": ["你好，你可以帮我做什么？用两句话回答。"], "expected": "直接说明能力，不检索、不反问无关条件。"},
    {"id": "memory", "questions": ["记住我现在在江湾校区，不用介绍校区。", "我改到枫林校区了。只回答我现在在哪个校区，不要地址或其他信息。"], "expected": "第二轮只答枫林校区，无搜索、无地址补充。"},
    {"id": "official", "questions": ["请搜索复旦大学研究生院官网，只给官网名称和引用，不需要地址。"], "expected": "复旦大学研究生院，有正确来源引用，不补充地址；合成资料的限制说明允许保留。真实检索的简洁性另用live_official验证。"},
    {"id": "irrelevant", "questions": ["请查复旦大学研究生院官网，只要名称和引用。"], "expected": "第一批命中无关时改词补查，引用第二批相关证据。"},
    {"id": "unsupported", "questions": ["请查复旦大学研究生在读证明是否保证申请后24小时办好？只依据查到的资料回答。"], "expected": "首页导航不能证明24小时办结，不杜撰政策或承诺。"},
    {"id": "distance", "live": True, "questions": ["复旦大学江湾校区离枫林校区多远"], "expected": "直接给有依据的距离或范围，区分直线/道路/轨道口径；无依据时明确缺口，不只反问出行方式。"},
    {"id": "read_gap", "questions": ["在虚构的演示大学测试情境中，请查演示大学材料申请要几个工作日。搜索摘要不含时限，请读取相关网页正文再回答。"], "expected": "读取命中正文后回答虚构情境中3个工作日，不仅给出摘要。"},
    {"id": "distance_decoy", "questions": ["复旦大学江湾校区离枫林校区多远？只依据查到的资料回答。"], "expected": "工具只返回江湾到邯郸3.5公里和本部到枫林约20公里时，不把它们用作江湾到枫林的距离，也不编造新数字。"},
    {"id": "live_official", "live": True, "questions": ["请搜索复旦大学研究生院官网，只给官网名称和引用，不需要地址。"], "expected": "真实搜索后只给复旦大学研究生院及引用，无多余说明。"},
    {"id": "live_read", "live": True, "questions": ["请搜索并读取复旦大学研究生院官网首页正文，只回答首页是否有“学生服务”栏目，附引用。"], "expected": "实际读取正文，正确判断栏目存在并引用，不仅引用搜索摘要。"},
]


class FixtureSearch:
    def __init__(self, case_id):
        self.case_id, self.queries = case_id, []

    async def search(self, query):
        self.queries.append(query)
        unrelated = self.case_id == "irrelevant" and len(self.queries) == 1
        return SearchResponse(query=query, provider="tavily", is_mock=False,
            notice="评测注入的合成检索响应；只用于检验处理行为，不是实际 Tavily 搜索。",
            results=[SearchResult(
                title="其他学校旅游介绍" if unrelated else "演示大学办事说明" if self.case_id == "read_gap" else "复旦大学研究生院",
                url="https://example.org/unrelated" if unrelated else "https://gs.fudan.edu.cn/",
                snippet="这是一篇与复旦研究生院无关的旅游介绍。" if unrelated else "江湾校区距邯郸校区约3.5公里。另一条网络问答说：与本部相比，枫林校区距离稍远，约20公里。两条资料都未提供江湾到枫林校区的距离。" if self.case_id == "distance_decoy" else "复旦大学研究生院官方网站。首页导航：学生服务、研究生各类证明。此摘录没有说明办理时限、申请材料或保证办结时间。",
            )])


class FixtureReader:
    def __init__(self, case_id):
        self.case_id = case_id

    async def read(self, source):
        return {"source_id": source["id"], "url": source["url"], "title": source["title"], "truncated": False,
                "text": "虚构情境测试正文：演示大学材料申请在材料齐全后3个工作日办结。" if self.case_id == "read_gap" else "测试正文只包含网站目录，没有办理时限或保证的说明。"}


class CountModel(ModelService):
    def __init__(self, *args):
        super().__init__(*args)
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        return await super().complete(*args, **kwargs)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--thinking", choices=["enabled", "disabled"])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("label must contain only letters, digits, hyphens or underscores")
    config = Settings()
    if args.thinking:
        config = config.model_copy(update={"model_thinking": args.thinking})
    reports = []
    folder = ROOT / ".private/quality"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / (args.label + ".json")
    for case in CASES:
        if args.case and case["id"] not in args.case:
            continue
        async with httpx.AsyncClient(timeout=config.http_timeout_seconds, follow_redirects=False) as client:
            model = CountModel(config, client)
            search = SearchService(config, client) if case.get("live") else FixtureSearch(case["id"])
            agent = Agent(config, model, search, PageReader(config) if case.get("live") else FixtureReader(case["id"]))
            session = Session()
            turns = []
            for question in case["questions"]:
                start = time.monotonic()
                before = model.calls
                events = [event async for event in agent.events(session, question)]
                final = events[-1]
                turns.append({"question": question, "answer": final["message"]["content"],
                    "sources": session.sources, "model_calls": model.calls - before,
                    "tool_calls": final.get("tool_calls"), "elapsed_seconds": round(time.monotonic() - start, 2),
                    "metrics": final.get("metrics"), "warnings": final["message"].get("warnings"),
                    "status": final["message"].get("status"), "reviewed": final["message"].get("reviewed"),
                    "events": [{k: v for k, v in e.items() if k in ("type", "name", "error", "result")} for e in events if e["type"].startswith("tool_")],
                })
            reports.append({"case": case["id"], "retrieval": "live Tavily" if case.get("live") else "synthetic fixture; real model",
                "model": config.model_name, "thinking": getattr(config, "model_thinking", "disabled"),
                "settings": {key: getattr(config, key) for key in ("model_reasoning_effort", "model_max_tokens", "model_timeout_seconds", "search_depth", "max_tool_calls", "request_budget_seconds", "answer_review_enabled")},
                "expected": case["expected"], "turns": turns})
            output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{case['id']}: {sum(t['elapsed_seconds'] for t in turns):.2f}s, model calls={model.calls}", flush=True)
    print(str(output))


if __name__ == "__main__":
    asyncio.run(main())
