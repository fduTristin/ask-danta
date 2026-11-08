"""Desktop access boundary and packaged resource behavior, without user data."""
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location("desktop_backend", Path(__file__).resolve().parents[1] / "desktop/backend.py")
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


def test_desktop_access_and_storage(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<html>desktop</html>")
    data = tmp_path / "profile"
    with TestClient(desktop.desktop_app(data, assets, "test-secret")) as client:
        assert client.get("/api/health").status_code == 403
        assert client.get("/").status_code == 403
        assert client.get("/api/settings", headers={"x-desktop-token": "wrong"}).status_code == 403
        client.headers["x-desktop-token"] = "test-secret"
        assert client.get("/api/health").status_code == 200
        response = client.get("/")
        assert "desktop" in response.text
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert client.get("/api/settings").status_code == 200
        assert client.get("/../settings.json").status_code == 404
    assert (data / "history/chat.sqlite3").exists()
