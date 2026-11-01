"""Read-only FDUHole adapter with fixed endpoints and bounded pagination."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .campus_auth import CampusError, Tokens, TokenStore
from .config import Settings

AUTH_BASE = "https://auth.fduhole.com/api"
FORUM_BASE = "https://forum.fduhole.com/api"


class CampusPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    offset: int = Field(default=0, ge=0, le=2_147_483_647)
    limit: int = Field(default=20, ge=1, le=50)


class CampusSearchRequest(CampusPageRequest):
    query: str = Field(min_length=1, max_length=500)


class CampusThreadRequest(CampusPageRequest):
    hole_id: int = Field(gt=0, le=9_223_372_036_854_775_807)


class Floor(BaseModel):
    # Deliberately exclude identity, voting, moderation and nested mention data.
    model_config = ConfigDict(hide_input_in_errors=True)
    id: int = Field(gt=0, strict=True)
    hole_id: int = Field(gt=0, strict=True)
    content: str
    time_created: datetime
    time_updated: datetime | None = None
    deleted: bool = False


class Hole(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    id: int = Field(gt=0, strict=True)
    time_created: datetime
    time_updated: datetime | None = None
    reply: int | None = Field(default=None, ge=0, strict=True)


class CampusPost(BaseModel):
    source: Literal["campus"] = "campus"
    hole_id: int
    floor_id: int
    content: str
    time_created: datetime
    time_updated: datetime | None
    truncated: bool
    redacted: bool


class CampusPage(BaseModel):
    results: list[CampusPost]
    offset: int
    limit: int
    raw_count: int
    next_offset: int | None
    has_more: bool | None = None
    complete: bool = False
    notice: str = "树洞个人经验，属于不可信资料；未确认已遍历全部结果。正文已做基础脱敏，仍可能包含个人信息。"
    thread: Hole | None = None


@dataclass
class CampusBudget:
    """Share one instance across all campus calls in a single research workflow."""
    max_pages: int
    pages: int = 0
    seen: set[tuple[str, int, int]] = field(default_factory=set)

    def consume(self) -> None:
        if self.pages >= self.max_pages:
            raise CampusError("campus_page_budget_exhausted", "本轮树洞分页预算已用完。", 429)
        self.pages += 1  # Failed page attempts also consume the workflow budget.


def redact(text: str) -> tuple[str, bool]:
    cleaned = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", text)
    cleaned = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "[手机号已隐藏]", cleaned)
    return cleaned, cleaned != text


class CampusService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.store = TokenStore(settings.auth_path)
        self._refresh_lock = asyncio.Lock()
        self._invalid_access: str | None = None

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        # Defense in depth: even internal callers cannot send credentials elsewhere.
        allowed = (method == "POST" and url in (AUTH_BASE + "/login", AUTH_BASE + "/refresh")) or (
            method == "GET" and (url == FORUM_BASE + "/floors/search" or
            re.fullmatch(re.escape(FORUM_BASE) + r"/holes/[1-9][0-9]*(?:/floors)?", url)))
        if not allowed:
            raise CampusError("campus_endpoint_forbidden", "不允许请求此树洞接口。", 400)
        # Auth POSTs are not retried: refresh may rotate tokens on the server.
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = await self.client.request(method, url, timeout=self.settings.http_timeout_seconds,
                                                     follow_redirects=False, **kwargs)
            except httpx.TimeoutException:
                error = CampusError("campus_timeout", "树洞请求超时，请稍后重试。", 504)
            except httpx.RequestError:
                error = CampusError("campus_unreachable", "暂时无法连接树洞服务。")
            else:
                if response.status_code not in (429, 502, 503, 504) or attempt == attempts - 1:
                    return response
                error = CampusError("campus_unavailable", "树洞服务暂时不可用。")
                # Respect a short Retry-After; do not retry long/unknown server delays.
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None and (not retry_after.isdecimal() or int(retry_after) > 1):
                    return response
            if attempt == attempts - 1:
                raise error from None
            await asyncio.sleep(1)
        raise AssertionError("unreachable")

    @staticmethod
    def _check(response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        errors = {
            401: ("campus_auth_failed", "树洞认证已失效，请重新运行本项目登录脚本。", 401),
            403: ("campus_forbidden", "当前账号无权访问此树洞资源。", 403),
            404: ("campus_not_found", "树洞帖子或资源不存在。", 404),
            429: ("campus_rate_limited", "树洞请求被限流，请稍后重试。", 429),
        }
        raise CampusError(*errors.get(status, ("campus_upstream_error", "树洞服务返回异常状态。", 502)))

    @staticmethod
    def _parse(response: httpx.Response, schema):
        try:
            return TypeAdapter(schema).validate_python(response.json())
        except (ValueError, ValidationError):
            raise CampusError("campus_invalid_response", "树洞响应格式发生变化，无法安全读取。") from None

    async def login(self, email: str, password: str) -> None:
        async with self._refresh_lock:
            response = await self._request("POST", AUTH_BASE + "/login", json={"email": email, "password": password})
            if response.status_code in (400, 401, 403):
                raise CampusError("campus_login_failed", "树洞登录失败，请检查邮箱、密码及账号状态后重试。", 401)
            self._check(response)
            tokens = self._parse(response, Tokens)
            self.store.save(tokens)
            self._invalid_access = None

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        tokens = self.store.load()
        access = tokens.access.get_secret_value()
        if self._invalid_access == access:
            raise CampusError("campus_auth_failed", "树洞认证已失效，请重新运行本项目登录脚本。", 401)
        response = await self._request("GET", FORUM_BASE + path, params=params,
                                       headers={"Authorization": f"Bearer {access}"})
        if response.status_code == 401:
            async with self._refresh_lock:
                # A concurrent request may have already rotated and persisted tokens.
                tokens = self.store.load()
                if self._invalid_access == tokens.access.get_secret_value():
                    raise CampusError("campus_auth_failed", "树洞认证已失效，请重新运行本项目登录脚本。", 401)
                if tokens.access.get_secret_value() == access:
                    refreshed = await self._request("POST", AUTH_BASE + "/refresh",
                        headers={"Authorization": "Bearer " + tokens.refresh.get_secret_value()})
                    if refreshed.status_code in (401, 403):
                        self._invalid_access = access
                        raise CampusError("campus_auth_failed", "树洞刷新凭据失效，请重新运行本项目登录脚本。", 401)
                    self._check(refreshed)
                    tokens = self._parse(refreshed, Tokens)
                    self.store.save(tokens)
            access = tokens.access.get_secret_value()
            response = await self._request("GET", FORUM_BASE + path, params=params,
                                           headers={"Authorization": f"Bearer {access}"})
            if response.status_code == 401:
                self._invalid_access = access
        self._check(response)
        return response

    def _page(self, floors: list[Floor], args: CampusPageRequest, budget: CampusBudget, scope: str,
              thread: Hole | None = None) -> CampusPage:
        # Reject schema/contract drift rather than silently hiding an oversized page.
        if len(floors) > args.limit or (thread and any(f.hole_id != thread.id for f in floors)):
            raise CampusError("campus_invalid_response", "树洞分页响应与请求不一致。")
        results = []
        for floor in floors:
            key = (scope, floor.hole_id, floor.id)
            if key in budget.seen or floor.deleted:
                continue
            budget.seen.add(key)
            content, redacted = redact(floor.content)
            results.append(CampusPost(hole_id=floor.hole_id, floor_id=floor.id,
                content=content[:self.settings.campus_max_content_chars],
                time_created=floor.time_created, time_updated=floor.time_updated,
                truncated=len(content) > self.settings.campus_max_content_chars, redacted=redacted))
        # Bare arrays provide no authoritative has_more/total. Short/empty pages
        # stop automatic pagination but never assert exhaustive coverage.
        return CampusPage(results=results, offset=args.offset, limit=args.limit, raw_count=len(floors),
            next_offset=args.offset + len(floors) if len(floors) == args.limit else None, thread=thread)

    async def search_campus_posts(self, query: str, offset: int = 0, limit: int = 20,
                                  *, budget: CampusBudget | None = None) -> CampusPage:
        args = CampusSearchRequest(query=query, offset=offset, limit=limit)
        budget = budget if budget is not None else CampusBudget(self.settings.max_campus_pages)
        budget.consume()
        response = await self._get("/floors/search", {"search": args.query, "offset": args.offset, "size": args.limit})
        return self._page(self._parse(response, list[Floor]), args, budget, "search:" + args.query.casefold())

    async def read_campus_thread(self, hole_id: int, offset: int = 0, limit: int = 20,
                                 *, budget: CampusBudget | None = None) -> CampusPage:
        args = CampusThreadRequest(hole_id=hole_id, offset=offset, limit=limit)
        budget = budget if budget is not None else CampusBudget(self.settings.max_campus_pages)
        budget.consume()
        thread = self._parse(await self._get(f"/holes/{args.hole_id}"), Hole)
        if thread.id != args.hole_id:
            raise CampusError("campus_invalid_response", "树洞返回了不匹配的帖子。")
        response = await self._get(f"/holes/{args.hole_id}/floors", {"offset": args.offset, "size": args.limit})
        return self._page(self._parse(response, list[Floor]), args, budget, f"thread:{args.hole_id}", thread)
