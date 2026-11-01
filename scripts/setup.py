"""Install locked dependencies without requiring shell activation."""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    uv = shutil.which("uv")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not uv or not npm:
        print("Install uv and Node.js (22.12+ recommended), then retry.", file=sys.stderr)
        return 1
    subprocess.run([uv, "sync", "--frozen"], cwd=ROOT, check=True)
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend", check=True)
    target = ROOT / ".env"
    if not target.exists():
        # Exclusive creation protects an existing file from concurrent setup.
        try:
            with target.open("x", encoding="utf-8") as output:
                output.write((ROOT / ".env.example").read_text(encoding="utf-8"))
        except FileExistsError:
            pass
    print("Ready. Edit .env as needed, then run: python scripts/dev.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
