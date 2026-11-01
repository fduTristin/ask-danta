from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8-sig", extra="ignore",
        hide_input_in_errors=True,
    )

    model_base_url: HttpUrl = "https://api.deepseek.com"
    model_name: str = Field(default="deepseek-flash", min_length=1, max_length=200)
    model_api_key: SecretStr = SecretStr("")
    model_thinking: Literal["enabled", "disabled"] = "disabled"
    model_reasoning_effort: Literal["low", "high", "max"] = "low"
    model_max_tokens: int = Field(default=4096, ge=256, le=32768)
    model_timeout_seconds: float = Field(default=45, gt=0, le=300)
    search_timeout_seconds: float | None = Field(default=None, gt=0, le=120)
    search_provider: Literal["mock", "tavily"] = "mock"
    search_api_key: SecretStr = SecretStr("")
    search_depth: Literal["basic", "advanced"] = "basic"
    search_max_results: int = Field(default=5, ge=1, le=10)
    search_max_snippet_chars: int = Field(default=2000, ge=100, le=10000)
    campus_auth_file: Path = Path(".private/campus-tokens.json")
    http_timeout_seconds: float = Field(default=15, gt=0, le=120)
    max_tool_calls: int = Field(default=6, ge=1, le=30)
    max_campus_pages: int = Field(default=3, ge=1, le=20)
    request_budget_seconds: float = Field(default=90, gt=0, le=600)
    backend_port: int = Field(default=8000, ge=1024, le=65535)
    frontend_port: int = Field(default=5173, ge=1024, le=65535)

    @field_validator("model_api_key", "search_api_key", mode="before")
    @classmethod
    def trim_key(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def different_ports(self):
        if self.backend_port == self.frontend_port:
            raise ValueError("BACKEND_PORT and FRONTEND_PORT must differ")
        return self

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
