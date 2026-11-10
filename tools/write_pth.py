"""Put every app and package src directory on the virtual environment's path (no root pyproject)."""

from __future__ import annotations

import site
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ["apps/api", "apps/worker", "packages/core", "packages/db", "packages/files", "packages/parsers", "packages/obs"]
target = Path(site.getsitepackages()[0]) / "supplementpacket_src.pth"
target.write_text("".join(f"{ROOT / d / 'src'}\n" for d in DIRS) + f"{ROOT}\n")
print(f"wrote {target}")
