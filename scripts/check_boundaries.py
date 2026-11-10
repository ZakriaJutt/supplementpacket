"""Import-boundary and single-home helper check (T-2.1.1, R-03, R-04, R-07).

Rules (TRD section 5): apps import only packages; apps never import each other;
packages never import apps; packages/obs and apps/worker import no web framework.
Money, date, key-building, settings and state-transition helpers are defined once.
Exits non-zero listing every violation.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = {"fastapi", "starlette", "uvicorn"}
APPS = {"sp_api": "apps/api", "sp_worker": "apps/worker"}
SINGLE_HOME = {
    "parse_cents": "packages/core/src/sp_core/money.py",
    "format_cents": "packages/core/src/sp_core/money.py",
    "round_half_up": "packages/core/src/sp_core/money.py",
    "hours_times_rate_cents": "packages/core/src/sp_core/money.py",
    "business_days_between": "packages/core/src/sp_core/dates.py",
    "pilot_day_end": "packages/core/src/sp_core/dates.py",
    "build_object_key": "packages/files/src/sp_files/__init__.py",
    "decide_transition": "packages/core/src/sp_core/jobs.py",
    "get_settings": "packages/core/src/sp_core/settings.py",
    "compute_ro_ledger": "packages/core/src/sp_core/ledger.py",
    "line_fingerprint": "packages/core/src/sp_core/approval.py",
}


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def check(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    defined: dict[str, list[str]] = {}
    for path in sorted(root.glob("apps/*/src/**/*.py")) + sorted(root.glob("packages/*/src/**/*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(), filename=rel)
        imported = _imports(tree)
        in_app = next((name for name, prefix in APPS.items() if rel.startswith(prefix + "/")), None)
        for app_pkg in APPS:
            if app_pkg in imported and app_pkg != in_app:
                problems.append(f"{rel}: imports {app_pkg} ({'app imports another app' if in_app else 'package imports an app'})")
        if (rel.startswith("packages/obs/") or rel.startswith("apps/worker/") or rel.startswith("packages/core/")) and imported & WEB:
            problems.append(f"{rel}: imports a web framework ({', '.join(sorted(imported & WEB))})")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in SINGLE_HOME and node.col_offset == 0:
                defined.setdefault(node.name, []).append(rel)
    for name, home in SINGLE_HOME.items():
        places = defined.get(name, [])
        if places != [home]:
            problems.append(f"helper {name} must be defined once in {home}; found in {places or 'nowhere'}")
    return problems


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    problems = check(root)
    for problem in problems:
        print(problem)
    print(f"boundary check: {len(problems)} violation(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
