"""DeepSeek Chat Completions adapter; upstream error bodies stay private."""

import asyncio
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .config import Settings


class ModelError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, *, finish_reason: str | None = None, usage: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.finish_reason, self.usage = finish_reason, usage or {}


class FunctionCall(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arguments: str = Field(max_length=10000)


class ToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    type: Literal["function"]
    function: FunctionCall


class AssistantMessage(BaseModel):
    role: Literal["assistant"]
    content: str | None = Field(default=None, max_length=60000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=32)
    reasoning_content: str | None = None
    usage: dict[str, int] = Field(default_factory=dict, exclude=True)

    @field_validator("tool_calls", mode="before")
    @classmethod
    def nullable_tools(cls, value):
        return [] if value is None else value

    @model_validator(mode="after")
    def valid_message(self):
        if not self.tool_calls and not (self.content and self.content.strip()):
            raise ValueError("Empty model message")
        if len({call.id for call in self.tool_calls}) != len(self.tool_calls):
            raise ValueError("Duplicate tool call IDs")
        return self

    def wire(self) -> dict:
        data = self.model_dump(exclude_none=True)
        data["content"] = self.content
        if not self.tool_calls:
            data.pop("tool_calls")
        return data


class Choice(BaseModel):
    # Inspect the termination reason before validating the message. Truncated
    # thinking responses can legitimately contain no final answer at all.
    message: dict
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter", "insufficient_system_resource", "aborted"]


class Completion(BaseModel):
    choices: list[Choice] = Field(min_length=1, max_length=1)
    usage: dict = Field(default_factory=dict)


class ModelService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client

    async def complete(self, messages: list[dict], tools: list[dict], *, thinking: Literal["enabled", "disabled"] | None = None) -> AssistantMessage:
        if not self.settings.model_api_key.get_secret_value():
            raise ModelError("model_not_configured", "请在设置中填写模型 API Key。", 503)
        thinking = thinking or self.settings.model_thinking
        # Fast review can request tools without producing reasoning. When its
        # result rejoins the thinking loop, DeepSeek still requires this field
        # on assistant tool calls. Restored history also intentionally omits
        # private reasoning. Normalize only the wire copy, preserving any real
        # reasoning from the current turn and never persisting a fabricated trace.
        wire_messages = [
            {**message, "reasoning_content": message.get("reasoning_content") or ""}
            if thinking == "enabled" and message.get("role") == "assistant" and message.get("tool_calls")
            else message
            for message in messages
        ]
        body = {
            "model": self.settings.model_name, "messages": wire_messages,
            "stream": False, "thinking": {"type": thinking},
            "max_tokens": self.settings.model_max_tokens,
        }
        if thinking == "enabled":
            body["reasoning_effort"] = self.settings.model_reasoning_effort
        if tools:
            body["tools"] = tools
        try:
            async with asyncio.timeout(self.settings.model_timeout_seconds):
                response = await self.client.post(
                    str(self.settings.model_base_url).rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.model_api_key.get_secret_value()}"},
                    json=body,
                    timeout=self.settings.model_timeout_seconds,
                )
            response.raise_for_status()
            payload = Completion.model_validate(response.json())
            choice = payload.choices[0]
            usage = {key: value for key, value in payload.usage.items()
                             if key in ("prompt_tokens", "completion_tokens", "total_tokens",
                                        "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
                             and type(value) is int and value >= 0}
            failures = {
                "length": ("model_output_truncated", "模型输出达到长度限制，未能完整返回。可在设置中增加最大输出 Token 数，或降低思考强度后重试。"),
                "content_filter": ("model_content_filtered", "模型服务未返回本次内容。请调整问题后重试。"),
                "insufficient_system_resource": ("model_interrupted", "模型服务资源不足，本次生成中断，请稍后重试。"),
                "aborted": ("model_interrupted", "模型服务中断了本次生成，请稍后重试。"),
            }
            if choice.finish_reason in failures:
                code, detail = failures[choice.finish_reason]
                raise ModelError(code, detail, finish_reason=choice.finish_reason, usage=usage)
            content = choice.message.get("content")
            if choice.message.get("role") == "assistant" and (content is None or isinstance(content, str) and not content.strip()) and not choice.message.get("tool_calls"):
                raise ModelError("model_empty_response", "模型没有返回回答内容，请重试。", finish_reason=choice.finish_reason, usage=usage)
            try:
                message = AssistantMessage.model_validate(choice.message)
            except ValidationError:
                raise ModelError("model_invalid_response", "模型返回的数据格式无效，请重试。", finish_reason=choice.finish_reason, usage=usage) from None
            if (choice.finish_reason == "tool_calls") != bool(message.tool_calls):
                raise ModelError("model_invalid_response", "模型返回的工具调用状态不一致，请重试。", finish_reason=choice.finish_reason, usage=usage)
            message.usage = usage
            return message
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelError("model_timeout", "模型响应超时，本轮未能完成回答。", 504) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise ModelError("model_auth_failed", "模型认证失败，请检查 DeepSeek 密钥和权限。") from exc
            if status == 429:
                raise ModelError("model_rate_limited", "模型服务限流或额度不足，请稍后重试。", 429) from exc
            raise ModelError("model_upstream_error", f"模型服务请求失败（HTTP {status}），请检查模型配置或稍后重试。") from exc
        except httpx.RequestError as exc:
            raise ModelError("model_unreachable", "无法连接模型服务，请检查网络。") from exc
        except (ValueError, ValidationError) as exc:
            raise ModelError("model_invalid_response", "模型返回了不完整或不符合预期的数据。") from exc
