"""Shared fixtures. Synthetic data only: no real names, VINs, claim numbers or estimates.

The application and every isolation test connect as ``supplementpacket_app`` (no
superuser, no BYPASSRLS). The owner connection is used only to seed fixtures that the
product creates through vendor provisioning (tenants, users, sessions, grants, pilots).
"""

from __future__ import annotations

import getpass
import os
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from sp_api.context import hash_token
from sp_api.main import create_app
from sp_core.settings import Settings
from sp_files import MemoryObjectStore

DB = os.environ.get("SP_TEST_DB", "supplementpacket_test")
APP_URL = f"postgresql+psycopg://supplementpacket_app@localhost:5432/{DB}"
OWNER_URL = f"postgresql+psycopg://{getpass.getuser()}@localhost:5432/{DB}"
SYNTHETIC_PDF = b"%PDF-1.4\n% synthetic estimate for tests\n"
JPEG = b"\xff\xd8\xff\xe0synthetic-jpeg-"


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    root = tmp_path_factory.mktemp("storage")
    return Settings(
        PUBLIC_BASE_URL="https://app.example.test",
        DATABASE_URL=APP_URL,
        MIGRATION_DATABASE_URL=OWNER_URL,
        STORAGE_BUCKET=str(root),
        SESSION_KEY="test-session-key-not-secret",
        WORKER_HEARTBEAT_PATH=str(root / "hb"),
        LOG_LEVEL="INFO",
    )  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def owner_engine() -> Iterator[Engine]:
    engine = create_engine(OWNER_URL)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert head, "run `make test` (it resets and migrates the test database)"
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine() -> Iterator[Engine]:
    engine = create_engine(APP_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def store() -> MemoryObjectStore:
    return MemoryObjectStore()


@pytest.fixture()
def client(settings: Settings, store: MemoryObjectStore) -> TestClient:
    return TestClient(create_app(settings, store), raise_server_exceptions=True)


@dataclass
class Shop:
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    insurer_id: uuid.UUID
    users: dict[str, uuid.UUID] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    pilot_id: uuid.UUID | None = None


def _seed_shop(engine: Engine, label: str) -> Shop:
    tenant_id, location_id, insurer_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    shop = Shop(tenant_id, location_id, insurer_id)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO tenants (id, name) VALUES (:id, :n)"), {"id": tenant_id, "n": f"Synthetic Shop {label}"})
        conn.execute(text("INSERT INTO locations (id, tenant_id, name) VALUES (:id, :t, 'Main')"), {"id": location_id, "t": tenant_id})
        conn.execute(
            text("INSERT INTO insurers (id, tenant_id, name) VALUES (:id, :t, 'Synthetic Mutual')"), {"id": insurer_id, "t": tenant_id}
        )
        for role in ("owner", "estimator", "office", "operator", "operator_nogrant"):
            uid = uuid.uuid4()
            conn.execute(
                text("INSERT INTO users (id, email, password_hash, is_operator) VALUES (:id, :e, 'not-a-real-hash', :op)"),
                {"id": uid, "e": f"{role}.{uid.hex[:8]}@example.test", "op": role.startswith("operator")},
            )
            if role in ("owner", "estimator", "office"):
                conn.execute(
                    text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, :r)"), {"t": tenant_id, "u": uid, "r": role}
                )
            token = secrets.token_urlsafe(24)
            conn.execute(
                text("INSERT INTO sessions (id, user_id, tenant_id, expires_at) VALUES (:id, :u, :t, :x)"),
                {"id": hash_token(token), "u": uid, "t": tenant_id, "x": datetime.now(UTC) + timedelta(hours=12)},
            )
            shop.users[role] = uid
            shop.tokens[role] = token
        conn.execute(
            text(
                "INSERT INTO operator_grants (tenant_id, operator_user_id, granted_by, expires_at) "
                "VALUES (:t, :op, :owner, now() + interval '7 days')"
            ),
            {"t": tenant_id, "op": shop.users["operator"], "owner": shop.users["owner"]},
        )
        pilot_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO pilots (id, tenant_id, location_id, start_date, terms_version, created_by) "
                "VALUES (:id, :t, :l, :d, 'pilot-terms-v1', :op)"
            ),
            {"id": pilot_id, "t": tenant_id, "l": location_id, "d": date(2026, 9, 1), "op": shop.users["operator"]},
        )
        shop.pilot_id = pilot_id
    return shop


@pytest.fixture()
def shop(owner_engine: Engine) -> Shop:
    return _seed_shop(owner_engine, "A")


@pytest.fixture()
def other_shop(owner_engine: Engine) -> Shop:
    return _seed_shop(owner_engine, "B")


