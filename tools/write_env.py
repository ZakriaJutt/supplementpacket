"""Create the untracked .env from config/dev.env.example with a fresh SESSION_KEY and the local owner role."""

from __future__ import annotations

import getpass
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lines = []
for line in (ROOT / "config" / "dev.env.example").read_text().splitlines():
    if line.startswith("SESSION_KEY="):
        line = f"SESSION_KEY={secrets.token_hex(32)}"
    lines.append(line.replace("OWNER_ROLE@", f"{getpass.getuser()}@"))
target = ROOT / ".env"
target.write_text("\n".join(lines) + "\n")
target.chmod(0o600)
print("wrote .env")
