"""Keep every application's history database away from local user data."""
import pytest
from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_history(monkeypatch, tmp_path):
    monkeypatch.setattr(Settings, "sessions_path", property(
        lambda self: self.session_db_file if self.session_db_file.is_absolute()
        else tmp_path / "history" / "chat.sqlite3"
    ))
