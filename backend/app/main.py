from contextlib import asynccontextmanager
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
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
from .sessions import SessionStore, SessionStorageError, SessionUpdate


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
            app.state.store = SessionStore(settings.sessions_path)
            app.state.sessions = app.state.store.load()
            app.state.active_tasks = {}
            app.state.cancellations = {}
            try:
                yield
            finally:
                tasks = list(app.state.active_tasks.values())
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                app.state.sessions.clear()
                app.state.store.close()

    app = FastAPI(title="问问旦挞", version="0.6.0", lifespan=lifespan)

    @app.exception_handler(SessionStorageError)
    async def storage_error_handler(request: Request, exc: SessionStorageError):
        return JSONResponse(status_code=503, content={"error": {"code": "history_storage_error", "message": str(exc)}})

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
            "status": "ok", "stage": 6,
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
            raise HTTPException(404, "会话不存在或已删除，请选择其他会话。")
        return session

    def ensure_idle(session: Session):
        if session.busy:
            raise HTTPException(409, "本会话正在回答，请等待完成或停止请求后重试。")

    @app.post("/api/sessions", status_code=201)
    async def create_session():
        session = Session()
        app.state.store.save(session)
        app.state.sessions[session.id] = session
        return session.public()

    @app.get("/api/sessions")
    async def list_sessions():
        sessions = [s for s in app.state.sessions.values() if s.messages or s.pending_question or s.title != "新对话"]
        return {"sessions": [s.summary() for s in sorted(sessions, key=lambda s: s.updated_at, reverse=True)]}

    @app.patch("/api/sessions/{session_id}")
    async def update_session(session_id: UUID, body: SessionUpdate):
        session = get_session(session_id)
        ensure_idle(session)
        changed = deepcopy(session)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(changed, key, value)
        changed.updated_at = datetime.now(timezone.utc).isoformat()
        app.state.store.save(changed)
        session.__dict__.update(changed.__dict__)
        return session.public()

    @app.get("/api/sessions/{session_id}")
    async def read_session(session_id: UUID):
        return get_session(session_id).public()

    @app.post("/api/sessions/{session_id}/clear")
    async def clear_session(session_id: UUID):
        session = get_session(session_id)
        ensure_idle(session)
        changed = deepcopy(session)
        changed.history.clear()
        changed.web_history.clear()
        changed.messages.clear()
        changed.sources.clear()
        changed.pending_question = None
        changed.interrupted = False
        changed.updated_at = datetime.now(timezone.utc).isoformat()
        app.state.store.save(changed)
        session.__dict__.update(changed.__dict__)
        return session.public()

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: UUID):
        session = get_session(session_id)
        ensure_idle(session)
        app.state.store.delete(session.id)
        del app.state.sessions[session.id]

    @app.post("/api/sessions/{session_id}/cancel", status_code=202)
    async def cancel_session(session_id: UUID):
        session = get_session(session_id)
        flag = app.state.cancellations.get(session.id)
        if flag:
            flag.set()
        task = app.state.active_tasks.get(session.id)
        if task:
            task.cancel()
        return {"requested": session.busy}

    @app.post("/api/sessions/{session_id}/chat")
    async def chat(session_id: UUID, body: ChatRequest):
        session = get_session(session_id)
        ensure_idle(session)
        if not settings.model_api_key.get_secret_value():
            raise ModelError("model_not_configured", "请在本地 .env 填写 MODEL_API_KEY 并重启服务。", 503)
        before = deepcopy(session)
        session.pending_question = body.message
        session.interrupted = False
        session.source_preference = body.source_preference
        session.updated_at = datetime.now(timezone.utc).isoformat()
        if session.title == "新对话":
            session.title = body.message[:32]
        try:
            app.state.store.save(session)
        except SessionStorageError:
            session.__dict__.update(before.__dict__)
            raise
        session.busy = True
        cancellation = asyncio.Event()
        app.state.cancellations[session.id] = cancellation
        released = False

        def release():
            nonlocal released
            # Background cleanup can run after a new request has started.
            # Releasing this request twice must not unlock that newer request.
            if not released:
                released = True
                session.busy = False
                session.interrupted = bool(session.pending_question)
                app.state.active_tasks.pop(session.id, None)
                app.state.cancellations.pop(session.id, None)
                try:
                    app.state.store.save(session)
                except SessionStorageError:
                    # The durable pending marker remains; do not fabricate success.
                    pass

        async def stream():
            events = app.state.agent.events(session, body.message, body.source_mode)
            app.state.active_tasks[session.id] = asyncio.current_task()
            try:
                if cancellation.is_set():
                    return
                async for event in events:
                    if event["type"] == "final":
                        session.pending_question = None
                        session.interrupted = False
                        session.updated_at = datetime.now(timezone.utc).isoformat()
                        try:
                            app.state.store.save(session)
                        except SessionStorageError as exc:
                            session.history = before.history
                            session.web_history = before.web_history
                            session.messages = before.messages
                            session.sources = before.sources
                            session.pending_question = body.message
                            yield "data: " + json.dumps({"type": "error", "error": {"message": str(exc)}}, ensure_ascii=False) + "\n\n"
                            return
                    yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            except asyncio.CancelledError:
                # Explicit stop ends the SSE response cleanly; disconnect cancellation
                # still belongs to Starlette's response task group.
                if not cancellation.is_set():
                    raise
            finally:
                await events.aclose()
                release()

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(release),
        )

    return app
