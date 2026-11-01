"""Bounded tool loop and transactional, in-memory conversation history."""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import Settings
from .model import ModelError, ModelService
from .search import SearchError, SearchRequest, SearchService
from .reader import PageReader, ReadRequest
from .prompts import SYSTEM, REVIEW

TOOLS = [{"type": "function", "function": {
    "name": "search_web", "description": "检索公开网页，返回标题、来源编号、链接、摘要和可用日期。",
    "parameters": SearchRequest.model_json_schema(),
}}, {"type": "function", "function": {
    "name": "read_web", "description": "按已检索到的来源编号读取公开网页正文，摘要缺少关键事实时使用。不能传任意 URL。",
    "parameters": ReadRequest.model_json_schema(),
}}]


def citation_ids(text: str) -> set[str]:
    return set(re.findall(r"\[(W[1-9][0-9]*)\]", text))


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    message: str = Field(min_length=1, max_length=8000)


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid4()))
    history: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    busy: bool = False

    def public(self) -> dict:
        return {"session_id": self.id, "messages": self.messages, "sources": self.sources, "busy": self.busy}


def fallback(reason: str, sources: list[dict]) -> str:
    text = f"本轮未完成完整回答：{reason}"
    actual = [source for source in sources if not source["is_mock"]]
    if actual:
        text += "\n\n已取得以下网页摘要，尚未完成综合核对："
        for source in actual[-5:]:
            text += f"\n\n[{source['id']}] {source['title']}\n{source['snippet'][:500]}"
    else:
        text += "\n\n尚无可用于核实本轮问题的真实网页资料。"
    return text + "\n\n资料可能不完整；可以缩小问题范围后继续追问。"


