from pathlib import Path
from typing import Literal
import os

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_FIELDS = ("backend_port", "frontend_port", "campus_auth_file", "session_db_file")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", hide_input_in_errors=True,
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        # User settings come exclusively from RuntimeSettingsStore. Only process
        # deployment variables are supported; legacy .env files are never read.
        def deployment_environment():
            return {name: os.environ[name.upper()] for name in DEPLOYMENT_FIELDS if name.upper() in os.environ}
        return init_settings, deployment_environment

    model_base_url: HttpUrl = "https://api.deepseek.com"
    model_name: str = Field(default="deepseek-flash", min_length=1, max_length=200)
    model_api_key: SecretStr = Field(default=SecretStr(""), max_length=8192)
    model_thinking: Literal["enabled", "disabled"] = "disabled"
    model_reasoning_effort: Literal["low", "high", "max"] = "low"
    model_max_tokens: int = Field(default=4096, ge=256, le=32768)
    model_timeout_seconds: float = Field(default=45, gt=0, le=300)
    search_timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    answer_review_enabled: bool = True
    search_provider: Literal["mock", "tavily"] = "mock"
    search_api_key: SecretStr = Field(default=SecretStr(""), max_length=8192)
    search_depth: Literal["basic", "advanced"] = "advanced"
    search_max_results: int = Field(default=5, ge=1, le=10)
    search_max_snippet_chars: int = Field(default=2000, ge=100, le=10000)
    campus_auth_file: Path = Path(".private/campus-tokens.json")
    session_db_file: Path = Path(".private/history/chat.sqlite3")
    campus_max_content_chars: int = Field(default=4000, ge=100, le=12000)
    http_timeout_seconds: float = Field(default=15, gt=0, le=120)
    max_tool_calls: int = Field(default=12, ge=1, le=30)
    max_campus_pages: int = Field(default=8, ge=1, le=20)
    request_budget_seconds: float = Field(default=150, gt=0, le=600)
    backend_port: int = Field(default=8000, ge=1024, le=65535)
    frontend_port: int = Field(default=5173, ge=1024, le=65535)

    @field_validator("model_base_url")
    @classmethod
    def plain_endpoint(cls, value):
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("Use a base URL without credentials, query or fragment")
        return value

    @field_validator("model_name")
    @classmethod
    def nonempty_model(cls, value):
        if not value.strip():
            raise ValueError("Model name is required")
        return value.strip()

    @field_validator("model_api_key", "search_api_key", mode="before")
    @classmethod
    def trim_key(cls, value):
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def different_ports(self):
        if self.backend_port == self.frontend_port:
            raise ValueError("BACKEND_PORT and FRONTEND_PORT must differ")
        return self

    @property
    def sessions_path(self) -> Path:
        path = self.session_db_file.expanduser()
        return path if path.is_absolute() else ROOT / path

    @property
    def auth_path(self) -> Path:
        path = self.campus_auth_file.expanduser()
        return path if path.is_absolute() else ROOT / path

    @property
    def search_configured(self) -> bool:
        return self.search_provider == "mock" or bool(self.search_api_key.get_secret_value())

    @property
    def search_timeout(self) -> float:
        return self.search_timeout_seconds or self.http_timeout_seconds
