"""Local single-process session persistence; no credentials or reasoning traces."""

from dataclasses import asdict
import json
import os
import re
from copy import deepcopy
from pathlib import Path
import sqlite3
import subprocess

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .agent import Session
from .campus_auth import restrict_file


class SessionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=80)
    source_preference: Literal["auto", "web", "all"] | None = None


class SessionStorageError(Exception):
    pass


def without_reasoning(value):
    if isinstance(value, dict):
        return {key: without_reasoning(item) for key, item in value.items() if key != "reasoning_content"}
    if isinstance(value, list):
        return [without_reasoning(item) for item in value]
    return value


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("History directory cannot be a symlink")
    if os.name != "nt":
        path.chmod(0o700)
        return
    script = """
$ErrorActionPreference = 'Stop'
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$acl.AddAccessRule($rule)
[System.IO.Directory]::SetAccessControl($env:CAMPUS_HISTORY_DIRECTORY, $acl)
"""
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env={**os.environ, "CAMPUS_HISTORY_DIRECTORY": str(path.resolve())},
                   capture_output=True, check=True, timeout=15)


class SessionStore:
    def __init__(self, path: Path):
        try:
            private_directory(path.parent)
            if path.is_symlink():
                raise OSError("History file cannot be a symlink")
            path.touch(exist_ok=True)
            restrict_file(path)
            self.db = sqlite3.connect(path, check_same_thread=False)
            self.db.execute("PRAGMA secure_delete=ON")
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            self.db.commit()
        except (OSError, sqlite3.Error, subprocess.SubprocessError):
            raise SessionStorageError("无法打开本机聊天记录，请检查历史存储目录与文件权限。") from None

    def load(self) -> dict[str, Session]:
        try:
            sessions = {}
            for sid, payload in self.db.execute("SELECT id, payload FROM sessions"):
                data = json.loads(payload)
                data["busy"] = False
                data["interrupted"] = bool(data.get("pending_question"))
                if data["interrupted"] and data.get("progress"):
                    data["progress"]["status"] = "interrupted"
                    for step in data["progress"]["steps"]:
                        if step["status"] == "running":
                            step["status"] = "interrupted"
                session = Session(**data)
                # Older releases missed lowercase citations when attaching sources.
                # Recover only existing, real evidence from this same conversation.
                for message in session.messages:
                    if message.get("role") != "assistant":
                        continue
                    missing = {sid.upper() for sid in re.findall(r"\[([wc][1-9][0-9]*)\]", message.get("content", ""))}
                    missing -= {source["id"] for source in message.get("sources", [])}
                    recovered = [deepcopy(source) for source in session.sources
                                 if source["id"] in missing and not source.get("is_mock")
                                 and not (message.get("source_mode") == "web" and source.get("source") == "campus")]
                    if recovered:
                        message.setdefault("sources", []).extend(recovered)
                sessions[sid] = session
            return sessions
        except (sqlite3.Error, ValueError, TypeError):
            raise SessionStorageError("聊天记录无法读取，请保留历史文件并检查存储状态。") from None

    def save(self, session: Session) -> None:
        try:
            payload = json.dumps(without_reasoning(asdict(session)), ensure_ascii=False)
            with self.db:
                self.db.execute("INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                                (session.id, payload))
        except (sqlite3.Error, OSError):
            raise SessionStorageError("聊天记录保存失败，请检查磁盘空间后重试。") from None

    def delete(self, sid: str) -> None:
        try:
            with self.db:
                self.db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        except sqlite3.Error:
            raise SessionStorageError("未能删除聊天记录，请稍后重试。") from None

    def close(self) -> None:
        self.db.close()