class Agent:
    def __init__(self, settings: Settings, model: ModelService, search: SearchService, reader: PageReader | None = None):
        self.settings, self.model, self.search = settings, model, search
        self.reader = reader or PageReader(settings)

    async def events(self, session: Session, question: str):
        # Commit only a completed turn. Disconnect/cancellation discards partial work.
        history = [*session.history, {"role": "user", "content": question}]
        sources = [dict(source) for source in session.sources]
        current_sources: list[dict] = []
        started = time.monotonic()
        deadline = started + self.settings.request_budget_seconds
        reserve = min(self.settings.model_timeout_seconds, self.settings.request_budget_seconds / 3)
        calls = 0
        limited = False
        warnings: list[str] = []
        answer = ""
        reviewed = False
        review_calls = 0
        failed = False
        retrieval_exhausted = False
        attempted: set[tuple[str, str]] = set()
        metrics = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        system = {"role": "system", "content": SYSTEM + "\n当前日期：" + datetime.now(timezone(timedelta(hours=8))).date().isoformat()}

        async def within(awaitable, end: float):
            async with asyncio.timeout(max(0, end - time.monotonic())):
                return await awaitable

        async def complete(messages, tools):
            metrics["model_calls"] += 1
            message = await within(self.model.complete(messages, tools), deadline)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                metrics[key] += message.usage.get(key, 0)
            return message

        try:
            yield {"type": "start", "session_id": session.id}
            try:
                while True:
                    limited = retrieval_exhausted or calls >= self.settings.max_tool_calls or time.monotonic() >= deadline - reserve
                    if limited:
                        warnings.append("已达到工具调用或检索时间预算，停止检索；以下回答仅基于已有资料，可能存在缺口。")
                        yield {"type": "budget", "message": warnings[-1]}
                    messages = [system, *history]
                    if reviewed:
                        messages.append({"role": "system", "content":
                            "这是发布前核对触发补查后的回答。请结合新增证据再次自查切题性和每个关键数值的依据；"
                            "只保留回答本轮问题所需的信息，不能用相关但不回答问题的资料填充篇幅。"
                            "简单事实题仍查不到核心事实时，用两三句话说明缺口和核实方式，不展开无关地址、班次或背景。"})
                    if limited:
                        messages.append({"role": "system", "content": warnings[-1] + "请立即回答，明确未核实部分，不再调用工具。简单事实题只给有证据的答案或简短缺口说明，不展开无关背景。"})
                    yield {"type": "model_start", "message": "正在整理回答…" if limited else "正在理解问题和已有资料…"}
                    message = await complete(messages, [] if limited else TOOLS)
                    if (not message.tool_calls and review_calls < 2 and self.settings.answer_review_enabled
                            and (current_sources or citation_ids(message.content or ""))):
                        reviewed = True
                        review_calls += 1
                        yield {"type": "review_start", "message": "正在核对答案是否切题、引用是否支持结论…"}
                        # The draft is never committed or displayed. The reviewer
                        # can use the remaining tool budget to fill evidence gaps.
                        # If the first check requested more evidence, check the
                        # resulting answer too. This last check cannot reopen
                        # research, so both review cost and the loop are bounded.
                        review_tools = [] if review_calls == 2 or calls >= self.settings.max_tool_calls or time.monotonic() >= deadline - reserve else TOOLS
                        message = await complete([*messages, {"role": "system", "content": REVIEW + json.dumps({"draft": message.content}, ensure_ascii=False)}], review_tools)
                        if not review_tools and message.tool_calls:
                            raise ModelError("model_ignored_review", "模型未按最终核对要求结束工具调用。")
                    if not message.tool_calls:
                        answer = message.content or ""
                        known = {source["id"] for source in sources if not source["is_mock"]}
                        if citation_ids(answer) - known:
                            failed = True
                            warnings.append("回答引用了不存在或合成的来源，未发布该候选答案。")
                            answer = fallback(warnings[-1], current_sources)
                        if limited:
                            answer += "\n\n" + warnings[-1]
                        history.append(message.wire())
                        history[-1]["content"] = answer
                        break
                    if limited:
                        raise ModelError("model_ignored_budget", "模型未按预算要求结束工具调用。")
                    history.append(message.wire())
                    for call in message.tool_calls:
                        active_call = {"call_id": call.id, "name": call.function.name}
                        yield {"type": "tool_start", **active_call}
                        result = None
                        try:
                            if calls >= self.settings.max_tool_calls or time.monotonic() >= deadline - reserve:
                                raise SearchError("tool_budget_exhausted", "检索预算已用完，此工具未执行。")
                            calls += 1  # Invalid/unknown attempts also consume budget.
                            if call.function.name not in ("search_web", "read_web"):
                                raise SearchError("unknown_tool", "不允许执行此工具。")
                            try:
                                args = (SearchRequest if call.function.name == "search_web" else ReadRequest).model_validate_json(call.function.arguments)
                            except ValidationError:
                                raise SearchError("invalid_tool_arguments", "工具参数无效，请按工具定义填写 query 或 source_id。") from None
                            argument = args.query if isinstance(args, SearchRequest) else args.source_id
                            signature = (call.function.name, " ".join(argument.lower().split()))
                            if signature in attempted:
                                raise SearchError("duplicate_tool_call", "本轮已尝试相同调用，请使用已有结果、换关键词或说明缺口。")
                            attempted.add(signature)
                            if isinstance(args, SearchRequest):
                                response = await within(self.search.search(args.query), deadline - reserve)
                                result = response.model_dump(mode="json")
                                enriched = []
                                for item in result["results"]:
                                    source = next((s for s in sources if s["url"] == item["url"] and s["is_mock"] == response.is_mock), None)
                                    if source is None:
                                        source = {**item, "id": f"W{len(sources) + 1}", "is_mock": response.is_mock}
                                        sources.append(source)
                                    else:
                                        source.update(item)
                                    if not any(s["id"] == source["id"] for s in current_sources):
                                        current_sources.append(source)
                                    enriched.append(source)
                                result["results"] = enriched
                            else:
                                source = next((s for s in sources if s["id"] == args.source_id), None)
                                if source is None:
                                    raise SearchError("unknown_source", "来源编号不存在，请先搜索。")
                                result = await within(self.reader.read(source), deadline - reserve)
                                source.update(page_read=True, page_truncated=result["truncated"])
                                if not any(s["id"] == source["id"] for s in current_sources):
                                    current_sources.append(source)
                            yield {"type": "tool_complete", **active_call, "result": result}
                        except (SearchError, TimeoutError) as exc:
                            if isinstance(exc, TimeoutError):
                                retrieval_exhausted = True
                            code = exc.code if isinstance(exc, SearchError) else "tool_budget_exhausted"
                            error = exc.message if isinstance(exc, SearchError) else "检索时间预算已用完，停止当前搜索。"
                            result = {"error": {"code": code, "message": error}}
                            warnings.append(error)
                            yield {"type": "tool_error", **active_call, **result}
                        history.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
                        active_call = None
            except (ModelError, TimeoutError) as exc:
                code = exc.code if isinstance(exc, ModelError) else "request_budget_exhausted"
                reason = exc.message if isinstance(exc, ModelError) else "本轮总时长预算已用完。"
                limited = limited or isinstance(exc, TimeoutError)
                warnings.append(reason)
                failed = True
                yield {"type": "error", "error": {"code": code, "message": reason}}
                answer = fallback(reason, current_sources)
                history.append({"role": "assistant", "content": answer})
            # All tool-call messages are paired before reaching this commit.
            session.history = history
            session.sources = sources
            cited = citation_ids(answer)
            assistant = {"role": "assistant", "content": answer,
                         "sources": [s for s in sources if s["id"] in cited and not s["is_mock"]],
                         "warnings": warnings, "limited": limited, "reviewed": reviewed,
                         "status": "incomplete" if failed or limited else "complete"}
            session.messages.extend([{"role": "user", "content": question}, assistant])
            metrics["elapsed_seconds"] = round(time.monotonic() - started, 3)
            yield {"type": "final", "session_id": session.id, "message": assistant,
                   "session_sources": sources, "tool_calls": calls, "metrics": metrics}
        finally:
            session.busy = False
