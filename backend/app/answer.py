"""Question-independent publication checks and evidence for answer review."""

import json
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class AnswerAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    corrections: list[Annotated[str, Field(min_length=1, max_length=800)]] = Field(max_length=8)


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


def answer_issues(answer: str, known: set[str], limit: int | None) -> list[dict]:
    issues = []
    unknown = citation_ids(answer) - known
    if unknown:
        issues.append({"code": "unknown_citations", "ids": sorted(unknown)})
    if limit is not None and len(answer) > limit:
        issues.append({"code": "answer_too_long", "actual": len(answer), "maximum": limit})
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
    tool_names = {}
    for index, item in enumerate(history):
        for call in item.get("tool_calls", []):
            tool_names[call["id"]] = call["function"]["name"]
        if item["role"] != "tool":
            continue
        try:
            result = json.loads(item["content"])
        except (ValueError, TypeError):
            continue
        if not isinstance(result, dict):
            continue
        if index >= turn_start and "error" in result:
            errors.append({"tool": tool_names.get(item.get("tool_call_id")), **result["error"]})
        source = evidence.get(result.get("source_id"))
        if source is not None and "text" in result:
            source.update(page_text=result["text"], page_read=True, page_truncated=result.get("truncated"))
    return {
        "question": question,
        "user_turns": [item["content"] for item in history if item["role"] == "user"],
        "previous_answer_for_reference_only": next((item.get("content") for item in reversed(history[:turn_start])
            if item["role"] == "assistant" and not item.get("tool_calls")), None),
        "evidence": list(evidence.values()), "current_tool_errors": errors,
        "allowed_citation_ids": sorted(known),
        "output_constraints": {"max_characters": limit, "draft_characters": len(draft)},
        "validation_errors": answer_issues(draft, known, limit), "draft": draft,
    }
