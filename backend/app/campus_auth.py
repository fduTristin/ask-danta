"""Project-owned credentials. Never read CLI/browser configuration or store passwords."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator


class CampusError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class Tokens(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    access: SecretStr
    refresh: SecretStr

    @field_validator("access", "refresh")
    @classmethod
    def valid_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not token or len(token) > 8192 or any(ord(c) <= 32 or ord(c) > 126 for c in token):
            raise ValueError("Invalid token")
        return value


class CampusLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def trim_email(cls, value):
        return value.strip() if isinstance(value, str) else value


def restrict_file(path: Path) -> None:
    """Set owner-only access before writing secrets, including on Windows."""
    if os.name != "nt":
        path.chmod(0o600)
        return
    script = """
$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
$acl.AddAccessRule($rule)
[System.IO.File]::SetAccessControl($env:CAMPUS_CREDENTIAL_PATH, $acl)
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "CAMPUS_CREDENTIAL_PATH": str(path.resolve())},
        capture_output=True, check=True, timeout=15,
    )


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Tokens:
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 20000:
                raise ValueError("Invalid credential file")
            return Tokens.model_validate_json(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise CampusError("campus_login_required", "尚未登录树洞，请运行本项目的 campus_login.py。", 503) from None
        except (OSError, ValueError, ValidationError):
            raise CampusError("campus_credentials_invalid", "树洞凭据文件不可读或格式无效，请重新运行本项目登录脚本。", 503) from None

    def save(self, tokens: Tokens) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise OSError("Refuse credential symlink")
            fd, name = tempfile.mkstemp(prefix=".campus-", suffix=".tmp", dir=self.path.parent)
            temporary = Path(name)
            os.close(fd)
            restrict_file(temporary)
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump({"access": tokens.access.get_secret_value(), "refresh": tokens.refresh.get_secret_value()}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except (OSError, subprocess.SubprocessError):
            raise CampusError("campus_credentials_write_failed", "无法安全保存树洞凭据，请检查本地文件权限后重新登录。", 503) from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    # Never mask a sanitized failure with a path-bearing traceback.
                    pass
