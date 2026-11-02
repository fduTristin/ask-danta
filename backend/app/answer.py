"""Question-independent publication checks and evidence for answer review."""

import json
import re
from typing import Annotated, Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field


class FactCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim: str = Field(min_length=1, max_length=400)
    source_id: str = Field(pattern=r'^[WC][1-9][0-9]*$')
    quote: str = Field(min_length=1, max_length=1600)
    qualification: str = Field(min_length=1, max_length=400)


class AnswerAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    corrections: list[Annotated[str, Field(min_length=1, max_length=800)]] = Field(max_length=8)
    required_actions: list[Literal['search_web', 'read_web', 'search_campus_posts', 'read_campus_thread']] = Field(default_factory=list, max_length=4)
    facts: list[FactCheck] = Field(default_factory=list, max_length=8)


def audit_fact_errors(audit: AnswerAudit, payload: dict) -> list[str]:
    errors = []
    evidence = {s['id']: s for s in payload['evidence']}
    if re.search(r'\d+(?:\.\d+)?\s*元|免费', payload['draft']) and not audit.facts and not audit.corrections:
        errors.append('回答包含费用结论，必须提供facts核对记录或明确指出无依据的费用断言。')
    for fact in audit.facts:
        source = evidence.get(fact.source_id, {})
        text = source.get('page_text', source.get('snippet', ''))
        if not normalized_text(fact.quote) or normalized_text(fact.quote) not in normalized_text(text):
            errors.append('facts中的原文摘录必须可在对应来源正文或摘要中找到，不得把草稿当作原文。')
    return errors


def model_view(value):
    """Opaque citation IDs are sufficient; database floor IDs are UI metadata."""
    if isinstance(value, list):
        return [model_view(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: model_view(item) for key, item in value.items() if key != 'floor_id'}
    if value.get('source') == 'campus':
        result['title'] = f"树洞 #{value.get('hole_id', '')} · 来源 {value.get('id', '')}"
        result['speaker_and_position'] = '未提供楼层顺序或是否楼主；只用来源编号引用'
    return result


def model_history(history: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in reversed(history):
        item = dict(item)
        if item['role'] == 'tool':
            try:
                data = json.loads(item['content'])
                if isinstance(data, dict):
                    for source in data.get('results', []):
                        sid = source.get('id')
                        if sid and sid in seen:
                            source.pop('snippet', None)
                            source.pop('content', None)
                            source['text_reference'] = '正文见后续同编号工具结果'
                        if sid:
                            seen.add(sid)
                item['content'] = json.dumps(model_view(data), ensure_ascii=False)
            except (ValueError, TypeError):
                pass
        result.append(item)
    return list(reversed(result))


def normalized_text(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if c.isalnum())


def copied_posts(answer: str, sources: list[dict]) -> list[str]:
    normalized = normalized_text(answer)
    return [s['id'] for s in sources if s.get('source') == 'campus'
            and len(body := normalized_text(s.get('snippet', ''))) >= 8 and body in normalized]


def retrieval_forbidden(question: str) -> bool:
    return bool(re.search(r'(?:不要|不再|不用|无需|禁止)(?:再)?(?:搜索|检索|查找|查阅)|只(?:依据|根据|用)(?:已有|现有)', question))


def citation_ids(text: str) -> set[str]:
    return set(re.findall(r"\[([WC][1-9][0-9]*)\]", text))


def character_limit(question: str) -> int | None:
    """Recognize explicit numeric Chinese character caps in the current request.

    Count the raw answer, including punctuation, whitespace and citation markers;
    this is conservative and avoids silently cutting sentences or references.
    Other natural-language constraints remain part of the model's review.
    """
    pattern = r"(?:最多|不超过|至多|上限(?:为)?|控制在)\s*(\d{1,5})\s*(?:个)?字|(\d{1,5})\s*字(?:以内|以下)"
    matches = list(re.finditer(pattern, question))
    if not matches:
        return None
    value = int(next(group for group in matches[-1].groups() if group is not None))
    return value if value > 0 else None


def answer_issues(answer: str, known: set[str], limit: int | None, sources: list[dict] = ()) -> list[dict]:
    issues = []
    unknown = citation_ids(answer) - known
    if unknown:
        issues.append({"code": "unknown_citations", "ids": sorted(unknown)})
    if limit is not None and len(answer) > limit:
        issues.append({"code": "answer_too_long", "actual": len(answer), "maximum": limit})
    copied = copied_posts(answer, sources)
    if copied:
        issues.append({'code': 'whole_post_copy', 'ids': copied, 'instruction': '用自己的话概括，不逐字复制整条帖子；仅更换标点也不算概括。'})
    return issues


def short_failure(limit: int) -> str:
    for text in ("本轮未能生成符合要求的回答，请缩小问题后重试。", "本轮未完成，请重试。", "未完成。", "…"):
        if len(text) <= limit:
            return text
    return ""


def review_payload(question: str, history: list[dict], sources: list[dict], turn_start: int,
                   draft: str, limit: int | None) -> dict:
    """Sources and successful reads are evidence; earlier assistant prose is not.

    The caller filters sources/history by the current data-source permission.
    Error records describe failures, never create a citation or a factual source.
    """
    known = {s["id"] for s in sources if not s["is_mock"]}
    evidence = {s["id"]: {key: value for key, value in s.items() if key in (
        "id", "source", "title", "url", "snippet", "published_at", "is_mock", "hole_id", "floor_id",
        "thread_read", "page_read", "page_truncated", "truncated")}
        for s in sources}
    errors = []
    actions = []
    tool_names = {}
    tool_arguments = {}
    for index, item in enumerate(history):
        for call in item.get("tool_calls", []):
            tool_names[call["id"]] = call["function"]["name"]
            try:
                tool_arguments[call['id']] = json.loads(call['function']['arguments'])
            except (ValueError, TypeError):
                tool_arguments[call['id']] = {}
        if item["role"] != "tool":
            continue
        try:
            result = json.loads(item["content"])
        except (ValueError, TypeError):
            continue
        if not isinstance(result, dict):
            continue
        if index >= turn_start:
            actions.append({"tool": tool_names.get(item.get("tool_call_id")),
                            "status": "error" if "error" in result else "complete",
                            "arguments": tool_arguments.get(item.get('tool_call_id'), {})})
        if index >= turn_start and "error" in result:
            errors.append({"tool": tool_names.get(item.get("tool_call_id")), **result["error"]})
        source = evidence.get(result.get("source_id"))
        if source is not None and "text" in result:
            source.pop('snippet', None)
            source.update(page_text=result["text"], page_read=True, page_truncated=result.get("truncated"))
    return {
        "question": question,
        "user_turns": [item["content"] for item in history if item["role"] == "user"],
        "previous_answer_for_reference_only": next((item.get("content") for item in reversed(history[:turn_start])
            if item["role"] == "assistant" and not item.get("tool_calls")), None),
        "evidence": model_view(list(evidence.values())), "current_tool_errors": errors, "current_tool_actions": actions,
        "allowed_citation_ids": sorted(known),
        "output_constraints": {"max_characters": limit, "draft_characters": len(draft)},
        "validation_errors": answer_issues(draft, known, limit, sources), "draft": draft,
    }
