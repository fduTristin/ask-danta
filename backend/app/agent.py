"""Bounded tool loop and transactional, in-memory conversation history."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import Settings
from .model import ModelError, ModelService
from .search import SearchError, SearchRequest, SearchService
from .reader import PageReader, ReadRequest
from .prompts import SYSTEM, REVIEW, AUDIT
from .campus import CampusService, CampusBudget, CampusSearchRequest, CampusThreadRequest
from .campus_auth import CampusError
from .research import ResearchPlan, load_research_skill
from .answer import AnswerAudit, answer_issues, character_limit, citation_ids, review_payload, short_failure

TOOLS = [{"type": "function", "function": {
    "name": "search_web", "description": "检索公开网页，返回标题、来源编号、链接、摘要和可用日期。",
    "parameters": SearchRequest.model_json_schema(),
}}, {"type": "function", "function": {
    "name": "read_web", "description": "按已检索到的来源编号读取公开网页正文，摘要缺少关键事实时使用。不能传任意 URL。",
    "parameters": ReadRequest.model_json_schema(),
}}]

CAMPUS_TOOLS = [{"type": "function", "function": {
    "name": "search_campus_posts", "description": "搜索获授权的树洞楼层，返回洞号、楼层 ID、正文、日期和来源编号。不是公开网页搜索。",
    "parameters": CampusSearchRequest.model_json_schema(),
}}, {"type": "function", "function": {
    "name": "read_campus_thread", "description": "按洞号分页读取帖子元数据和楼层上下文；每次只读取一页，不代表完整帖子。",
    "parameters": CampusThreadRequest.model_json_schema(),
}}]
PLAN_TOOL = {"type": "function", "function": {
    "name": "plan_research", "description": "复杂校园调研记录或更新子问题、证据缺口和下一步行动，应用 campus-research Skill；简单聊天不用。只记录工作计划，不记录内部思考。",
    "parameters": ResearchPlan.model_json_schema(),
}}
ARGUMENTS = {"search_web": SearchRequest, "read_web": ReadRequest,
             "search_campus_posts": CampusSearchRequest, "read_campus_thread": CampusThreadRequest,
             "plan_research": ResearchPlan}
MAX_REVIEW_CALLS = 4


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    message: str = Field(min_length=1, max_length=8000)
    source_mode: Literal["web", "all"] | None = None


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid4()))
    history: list[dict] = field(default_factory=list)
    web_history: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    busy: bool = False

    def public(self) -> dict:
        return {"session_id": self.id, "messages": self.messages, "sources": self.sources, "busy": self.busy}


def fallback(reason: str, sources: list[dict]) -> str:
    text = f"本轮未完成完整回答：{reason}"
    actual = [source for source in sources if not source["is_mock"]]
    if actual:
        text += "\n\n已取得以下来源资料，尚未完成综合核对："
        for source in actual[-5:]:
            text += f"\n\n[{source['id']}] {source['title']}\n{source['snippet'][:500]}"
    else:
        text += "\n\n尚无可用于核实本轮问题的真实资料。"
    return text + "\n\n资料可能不完整；可以缩小问题范围后继续追问。"


class Agent:
    def __init__(self, settings: Settings, model: ModelService, search: SearchService, reader: PageReader | None = None,
                 campus: CampusService | None = None):
        self.settings, self.model, self.search = settings, model, search
        self.reader = reader or PageReader(settings)
        self.campus = campus
        self.skill = load_research_skill()

    async def events(self, session: Session, question: str, source_mode: str | None = None):
        # Commit only a completed turn. Disconnect/cancellation discards partial work.
        campus_ready = self.campus is not None and self.campus.auth_state() == "configured"
        mode = source_mode or ("all" if campus_ready else "web")
        if mode not in ("web", "all"):
            raise ValueError("Invalid source mode")
        campus_allowed = mode == "all" and campus_ready
        campus_evidence_allowed = campus_allowed
        base_history = session.history if campus_allowed else session.web_history
        history = [*base_history, {"role": "user", "content": question}]
        sources = [dict(source) for source in session.sources]
        current_sources: list[dict] = []
        started = time.monotonic()
        deadline = started + self.settings.request_budget_seconds
        reserve = min(self.settings.model_timeout_seconds, self.settings.request_budget_seconds / 3)
        calls = 0
        limited = False
        warnings: list[str] = []
        if mode == "all" and not campus_allowed:
            warnings.append("树洞未登录或凭据失效，本轮仅使用公开网页；请在服务状态中重新登录。")
        campus_budget = CampusBudget(self.settings.max_campus_pages)
        plan: dict | None = None
        used_skill = False
        limit = character_limit(question)

        def available_tools():
            return [*TOOLS, PLAN_TOOL, *(CAMPUS_TOOLS if campus_allowed and campus_budget.pages < campus_budget.max_pages else [])]

        def permitted_source(source):
            return campus_evidence_allowed or source.get("source") != "campus"
        answer = ""
        reviewed = False
        review_calls = 0
        failed = False
        retrieval_exhausted = False
        attempted: set[tuple[str, str]] = set()
        metrics = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                   "usage_reported_calls": 0, "cache_usage_reported_calls": 0,
                   "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0,
                   "review_calls": 0, "answer_repairs": 0}
        system = {"role": "system", "content": SYSTEM + "\n当前日期：" + datetime.now(timezone(timedelta(hours=8))).date().isoformat()
                  + "\n本轮数据源权限：" + ("公开网页与树洞只读工具。" if campus_allowed else "仅公开网页；不得调用树洞工具或引用此前树洞资料。")
                  + "\n已加载 Skill：" + self.skill.name + "\n适用条件：" + self.skill.description + "\n" + self.skill.instructions
                  + ("\n" + warnings[0] if warnings else "")}
        if limit is not None:
            system["content"] += f"\n本轮回答硬性上限：{limit}个字符（包括标点、空白与引用编号）。精简表达，保留条件和引用。"

        async def within(awaitable, end: float):
            async with asyncio.timeout(max(0, end - time.monotonic())):
                return await awaitable

        async def complete(messages, tools):
            metrics["model_calls"] += 1
            message = await within(self.model.complete(messages, tools), deadline)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                metrics[key] += message.usage.get(key, 0)
            if all(key in message.usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
                metrics["usage_reported_calls"] += 1
            cache_keys = ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
            if (all(key in message.usage for key in cache_keys)
                    and sum(message.usage[key] for key in cache_keys) == message.usage.get("prompt_tokens")):
                metrics["cache_usage_reported_calls"] += 1
                for key in cache_keys:
                    metrics[key] += message.usage[key]
            return message

        try:
            yield {"type": "start", "session_id": session.id, "source_mode": mode,
                   "allowed_sources": ["web", "campus"] if campus_allowed else ["web"], "skill_loaded": self.skill.name}
            for warning in warnings:
                yield {"type": "source_notice", "message": warning}
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
                    message = await complete(messages, [] if limited else available_tools())
                    needs_review = self.settings.answer_review_enabled
                    known = {source["id"] for source in sources if not source["is_mock"] and permitted_source(source)}
                    corrections = []
                    audit_format_error = None
                    while not message.tool_calls and review_calls < MAX_REVIEW_CALLS:
                        issues = answer_issues(message.content or "", known, limit)
                        if not needs_review and not issues and not corrections:
                            break
                        # No real evidence can repair a fabricated factual citation.
                        if not needs_review and not known and limit is None and not corrections:
                            break
                        reviewed = True
                        review_calls += 1
                        metrics["review_calls"] = review_calls
                        yield {"type": "review_start", "message": "正在核对答案是否切题、引用是否支持结论…"}
                        # A separate audit identifies unsupported assertions before
                        # editing. At most four review/edit calls share the original
                        # deadline; only the first audit can reopen retrieval.
                        review_tools = [] if not needs_review or issues or review_calls > 1 or calls >= self.settings.max_tool_calls or time.monotonic() >= deadline - reserve else available_tools()
                        payload = review_payload(question, history, [s for s in sources if permitted_source(s)],
                                                 len(base_history), message.content or "", limit)
                        payload["runtime_notices"] = warnings
                        payload["corrections"] = corrections
                        payload["audit_format_error"] = audit_format_error
                        checked = await complete([
                            {"role": "system", "content": AUDIT if needs_review else REVIEW},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                        ], review_tools)
                        if not review_tools and checked.tool_calls:
                            raise ModelError("model_ignored_review", "模型未按最终核对要求结束工具调用。")
                        if checked.tool_calls:
                            message = checked
                            break
                        if needs_review:
                            try:
                                corrections = AnswerAudit.model_validate_json(checked.content).corrections
                            except ValidationError:
                                if review_calls < MAX_REVIEW_CALLS:
                                    audit_format_error = "仅返回 corrections 字符串数组，不要附加正文或代码块。"
                                    metrics["review_format_retries"] = metrics.get("review_format_retries", 0) + 1
                                    continue
                                raise ModelError("model_invalid_review", "模型核对结果格式无效，本轮未能完成回答。") from None
                            needs_review = False
                            if (corrections or issues) and review_calls == MAX_REVIEW_CALLS:
                                raise ModelError("answer_review_incomplete", "答案仍需修正，但本轮核对预算已用完。")
                        else:
                            message = checked
                            metrics["answer_repairs"] += 1
                            corrections = []
                            # An edit can introduce a new factual mistake. Spend
                            # the remaining review call auditing the edited prose
                            # when the mechanical constraints already hold.
                            needs_review = self.settings.answer_review_enabled and not answer_issues(message.content or "", known, limit)
                    if not message.tool_calls:
                        answer = message.content or ""
                        issues = answer_issues(answer, known, limit)
                        if issues:
                            failed = True
                            warnings.append("回答引用了不存在或合成的来源，未发布该候选答案。" if any(i["code"] == "unknown_citations" for i in issues)
                                            else "回答仍超出本轮字数上限，未发布该候选答案。")
                            answer = fallback(warnings[-1], current_sources)
                        if limited:
                            answer += "\n\n" + warnings[-1]
                        if limit is not None and len(answer) > limit:
                            failed = True
                            answer = short_failure(limit)
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
                            if call.function.name not in ARGUMENTS:
                                raise SearchError("unknown_tool", "不允许执行此工具。")
                            if call.function.name in ("search_campus_posts", "read_campus_thread") and not campus_allowed:
                                raise SearchError("source_not_allowed", "本轮未授权或无法使用树洞，只能使用公开网页。")
                            try:
                                args = ARGUMENTS[call.function.name].model_validate_json(call.function.arguments)
                            except ValidationError:
                                raise SearchError("invalid_tool_arguments", "工具参数无效，请按工具定义填写参数。") from None
                            signature = (call.function.name, " ".join(json.dumps(args.model_dump(), sort_keys=True, ensure_ascii=False).lower().split()))
                            if signature in attempted:
                                raise SearchError("duplicate_tool_call", "本轮已尝试相同调用，请使用已有结果、换关键词或说明缺口。")
                            attempted.add(signature)
                            used_skill = True
                            if isinstance(args, ResearchPlan):
                                if "campus" in args.sources and not campus_allowed:
                                    raise SearchError("source_not_allowed", "计划包含未授权的树洞来源，请调整为公开网页。")
                                plan = args.model_dump()
                                result = {"skill": self.skill.name, "plan": plan, "remaining_campus_pages": campus_budget.max_pages - campus_budget.pages}
                            elif isinstance(args, (CampusSearchRequest, CampusThreadRequest)):
                                method = self.campus.search_campus_posts if isinstance(args, CampusSearchRequest) else self.campus.read_campus_thread
                                response = await within(method(**args.model_dump(), budget=campus_budget), deadline - reserve)
                                result = response.model_dump(mode="json")
                                result.update(query=args.query if isinstance(args, CampusSearchRequest) else None,
                                              remaining_campus_pages=campus_budget.max_pages - campus_budget.pages)
                                enriched = []
                                for item in result["results"]:
                                    source = next((s for s in sources if s.get("source") == "campus" and s["hole_id"] == item["hole_id"] and s["floor_id"] == item["floor_id"]), None)
                                    fields = {**item, "title": f"树洞 #{item['hole_id']} · 楼层 ID {item['floor_id']}",
                                              "snippet": item["content"], "published_at": item["time_created"], "is_mock": False}
                                    fields.pop("content")  # One copy of each body in model context and session sources.
                                    if source is None:
                                        source = {**fields, "id": f"C{1 + sum(s.get('source') == 'campus' for s in sources)}"}
                                        sources.append(source)
                                    else:
                                        source.update(fields)
                                    if isinstance(args, CampusThreadRequest):
                                        source.update(thread_read=True)
                                    if not any(s["id"] == source["id"] for s in current_sources):
                                        current_sources.append(source)
                                    enriched.append(source)
                                result["results"] = enriched
                            elif isinstance(args, SearchRequest):
                                response = await within(self.search.search(args.query), deadline - reserve)
                                result = response.model_dump(mode="json")
                                enriched = []
                                for item in result["results"]:
                                    source = next((s for s in sources if s.get("source") != "campus" and s["url"] == item["url"] and s["is_mock"] == response.is_mock), None)
                                    if source is None:
                                        source = {**item, "id": f"W{1 + sum(s.get('source') != 'campus' for s in sources)}", "is_mock": response.is_mock}
                                        sources.append(source)
                                    else:
                                        source.update(item)
                                    if not any(s["id"] == source["id"] for s in current_sources):
                                        current_sources.append(source)
                                    enriched.append(source)
                                result["results"] = enriched
                            else:
                                source = next((s for s in sources if s["id"] == args.source_id and s.get("source") != "campus"), None)
                                if source is None:
                                    raise SearchError("unknown_source", "来源编号不存在，请先搜索。")
                                result = await within(self.reader.read(source), deadline - reserve)
                                source.update(page_read=True, page_truncated=result["truncated"])
                                if not any(s["id"] == source["id"] for s in current_sources):
                                    current_sources.append(source)
                            yield {"type": "tool_complete", **active_call, "result": result}
                        except (SearchError, CampusError, TimeoutError) as exc:
                            if isinstance(exc, TimeoutError):
                                retrieval_exhausted = True
                            code = exc.code if isinstance(exc, (SearchError, CampusError)) else "tool_budget_exhausted"
                            error = exc.message if isinstance(exc, (SearchError, CampusError)) else "检索时间预算已用完，停止当前搜索。"
                            if isinstance(exc, CampusError) and code in ("campus_auth_failed", "campus_credentials_invalid", "campus_login_required", "campus_credentials_write_failed"):
                                campus_allowed = False
                                system["content"] += "\n树洞认证现已失效，停止树洞调用，继续公开网页并说明限制。"
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
                if limit is not None and len(answer) > limit:
                    answer = short_failure(limit)
                history.append({"role": "assistant", "content": answer})
            # All tool-call messages are paired before reaching this commit.
            new_turn = history[len(base_history):]
            session.history.extend(new_turn)
            # Web-only requests must not resend earlier campus tool results or
            # answers derived from them. Preserve user conditions separately.
            if any(s.get("source") == "campus" for s in sources) and mode == "all":
                session.web_history.extend([{"role": "user", "content": question},
                    {"role": "assistant", "content": "本轮可能使用树洞资料；仅网页模式下省略该回答，请按用户条件重新核实。"}])
            else:
                session.web_history.extend(new_turn)
            session.sources = sources
            cited = citation_ids(answer)
            assistant = {"role": "assistant", "content": answer,
                         "sources": [s for s in sources if s["id"] in cited and not s["is_mock"]],
                         "warnings": warnings, "limited": limited, "reviewed": reviewed,
                         "status": "incomplete" if failed or limited else "complete",
                         "source_mode": mode, "skill": self.skill.name if used_skill else None, "plan": plan,
                         "end_reason": "error" if failed else "budget" if limited else "answered"}
            session.messages.extend([{"role": "user", "content": question}, assistant])
            metrics["elapsed_seconds"] = round(time.monotonic() - started, 3)
            yield {"type": "final", "session_id": session.id, "message": assistant,
                   "session_sources": sources, "tool_calls": calls, "campus_pages": campus_budget.pages, "metrics": metrics}
        finally:
            session.busy = False
