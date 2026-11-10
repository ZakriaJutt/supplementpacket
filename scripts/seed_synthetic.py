"""Seed two synthetic tenants for local development (proposed command, now implemented).

Runs as the owner role because it stands in for vendor provisioning (tenant, location,
Owner and pilot are created only by provisioning, MH-10). Idempotent: fixed UUIDs,
upserts. Writes local session tokens to .run/dev-tokens.json (untracked). Synthetic
data only: no real names, VINs, claim numbers or estimates.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

NS = uuid.UUID("6d1f3c2e-9a51-4b8e-8f00-5e0c1a2b3c4d")
ROOT = Path(__file__).resolve().parents[1]


def _id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NS, "/".join(parts))


def seed(url: str) -> dict[str, dict[str, str]]:
    engine = create_engine(url)
    tokens: dict[str, dict[str, str]] = {}
    with engine.begin() as conn:
        cv = _id("checklist", "1")
        conn.execute(
            text("INSERT INTO checklist_versions (id, version, author) VALUES (:id, 1, 'synthetic-dev-seed') ON CONFLICT (id) DO NOTHING"),
            {"id": cv},
        )
        for op in ("Pre-repair scan", "Post-repair scan", "Corrosion protection"):
            conn.execute(
                text(
                    "INSERT INTO checklist_items (id, checklist_version_id, repair_type, operation_name, prompt) "
                    "VALUES (:id, :cv, 'front_collision', :op, :p) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": _id("item", op), "cv": cv, "op": op, "p": f"Was {op.lower()} performed and not on the insurer estimate?"},
            )
        for label in ("A", "B"):
            tenant = _id("tenant", label)
            location = _id("location", label)
            conn.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, :n) ON CONFLICT (id) DO NOTHING"),
                {"id": tenant, "n": f"Synthetic Collision {label}"},
            )
            conn.execute(
                text("INSERT INTO locations (id, tenant_id, name) VALUES (:id, :t, 'Main') ON CONFLICT (id) DO NOTHING"),
                {"id": location, "t": tenant},
            )
            conn.execute(
                text("INSERT INTO insurers (id, tenant_id, name) VALUES (:id, :t, 'Synthetic Mutual') ON CONFLICT (id) DO NOTHING"),
                {"id": _id("insurer", label), "t": tenant},
            )
            tokens[label] = {"tenant_id": str(tenant), "location_id": str(location)}
            for role in ("owner", "estimator", "office"):
                user = _id("user", label, role)
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'login-not-implemented-in-b1') "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": user, "e": f"{role}.{label.lower()}@example.test"},
                )
                conn.execute(
                    text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, :r) ON CONFLICT DO NOTHING"),
                    {"t": tenant, "u": user, "r": role},
                )
                token = secrets.token_urlsafe(24)
                conn.execute(
                    text("INSERT INTO sessions (id, user_id, tenant_id, expires_at) VALUES (:id, :u, :t, :x)"),
                    {"id": hashlib.sha256(token.encode()).digest(), "u": user, "t": tenant, "x": datetime.now(UTC) + timedelta(hours=12)},
                )
                tokens[label][role] = token
            conn.execute(
                text(
                    "INSERT INTO pilots (id, tenant_id, location_id, start_date, terms_version, created_by) "
                    "VALUES (:id, :t, :l, current_date, 'pilot-terms-v1', :u) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": _id("pilot", label), "t": tenant, "l": location, "u": _id("user", label, "owner")},
            )
            tokens[label]["pilot_id"] = str(_id("pilot", label))
    engine.dispose()
    return tokens


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        print("MIGRATION_DATABASE_URL is required", file=sys.stderr)
        return 2
    tokens = seed(url)
    out = ROOT / ".run" / "dev-tokens.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(tokens, indent=2))
    out.chmod(0o600)
    print(f"seeded 2 synthetic tenants; session tokens in {out.relative_to(ROOT)} (untracked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
