"""Search adapter. Fixtures are explicit; live failures never fall back to fixtures."""

import asyncio
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from .config import Settings


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(min_length=1, max_length=500)


class SearchResult(BaseModel):
    source: Literal["web"] = "web"
    title: str
    url: HttpUrl
    snippet: str
    published_at: str | None = None
    truncated: bool = False


class SearchResponse(BaseModel):
    query: str
    provider: Literal["mock", "tavily"]
    is_mock: bool
    notice: str
    results: list[SearchResult]


class SearchError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class TavilyItem(BaseModel):
    title: str = Field(min_length=1)
    url: HttpUrl
    content: str
    published_date: str | None = None


class TavilyPayload(BaseModel):
    results: list[TavilyItem]


class SearchService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    async def search(self, query: str) -> SearchResponse:
        if self.settings.search_provider == "mock":
            return SearchResponse(
                query=query, provider="mock", is_mock=True,
                notice="离线固定样例：未访问网络，内容与查询无关，不可作为办事依据。",
                results=[SearchResult(
                    title="校园办事指南（合成样例）",
                    url="https://example.invalid/campus-guide",
                    snippet="这是一条用于检查展示效果的合成记录。真实搜索将返回来源标题、链接、摘要和可用日期；此记录不包含实际办事要求。",
                )],
            )
        if not self.settings.search_configured:
            raise SearchError("search_not_configured", "请在项目根目录 .env 中填写 SEARCH_API_KEY 并重启服务。", 503)
        try:
            # An overall deadline also bounds a server that slowly streams bytes.
            async with asyncio.timeout(self.settings.search_timeout):
                response = await self.client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self.settings.search_api_key.get_secret_value()}"},
                    json={
                        "query": query, "search_depth": self.settings.search_depth, "topic": "general",
                        "max_results": self.settings.search_max_results,
                        "include_answer": False, "include_raw_content": False,
                        "include_published_date": True,
                    },
                    timeout=self.settings.search_timeout,
                )
            response.raise_for_status()
            payload = TavilyPayload.model_validate(response.json())
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise SearchError("search_timeout", "搜索超时，请稍后重试。", 504) from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                raise SearchError("search_auth_failed", "搜索服务认证失败，请检查 Tavily 密钥与权限。") from exc
            if code in (429, 432, 433):
                raise SearchError("search_rate_limited", "搜索服务限流或额度不足，请检查服务配额后重试。", 429) from exc
            raise SearchError("search_upstream_error", "搜索服务暂时不可用，请稍后重试。") from exc
        except httpx.RequestError as exc:
            raise SearchError("search_unreachable", "无法连接搜索服务，请检查网络后重试。") from exc
        except (ValueError, ValidationError) as exc:
            raise SearchError("search_invalid_response", "搜索服务返回了不符合预期的数据。") from exc

        results = []
        seen = set()
        for item in payload.results:
            url = str(item.url)
            if url in seen:
                continue
            seen.add(url)
            limit = self.settings.search_max_snippet_chars
            results.append(SearchResult(
                title=item.title, url=item.url, snippet=item.content[:limit],
                published_at=item.published_date,
                truncated=len(item.content) > limit,
            ))
            if len(results) == self.settings.search_max_results:
                break
        return SearchResponse(
            query=query, provider="tavily", is_mock=False,
            notice="实际网页搜索结果；日期仅在来源服务提供时展示，检索结果不代表全部资料。",
            results=results,
        )
