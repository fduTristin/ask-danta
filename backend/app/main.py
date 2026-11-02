from contextlib import asynccontextmanager
import asyncio
import json
from uuid import UUID

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from .config import Settings
from .search import SearchError, SearchRequest, SearchResponse, SearchService
from .model import ModelError, ModelService
from .agent import Agent, ChatRequest, Session
from .campus import CampusService, CampusPage, CampusSearchRequest, CampusThreadRequest
from .campus_auth import CampusError, CampusLoginRequest


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=settings.http_timeout_seconds, transport=transport,
            follow_redirects=False, trust_env=False,
        ) as client:
            app.state.search = SearchService(settings, client)
            app.state.campus = CampusService(settings, client)
            app.state.agent = Agent(settings, ModelService(settings, client), app.state.search, campus=app.state.campus)
            app.state.sessions = {}
            yield
            app.state.sessions.clear()

    app = FastAPI(title="Campus Agent", version="0.5.0", lifespan=lifespan)

    @app.exception_handler(SearchError)
    @app.exception_handler(ModelError)
    @app.exception_handler(CampusError)
    async def search_error_handler(request: Request, exc: SearchError):
        # Never forward upstream responses, request headers, or credentials.
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        if request.url.path == "/api/campus/login":
            # FastAPI's default validation errors may include raw request input,
            # including the whole body for malformed JSON. Never echo login data.
            return JSONResponse(status_code=422, content={"error": {
                "code": "campus_invalid_login", "message": "请输入有效邮箱和非空密码。",
            }}, headers={"Cache-Control": "no-store"})
        return await request_validation_exception_handler(request, exc)

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok", "stage": 5,
            "model": {
                "name": settings.model_name,
                "configured": bool(settings.model_api_key.get_secret_value()),
                "available": False,
                "chat_enabled": bool(settings.model_api_key.get_secret_value()),
                "thinking": settings.model_thinking,
                "max_tokens": settings.model_max_tokens,
                "answer_review_enabled": settings.answer_review_enabled,
            },
            "search": {
                "provider": settings.search_provider,
                "configured": settings.search_configured,
                "is_mock": settings.search_provider == "mock",
            },
            "campus": {"credentials_present": settings.auth_path.is_file(), "available": False,
                       "auth_state": app.state.campus.auth_state(),
                       "tools_enabled": app.state.campus.auth_state() == "configured"},
            "skills": [app.state.agent.skill.name],
            "budgets": {
                "http_timeout_seconds": settings.http_timeout_seconds,
                "model_timeout_seconds": settings.model_timeout_seconds,
                "search_timeout_seconds": settings.search_timeout,
                "max_tool_calls": settings.max_tool_calls,
                "max_campus_pages": settings.max_campus_pages,
                "request_budget_seconds": settings.request_budget_seconds,
            },
        }

    @app.post("/api/search", response_model=SearchResponse)
    async def search(body: SearchRequest, request: Request):
        return await request.app.state.search.search(body.query)

    @app.post("/api/campus/search", response_model=CampusPage)
    async def campus_search(body: CampusSearchRequest, request: Request):
        return await campus_within_budget(request.app.state.campus.search_campus_posts(**body.model_dump()))

    @app.post("/api/campus/login")
    async def campus_login(body: CampusLoginRequest, request: Request):
        await campus_within_budget(request.app.state.campus.login(body.email, body.password.get_secret_value()))
        return JSONResponse(content={"authenticated": True, "message": "登录成功，凭据已保存在本机。"},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/campus/thread", response_model=CampusPage)
    async def campus_thread(body: CampusThreadRequest, request: Request):
        return await campus_within_budget(request.app.state.campus.read_campus_thread(**body.model_dump()))

    async def campus_within_budget(operation):
        try:
            async with asyncio.timeout(settings.request_budget_seconds):
                return await operation
        except TimeoutError:
            raise CampusError("campus_request_budget_exhausted", "树洞请求已达到总时长预算。", 504) from None

    def get_session(session_id: UUID) -> Session:
        session = app.state.sessions.get(str(session_id))
        if session is None:
            raise HTTPException(404, "会话不存在或服务已重启，请新建会话。")
        return session

    def ensure_idle(session: Session):
        if session.busy:
            raise HTTPException(409, "本会话正在回答，请等待完成或停止请求后重试。")

    @app.post("/api/sessions", status_code=201)
    async def create_session():
        session = Session()
        app.state.sessions[session.id] = session
        return session.public()

    @app.get("/api/sessions/{session_id}")
    async def read_session(session_id: UUID):
        return get_session(session_id).public()

    @app.post("/api/sessions/{session_id}/clear")
    async def clear_session(session_id: UUID):
        session = get_session(session_id)
        ensure_idle(session)
        session.history.clear()
        session.web_history.clear()
        session.messages.clear()
        session.sources.clear()
        return session.public()

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: UUID):
        session = get_session(session_id)
        ensure_idle(session)
        del app.state.sessions[session.id]

    @app.post("/api/sessions/{session_id}/chat")
    async def chat(session_id: UUID, body: ChatRequest):
        session = get_session(session_id)
        ensure_idle(session)
        if not settings.model_api_key.get_secret_value():
            raise ModelError("model_not_configured", "请在本地 .env 填写 MODEL_API_KEY 并重启服务。", 503)
        session.busy = True
        released = False

        def release():
            nonlocal released
            # Background cleanup can run after a new request has started.
            # Releasing this request twice must not unlock that newer request.
            if not released:
                released = True
                session.busy = False

        async def stream():
            events = app.state.agent.events(session, body.message, body.source_mode)
            try:
                async for event in events:
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            finally:
                await events.aclose()
                release()

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(release),
        )

    return app
