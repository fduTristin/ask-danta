"""Private desktop server. Parent stdin owns its lifetime and session token."""
import json
import secrets
import socket
import sys
import threading
from pathlib import Path

import uvicorn
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import ROOT, Settings
from app.main import create_app


def desktop_app(data: Path, assets: Path, token: str):
    data.mkdir(parents=True, exist_ok=True)
    application = create_app(Settings(
        campus_auth_file=data / "campus-tokens.json",
        session_db_file=data / "history/chat.sqlite3",
    ), settings_file=data / "settings.json")

    @application.middleware("http")
    async def authorize(request, call_next):
        if not secrets.compare_digest(request.headers.get("x-desktop-token", ""), token):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://image.fduhole.com; connect-src 'self'; "
            "object-src 'none'; frame-src 'none'; base-uri 'none'"
        )
        return response

    application.mount("/", StaticFiles(directory=assets, html=True), name="frontend")
    return application


def main():
    config = json.loads(sys.stdin.readline())
    application = desktop_app(Path(config["data"]), ROOT / "frontend/dist", config["token"])
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(application, log_level="error", access_log=False))

    def watch_parent():
        sys.stdin.read()
        server.should_exit = True

    threading.Thread(target=watch_parent, daemon=True).start()
    print(json.dumps({"port": sock.getsockname()[1]}), flush=True)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
