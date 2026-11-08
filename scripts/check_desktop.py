"""Smoke-test the frozen backend and its parent-pipe shutdown contract."""
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STARTUP_TIMEOUT_SECONDS = 120
SHUTDOWN_TIMEOUT_SECONDS = 60


def main():
    executable = ROOT / "dist/ask-danta-backend" / ("ask-danta-backend.exe" if os.name == "nt" else "ask-danta-backend")
    with tempfile.TemporaryDirectory(prefix="ask-danta-test-") as directory:
        child = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            token = secrets.token_hex(32)
            child.stdin.write(json.dumps({"token": token, "data": directory}) + "\n")
            child.stdin.flush()
            lines = queue.Queue()
            threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True).start()
            port = json.loads(lines.get(timeout=STARTUP_TIMEOUT_SECONDS))["port"]
            origin = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
            while True:
                try:
                    with urlopen(Request(origin + "/api/health", headers={"x-desktop-token": token}), timeout=1) as response:
                        assert response.status == 200
                        assert json.load(response)["skills"] == ["ask-danta-research"]
                    break
                except URLError:
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            for route in ("/", "/api/settings", "/api/sessions", "/danta-logo.webp"):
                with urlopen(Request(origin + route, headers={"x-desktop-token": token}), timeout=5) as response:
                    assert response.status == 200, route
            try:
                urlopen(origin + "/api/settings", timeout=5)
                raise AssertionError("Unauthenticated access allowed")
            except HTTPError as error:
                assert error.code == 403
            child.stdin.close()
            assert child.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS) == 0
            print("Frozen backend smoke passed (assets, API, authorization, shutdown)")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
