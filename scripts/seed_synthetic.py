"""Seed two synthetic tenants for local development (proposed command, now implemented).

Runs as the owner role because it stands in for vendor provisioning (tenant, location,
Owner and pilot are created only by provisioning, MH-10). Idempotent: fixed UUIDs,
upserts. B2: no session is created here any more; each run sets a fresh random password
and authenticator secret for every synthetic user and writes them to
.run/dev-credentials.json (untracked, mode 600), so a developer signs in through the real
password and TOTP path. Synthetic data only: no real names, VINs, claim numbers or estimates.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from sp_core.auth import derive_key, encrypt_secret, hash_password, new_totp_secret, totp_uri

NS = uuid.UUID("6d1f3c2e-9a51-4b8e-8f00-5e0c1a2b3c4d")
ROOT = Path(__file__).resolve().parents[1]


def _id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NS, "/".join(parts))


def _session_key() -> str:
    key = os.environ.get("SESSION_KEY")
    if not key:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("SESSION_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("SESSION_KEY is required (run `make env`)")
    return key


def seed(url: str) -> dict[str, dict[str, Any]]:
    engine = create_engine(url)
    totp_key = derive_key(_session_key(), "totp-secret")
    tokens: dict[str, dict[str, Any]] = {}
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
                email = f"{role}.{label.lower()}@example.test"
                password = secrets.token_urlsafe(18)
                secret = new_totp_secret()
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, totp_secret_enc, totp_enabled_at, password_changed_at) "
                        "VALUES (:id, :e, :n, :p, :s, now(), now()) ON CONFLICT (id) DO UPDATE SET password_hash = :p, "
                        "totp_secret_enc = :s, totp_enabled_at = now(), totp_last_step = NULL, password_changed_at = now()"
                    ),
                    {
                        "id": user,
                        "e": email,
                        "n": f"Synthetic {role.title()} {label}",
                        "p": hash_password(password),
                        "s": encrypt_secret(totp_key, secret),
                    },
                )
                conn.execute(
                    text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, :r) ON CONFLICT DO NOTHING"),
                    {"t": tenant, "u": user, "r": role},
                )
                conn.execute(text("UPDATE sessions SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"), {"u": user})
                tokens[label][role] = {"email": email, "password": password, "totp_secret": secret, "otpauth_uri": totp_uri(secret, email)}
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
    seeded = seed(url)
    out = ROOT / ".run" / "dev-credentials.json"
    out.parent.mkdir(exist_ok=True)
    out.touch(mode=0o600)
    out.write_text(json.dumps(seeded, indent=2))
    out.chmod(0o600)
    stale = ROOT / ".run" / "dev-tokens.json"
    stale.unlink(missing_ok=True)
    print(f"seeded 2 synthetic tenants; sign-in credentials in {out.relative_to(ROOT)} (untracked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