class Api:
    """Test client bound to one user; adds an Idempotency-Key to every mutation."""

    def __init__(self, client: TestClient, token: str) -> None:
        self.client = client
        self.token = token

    def _headers(self, extra: dict[str, str] | None, method: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if method != "GET":
            headers["Idempotency-Key"] = secrets.token_hex(12)
        headers.update(extra or {})
        return headers

    def get(self, path: str, **kw: Any) -> Any:
        return self.client.get(f"/api/v1{path}", headers=self._headers(kw.pop("headers", None), "GET"), **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.client.post(f"/api/v1{path}", headers=self._headers(kw.pop("headers", None), "POST"), **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.client.patch(f"/api/v1{path}", headers=self._headers(kw.pop("headers", None), "PATCH"), **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.client.put(f"/api/v1{path}", headers=self._headers(kw.pop("headers", None), "PUT"), **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.client.delete(f"/api/v1{path}", headers=self._headers(kw.pop("headers", None), "DELETE"), **kw)


@pytest.fixture()
def api(client: TestClient, shop: Shop) -> dict[str, Api]:
    return {role: Api(client, token) for role, token in shop.tokens.items()}


# Core-path builders --------------------------------------------------------------------------

SHOP_LINES = [
    {"operation": "blend", "description": "Blend fender", "labor_hours": "1.2", "labor_rate_cents": 5400, "line_total_cents": 6480},
    {
        "operation": "repair",
        "description": "Repair front bumper",
        "labor_hours": "2.5",
        "labor_rate_cents": 6000,
        "line_total_cents": 15000,
    },
    {
        "operation": "replace",
        "description": "Headlamp assembly",
        "part_number": "HL-100",
        "part_type": "oem",
        "part_price_cents": 42000,
        "line_total_cents": 42000,
    },
]
INSURER_LINES = [
    {
        "operation": "repair",
        "description": "Repair front bumper",
        "labor_hours": "2.0",
        "labor_rate_cents": 6000,
        "line_total_cents": 12000,
    },
    {
        "operation": "replace",
        "description": "Headlamp assembly",
        "part_number": "HL-100",
        "part_type": "aftermarket",
        "part_price_cents": 30000,
        "line_total_cents": 30000,
    },
]


def upload_estimate(user: Api, ro_id: str, purpose: str, marker: str = "") -> dict[str, Any]:
    pdf = SYNTHETIC_PDF + f"{purpose}{marker}{uuid.uuid4()}".encode()
    r = user.post(f"/ros/{ro_id}/documents", data={"purpose": purpose}, files={"file": ("x.pdf", pdf, "application/pdf")})
    assert r.status_code == 202, r.text
    return r.json()["document"]


def enter_lines(user: Api, document_id: str, lines: list[dict[str, Any]], printed: int | None = None) -> dict[str, Any]:
    total = sum(int(x["line_total_cents"]) for x in lines) if printed is None else printed
    r = user.post(f"/documents/{document_id}/manual-lines", json={"printed_total_cents": total, "lines": lines})
    assert r.status_code == 201, r.text
    return r.json()


def create_ro(user: Api, shop: Shop, number: str | None = None) -> dict[str, Any]:
    r = user.post(
        "/ros",
        json={
            "location_id": str(shop.location_id),
            "ro_number": number or f"RO-{uuid.uuid4().hex[:6]}",
            "insurer_id": str(shop.insurer_id),
            "claim_number": "SYN-CLAIM-0001",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def ro_with_diff(user: Api, shop: Shop) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ro = create_ro(user, shop)
    ins = upload_estimate(user, ro["id"], "insurer_estimate")
    sh = upload_estimate(user, ro["id"], "shop_estimate")
    enter_lines(user, ins["id"], INSURER_LINES)
    enter_lines(user, sh["id"], SHOP_LINES)
    r = user.post(f"/ros/{ro['id']}/diff")
    assert r.status_code == 200, r.text
    lines = user.get(f"/ros/{ro['id']}/lines").json()
    return ro, lines


def explain(user: Api, line: dict[str, Any]) -> dict[str, Any]:
    r = user.patch(
        f"/lines/{line['id']}",
        json={"explanation": "Shop photos show the operation is required for this repair."},
        headers={"If-Match": str(line["row_version"])},
    )
    assert r.status_code == 200, r.text
    return r.json()


def approve(user: Api, line: dict[str, Any]) -> Any:
    return user.post(f"/lines/{line['id']}/approve", headers={"If-Match": str(line["row_version"])})


def approve_all(user: Api, ro_id: str) -> None:
    for line in user.get(f"/ros/{ro_id}/lines").json():
        if line["match_state"] == "needs_review":
            continue
        if not line["explanation"]:
            line = explain(user, line)
        r = approve(user, line)
        assert r.status_code == 200, r.text


def freeze(user: Api, ro_id: str) -> Any:
    review = user.get(f"/ros/{ro_id}/packet-review").json()
    return user.post(
        f"/ros/{ro_id}/packets",
        json={"review_fingerprint": review["review_fingerprint"], "review_components": review["review_components"]},
    )
