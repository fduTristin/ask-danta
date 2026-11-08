"""Convert the existing logo to desktop formats without changing its artwork.

Run: uv run --with pillow==12.2.0 python scripts/build_icons.py
Generated assets are committed; normal application builds do not need Pillow.
"""
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
destination = ROOT / "desktop/icons"
destination.mkdir(parents=True, exist_ok=True)
with Image.open(ROOT / "frontend/public/danta-logo.webp") as source:
    icon = ImageOps.pad(source.convert("RGBA"), (1024, 1024), method=Image.Resampling.LANCZOS)
    icon.save(destination / "icon.icns")
    icon.resize((512, 512), Image.Resampling.LANCZOS).save(destination / "icon.png")
    icon.save(destination / "icon.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
print(f"Desktop icons generated in {destination}")
