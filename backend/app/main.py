from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .search import SearchError, SearchRequest, SearchResponse, SearchService


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_seconds, transport=transport,
            follow_redirects=False,
        ) as client:
            app.state.search = SearchService(settings, client)
            yield

    app = FastAPI(title="Campus Agent", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(SearchError)
    async def search_error_handler(request: Request, exc: SearchError):
        # Never forward upstream responses, request headers, or credentials.
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok", "stage": 1,
            "model": {
                "name": settings.model_name,
                "configured": bool(settings.model_api_key.get_secret_value()),
                "available": False,
            },
            "search": {
                "provider": settings.search_provider,
                "configured": settings.search_configured,
                "is_mock": settings.search_provider == "mock",
            },
            "campus": {"credentials_present": settings.auth_path.is_file(), "available": False},
            "budgets": {
                "http_timeout_seconds": settings.http_timeout_seconds,
                "max_tool_calls": settings.max_tool_calls,
                "max_campus_pages": settings.max_campus_pages,
                "request_budget_seconds": settings.request_budget_seconds,
            },
        }

    @app.post("/api/search", response_model=SearchResponse)
    async def search(body: SearchRequest, request: Request):
        return await request.app.state.search.search(body.query)

    return app
