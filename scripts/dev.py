"""Run and supervise both loopback-only development servers."""
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def stop(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def main() -> int:
    if not PYTHON.exists():
        print("Dependencies missing. Run: python scripts/setup.py", file=sys.stderr)
        return 1
    if Path(sys.executable).resolve() != PYTHON.resolve():
        # The supervisor must run inside the project's virtual environment.
        supervisor = subprocess.Popen([str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
        try:
            return supervisor.wait()
        except KeyboardInterrupt:
            # Both processes receive console Ctrl+C. Let the supervisor finish
            # stopping its children rather than killing it during cleanup.
            return supervisor.wait(timeout=15)

    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import Settings
    from pydantic import ValidationError

    try:
        settings = Settings()
    except ValidationError as exc:
        print("Invalid deployment environment variables:", file=sys.stderr)
        for error in exc.errors(include_input=False, include_context=False):
            print(f"  {'.'.join(map(str, error['loc'])) or 'ports'}: {error['type']}", file=sys.stderr)
        return 1
    node = shutil.which("node")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.exists():
        print("Frontend dependencies missing. Run: python scripts/setup.py", file=sys.stderr)
        return 1
    for port in (settings.backend_port, settings.frontend_port):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                print(f"Port {port} is already in use. Set BACKEND_PORT / FRONTEND_PORT or stop the existing service.", file=sys.stderr)
                return 1

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    if os.name == "nt":
        signal.signal(signal.SIGBREAK, interrupted)
    children = []
    env = os.environ.copy()
    env.update(BACKEND_PORT=str(settings.backend_port), FRONTEND_PORT=str(settings.frontend_port))
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        children.append(subprocess.Popen([
            str(PYTHON), "-m", "uvicorn", "app.main:create_app", "--factory",
            "--app-dir", str(ROOT / "backend"), "--host", "127.0.0.1",
            "--port", str(settings.backend_port), "--no-access-log",
        ], cwd=ROOT, env=env, creationflags=flags))
        children.append(subprocess.Popen([node, str(vite)], cwd=ROOT / "frontend", env=env, creationflags=flags))
        addresses = [f"http://127.0.0.1:{settings.backend_port}/api/health", f"http://127.0.0.1:{settings.frontend_port}/"]
        pending = set(addresses)
        deadline = time.monotonic() + 30
        while pending:
            if any(child.poll() is not None for child in children):
                print("A development server exited during startup.", file=sys.stderr)
                return 1
            for address in list(pending):
                try:
                    with urlopen(address, timeout=.5) as response:
                        if response.status == 200:
                            pending.remove(address)
                except (URLError, OSError):
                    pass
            if time.monotonic() > deadline:
                print("Startup timed out; inspect the server output above.", file=sys.stderr)
                return 1
            time.sleep(.2)
        print(f"\nReady: {addresses[1]}\nAPI docs: http://127.0.0.1:{settings.backend_port}/docs\nPress Ctrl+C to stop both servers.\n", flush=True)
        if "--smoke" in sys.argv:
            # No external search calls or credentials needed for startup verification.
            with urlopen(f"{addresses[1]}api/health", timeout=5) as response:
                assert response.status == 200
            print("Smoke check passed: frontend, backend and API proxy.", flush=True)
            return 0
        while all(child.poll() is None for child in children):
            time.sleep(.3)
        print("A development server stopped; stopping its sibling.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopping development servers.", flush=True)
        return 0
    finally:
        stop(children)


if __name__ == "__main__":
    sys.exit(main())
