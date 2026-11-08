"""Explicit paid model evaluation. Fixture retrieval and live retrieval are labelled separately.

Run with the project Python. Reports contain only fixed public/synthetic questions,
answers and source evidence, never keys, raw reasoning or request headers.
"""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from app.agent import Agent, Session, MAX_REVIEW_CALLS
from app.config import Settings
from app.model import ModelService
from app.search import SearchResponse, SearchResult, SearchService
from app.reader import PageReader
from app.answer import character_limit
from app.campus import CampusService, redact
from quality_fixtures import RESEARCH_CASES, ResearchSearch, ResearchReader, campus_response

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
CASES += RESEARCH_CASES


class FixtureSearch:
    def __init__(self, case_id):
        self.case_id, self.queries = case_id, []

    async def search(self, query: str) -> SearchResponse:
        self.queries.append(query)
        unrelated = self.case_id == "irrelevant" and len(self.queries) == 1
        return SearchResponse(query=query, provider="tavily", is_mock=False,
            notice="评测注入的合成检索响应；只用于检验处理行为，不是实际 Tavily 搜索。",
            results=[SearchResult(
                title="其他学校旅游介绍" if unrelated else "演示大学办事说明" if self.case_id == "read_gap" else "复旦大学研究生院",
                url="https://example.org/unrelated" if unrelated else "https://example.org/synthetic/materials" if self.case_id == "read_gap" else "https://gs.fudan.edu.cn/",
                snippet="这是一篇与复旦研究生院无关的旅游介绍。" if unrelated else "虚构演示大学材料申请指南，详细办理时限请查看本页正文。" if self.case_id == "read_gap" else "江湾校区距邯郸校区约3.5公里。另一条网络问答说：与本部相比，枫林校区距离稍远，约20公里。两条资料都未提供江湾到枫林校区的距离。" if self.case_id == "distance_decoy" else "复旦大学研究生院官方网站。首页导航：学生服务、研究生各类证明。此摘录没有说明办理时限、申请材料或保证办结时间。",
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


class CountSearch:
    def __init__(self, search):
        self.search_service = search
        self.attempts = self.successes = 0

    async def search(self, query):
        self.attempts += 1
        response = await self.search_service.search(query)
        self.successes += 1
        return response


def private_safe_report(report: dict) -> dict:
    """Omit all real post bodies, even exact copies in fallback answers."""
    bodies = {s["snippet"] for turn in report["turns"] for s in turn["sources"]
              if s.get("source") == "campus" and s.get("snippet")}

    def scrub(value):
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: "[真实树洞正文不保存]" if value.get("source") == "campus" and key in ("content", "snippet") else scrub(item)
                    for key, item in value.items()}
        if isinstance(value, str):
            for body in sorted(bodies, key=len, reverse=True):
                value = value.replace(body, "[真实树洞正文不保存]")
            return redact(value)[0]
        return value
    return scrub(report)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--thinking", choices=["enabled", "disabled"])
    parser.add_argument("--case", action="append", choices=[case["id"] for case in CASES])
    parser.add_argument("--exclude-case", action="append", default=[], choices=[case["id"] for case in CASES])
    parser.add_argument("--repeat", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--review", choices=["enabled", "disabled"], help="Explicit ablation; normal default remains enabled")
    args = parser.parse_args()
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("label must contain only letters, digits, hyphens or underscores")
    from app.runtime_settings import load_settings
    config = load_settings()
    if args.thinking:
        config = config.model_copy(update={"model_thinking": args.thinking})
    if args.review:
        config = config.model_copy(update={"answer_review_enabled": args.review == "enabled"})
    reports = []
    folder = ROOT / ".private/quality"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / (args.label + ".json")
    if output.exists():
        parser.error("label already exists; choose a new label to preserve earlier results")
    selected = [case for case in CASES if (not args.case or case["id"] in args.case) and case["id"] not in args.exclude_case]
    if not selected:
        parser.error("No cases selected")
    for case in selected:
        for repetition in range(1, args.repeat + 1):
            with tempfile.TemporaryDirectory(prefix="campus-quality-") as temp:
                case_config = config.model_copy(update={"campus_auth_file": Path(temp) / "tokens.json"})
                if case.get("campus") in ("fixture", "expired"):
                    case_config.auth_path.write_text(json.dumps({"access": "synthetic-access", "refresh": "synthetic-refresh"}))
                elif case.get("campus") == "live":
                    case_config = config
                await evaluate_case(case, case_config, reports, output, repetition)
    print(str(output))


async def evaluate_case(case: dict, config: Settings, reports: list[dict], output: Path, repetition: int = 1) -> None:
    timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
    async with httpx.AsyncClient(timeout=config.http_timeout_seconds, follow_redirects=False, trust_env=False) as client, \
            httpx.AsyncClient(transport=httpx.MockTransport(lambda r: campus_response(case["id"], r))) as fixture_client:
        model = CountModel(config, client)
        research_fixture = case.get("campus") in ("fixture", "expired")
        search = CountSearch(SearchService(config, client) if case.get("live") else
                             ResearchSearch(case["id"]) if research_fixture else FixtureSearch(case["id"]))
        reader = PageReader(config) if case.get("live") else ResearchReader() if research_fixture else FixtureReader(case["id"])
        campus = CampusService(config, fixture_client if research_fixture else client) if case.get("campus") else None
        if case.get("live") and (config.search_provider != "tavily" or not config.search_configured):
            raise SystemExit("Live evaluation requires configured Tavily; mock is not accepted.")
        if case.get("campus") == "live" and campus.auth_state() != "configured":
            raise SystemExit("Live campus evaluation requires project-owned credentials; no fixture fallback.")
        agent = Agent(config, model, search, reader, campus=campus)
        session = Session()
        turns = []
        for question in case["questions"]:
            start = time.monotonic()
            before = model.calls
            search_before = (search.attempts, search.successes)
            events = [event async for event in agent.events(session, question, case.get("source_mode", "all" if campus else "web"))]
            final = events[-1]
            turns.append({"question": question, "answer": final["message"]["content"],
                "answer_characters": len(final["message"]["content"]), "answer_limit": character_limit(question),
                "sources": deepcopy(session.sources), "model_calls": model.calls - before,
                "search_requests": search.attempts - search_before[0] if case.get("live") else 0,
                "search_successes": search.successes - search_before[1] if case.get("live") else 0,
                "tool_calls": final.get("tool_calls"), "elapsed_seconds": round(time.monotonic() - start, 2),
                "campus_pages": final.get("campus_pages"), "end_reason": final["message"].get("end_reason"),
                "metrics": final.get("metrics"), "warnings": final["message"].get("warnings"),
                "status": final["message"].get("status"), "reviewed": final["message"].get("reviewed"),
                "events": [{k: v for k, v in e.items() if k in ("type", "name", "error", "result")} for e in events if e["type"].startswith("tool_")],
            })
        report = {"case": case["id"], "timestamp": timestamp, "retrieval": "live Tavily + campus" if case.get("campus") == "live" else "live Tavily" if case.get("live") else "synthetic fixture; real model",
            "repetition": repetition,
            "fixture_revision": 2, "manual_review": {"verdict": "pending", "reason": "逐项核对证据后填写评审文档；不自动以引用数或状态打分。"},
            "model": config.model_name, "thinking": getattr(config, "model_thinking", "disabled"),
            "settings": {"max_answer_review_calls": MAX_REVIEW_CALLS, **{key: getattr(config, key) for key in ("model_reasoning_effort", "model_max_tokens", "model_timeout_seconds", "search_depth", "max_tool_calls", "max_campus_pages", "request_budget_seconds", "answer_review_enabled")}},
            "expected": case["expected"], "turns": turns}
        reports.append(private_safe_report(report) if case.get("campus") == "live" else report)
        output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{case['id']}[{repetition}]: {sum(t['elapsed_seconds'] for t in turns):.2f}s, model calls={model.calls}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
