"""Load the repository-owned research skill; no user-controlled skill paths."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import ROOT


@dataclass(frozen=True)
class ResearchSkill:
    name: str
    description: str
    instructions: str


def load_research_skill() -> ResearchSkill:
    text = (ROOT / "skills/ask-danta-research/SKILL.md").read_text(encoding="utf-8")
    # This bundled skill uses a deliberately small, single-line YAML header.
    header, body = text.removeprefix("---\n").split("\n---\n", 1)
    metadata = dict(line.split(": ", 1) for line in header.splitlines())
    if metadata.get("name") != "ask-danta-research" or not metadata.get("description") or not body.strip():
        raise ValueError("Invalid bundled campus research skill")
    return ResearchSkill(metadata["name"], metadata["description"], body.strip())


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    questions: list[str] = Field(min_length=1, max_length=5)
    gaps: list[str] = Field(default_factory=list, max_length=5)
    next_action: Literal["search", "read_context", "answer", "clarify"]
    sources: list[Literal["web", "campus"]] = Field(max_length=2)

