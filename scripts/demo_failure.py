"""Loopback browser demo: synthetic expired campus auth, real model and web.

Build frontend first. No project campus credential is read or overwritten.
Run: uv run --frozen python scripts/demo_failure.py --port 8002
"""

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.config import Settings
from app.runtime_settings import load_settings
from app.main import create_app


class ExpiredCampusTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.live = httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host in ("forum.fduhole.com", "auth.fduhole.com"):
            return httpx.Response(401, json={"detail": "synthetic expiry demo"})
        return await self.live.handle_async_request(request)

    async def aclose(self):
        await self.live.aclose()


def build_demo(settings: Settings, token_path: Path) -> FastAPI:
    token_path.write_text(json.dumps({"access": "demo-invalid-access", "refresh": "demo-invalid-refresh"}))
    config = settings.model_copy(update={
        "campus_auth_file": token_path,
        "session_db_file": token_path.parent / "history" / "chat.sqlite3",
    })
    app = create_app(config, transport=ExpiredCampusTransport())
    dist = ROOT / "frontend/dist"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html = (dist / "index.html").read_text(encoding="utf-8")
        banner = ('<style>body{height:100dvh;display:flex;flex-direction:column}'
                  'body>aside{flex-shrink:0}#root{flex:1;min-height:0}#root>.app{height:100%}</style>'
                  '<aside role="status" style="padding:16px;background:#fff1c2;color:#3e310e;text-align:center">'
                  '模拟认证失效演示 · 树洞固定返回 401；模型和网页搜索使用真实服务。'
                  '独立演示凭据，不修改你的登录状态。</aside>')
        return html.replace("<body>", "<body>" + banner, 1)

    @app.get("/danta-logo.webp", include_in_schema=False)
    async def logo():
        return FileResponse(dist / "danta-logo.webp", media_type="image/webp")

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    if not (ROOT / "frontend/dist/index.html").is_file():
        parser.error("Build frontend first: npm --prefix frontend run build")
    with tempfile.TemporaryDirectory(prefix="campus-failure-demo-") as temp:
        app = build_demo(load_settings(), Path(temp) / "synthetic-tokens.json")
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
