"""One linear migration history (T-2.1.3, R-10, IT-07). Exits non-zero with more than one head."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

DEFAULT_INI = Path(__file__).resolve().parents[1] / "packages" / "db" / "alembic.ini"


def heads(script_location: str | None = None) -> list[str]:
    config = Config(str(DEFAULT_INI))
    if script_location:
        config.set_main_option("script_location", script_location)
    return list(ScriptDirectory.from_config(config).get_heads())


def main(argv: list[str]) -> int:
    found = heads(argv[1] if len(argv) > 1 else None)
    print(f"migration heads: {len(found)} ({', '.join(sorted(found))})")
    return 0 if len(found) == 1 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
