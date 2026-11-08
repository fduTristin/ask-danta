"""Validated, owner-only runtime configuration; secrets are write-only over HTTP."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile

from pydantic import ConfigDict, ValidationError, create_model

from .campus_auth import restrict_file
from .config import Settings
from .sessions import private_directory

FIELDS = (
    "model_base_url", "model_name", "model_api_key", "model_thinking", "model_reasoning_effort",
    "model_max_tokens", "model_timeout_seconds", "answer_review_enabled", "search_provider",
    "search_api_key", "search_depth", "search_max_results", "search_max_snippet_chars",
    "search_timeout_seconds", "http_timeout_seconds", "campus_max_content_chars",
    "max_tool_calls", "max_campus_pages", "request_budget_seconds",
)
SECRETS = {"model_api_key", "search_api_key"}
SettingsPatch = create_model("SettingsPatch", __config__=ConfigDict(extra="forbid", hide_input_in_errors=True),
    **{name: (Settings.model_fields[name].annotation, deepcopy(Settings.model_fields[name])) for name in FIELDS})


class SettingsStorageError(Exception):
    pass


def public_settings(settings: Settings) -> dict:
    result = settings.model_dump(mode="json", include=set(FIELDS) - SECRETS)
    for name in SECRETS:
        result[name + "_configured"] = bool(getattr(settings, name).get_secret_value())
    return result


class RuntimeSettingsStore:
    def __init__(self, base: Settings, path: Path):
        self.base, self.path = base, path
        self.overrides: dict = {}

    def merge(self, changes: dict) -> Settings:
        return Settings(_env_file=None, **{**self.base.model_dump(), **self.overrides, **changes})

    def load(self) -> Settings:
        try:
            if self.path.is_symlink():
                raise ValueError("Invalid settings file")
            if not self.path.exists():
                return self.base
            if self.path.stat().st_size > 100_000:
                raise ValueError("Invalid settings size")
            patch = SettingsPatch.model_validate_json(self.path.read_text(encoding="utf-8"))
            self.overrides = patch.model_dump(exclude_unset=True)
            return self.merge({})
        except (OSError, ValueError, ValidationError):
            raise SettingsStorageError("无法读取本机设置，请检查 .private/settings.json 的格式与权限。") from None

    def save(self, changes: dict) -> Settings:
        settings = self.merge(changes)
        overrides = {**self.overrides, **changes}
        payload = settings.model_dump(mode="json", include=set(overrides))
        for name in SECRETS & overrides.keys():
            payload[name] = getattr(settings, name).get_secret_value()
        temporary = None
        try:
            private_directory(self.path.parent)
            if self.path.is_symlink():
                raise OSError("Invalid settings path")
            fd, name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=self.path.parent)
            temporary = Path(name)
            os.close(fd)
            restrict_file(temporary)
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, subprocess.SubprocessError):
            raise SettingsStorageError("无法安全保存设置，请检查本机文件权限后重试。") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        self.overrides = overrides
        return settings
