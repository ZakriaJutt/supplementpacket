"""Request context: authentication, tenant transaction, permission checks, idempotency.

TRD 8.1-8.3. Cross-tenant access returns 404 (RLS hides the row). A forbidden action on
a visible row returns 403 and writes an audit event (IT-02).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from sp_core.permissions import Action, Role, allowed
from sp_core.settings import Settings
from sp_db.session import global_transaction, tenant_transaction
from sp_files import ObjectStore

__all__ = [
    "SESSION_COOKIE",
    "AppState",
    "Ctx",
    "Problem",
    "authenticate",
    "hash_token",
]

SESSION_COOKIE = "sp_session"


class Problem(Exception):
    """An RFC 9457 problem document."""

    def __init__(self, status: int, title: str, detail: str | None = None, **extra: Any) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.extra = extra

    def body(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"type": "about:blank", "title": self.title, "status": self.status}
        if self.detail:
            doc["detail"] = self.detail
        doc.update(self.extra)
        return doc


class PermissionDenied(Problem):
    def __init__(self, action: Action, entity_type: str, entity_id: uuid.UUID) -> None:
        super().__init__(403, "Forbidden", f"your role cannot {action.value.replace('_', ' ')}")
        self.action = action
        self.entity_type = entity_type
        self.entity_id = entity_id


class StaleApprovals(Problem):
    """Approvals whose approver no longer holds the Owner or Estimator role (B1-006)."""

    def __init__(self, line_ids: list[uuid.UUID]) -> None:
        super().__init__(
            409,
            "Packet cannot be frozen",
            "an approver no longer holds the Owner or Estimator role; those lines returned to draft",
            problems=[{"item": f"line:{i}", "reason": "approver no longer permitted"} for i in line_ids],
            changed=[],
        )
        self.line_ids = line_ids


@dataclass
class AppState:
    settings: Settings
    store: ObjectStore


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


@dataclass
class Ctx:
    state: AppState
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    correlation_id: str
    _db: Session | None = field(default=None, repr=False)

    @property
    def db_url(self) -> str:
        return self.state.settings.database_url

    @contextmanager
    def tx(self) -> Iterator[Session]:
        with tenant_transaction(
            self.db_url,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            actor_role=self.role.value,
            correlation_id=self.correlation_id,
        ) as db:
            yield db

    def require(self, action: Action, entity_type: str, entity_id: uuid.UUID) -> None:
        if not allowed(self.role, action):
            raise PermissionDenied(action, entity_type, entity_id)

    def audit(
        self,
        db: Session,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        db.execute(
            text("SELECT sp_audit(:t, :a, :et, :eid, CAST(:b AS jsonb), CAST(:af AS jsonb))"),
            {
                "t": self.tenant_id,
                "a": action,
                "et": entity_type,
                "eid": entity_id,
                "b": json.dumps(before, default=str) if before is not None else None,
                "af": json.dumps(after, default=str) if after is not None else None,
            },
        )

    def record_denial(self, exc: PermissionDenied) -> None:
        """Written in its own transaction: the refused change itself rolled back."""
        with self.tx() as db:
            self.audit(db, "permission.denied", exc.entity_type, exc.entity_id, None, {"action": exc.action.value, "role": self.role.value})

    def reset_lines(self, line_ids: list[uuid.UUID], reason: str) -> None:
        """Committed in its own transaction: the refused freeze itself rolled back."""
        with self.tx() as db:
            for line_id in line_ids:
                db.execute(text("SELECT sp_reset_line(:i, :r)"), {"i": line_id, "r": reason})

    def idempotent(
        self,
        request_key: str | None,
        method: str,
        path: str,
        payload: Any,
        fn: Callable[[Session], tuple[int, dict[str, Any]]],
    ) -> tuple[int, dict[str, Any]]:
        """Run ``fn`` once per Idempotency-Key; a repeat returns the stored response."""
        if not request_key or len(request_key) > 200:
            raise Problem(428, "Idempotency-Key required", "every mutation carries an Idempotency-Key header")
        digest = hashlib.sha256(json.dumps([method, path, payload], sort_keys=True, default=str).encode()).digest()
        with self.tx() as db:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{self.tenant_id}:{request_key}"})
            row = db.execute(
                text("SELECT request_sha256, status_code, response FROM idempotency_records WHERE key = :k"),
                {"k": request_key},
            ).first()
            if row is not None:
                if bytes(row[0]) != digest:
                    raise Problem(422, "Idempotency-Key reused", "this key was used for a different request")
                return int(row[1]), dict(row[2])
            status, body = fn(db)
            db.execute(
                text(
                    "INSERT INTO idempotency_records (tenant_id, key, method, path, request_sha256, status_code, response) "
                    "VALUES (:t, :k, :m, :p, :h, :s, CAST(:r AS jsonb))"
                ),
                {
                    "t": self.tenant_id,
                    "k": request_key,
                    "m": method,
                    "p": path,
                    "h": digest,
                    "s": status,
                    "r": json.dumps(body, default=str),
                },
            )
            return status, body


def _token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


def authenticate(request: Request, state: AppState, correlation_id: str) -> Ctx:
    """Resolve the session to a user, a tenant and a role. No tenant role means 404 later."""
    token = _token_from(request)
    if not token:
        raise Problem(401, "Not signed in")
    now = datetime.now(UTC)
    with global_transaction(state.settings.database_url) as db:
        row = db.execute(
            text(
                "SELECT s.user_id, s.tenant_id, u.is_operator, u.status FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.id = :id AND s.revoked_at IS NULL AND s.expires_at > :now"
            ),
            {"id": hash_token(token), "now": now},
        ).first()
        if row is None:
            raise Problem(401, "Not signed in")
        db.execute(text("UPDATE sessions SET last_seen_at = :now WHERE id = :id"), {"id": hash_token(token), "now": now})
    user_id, tenant_id, is_operator, status = row
    if status != "active" or tenant_id is None:
        raise Problem(401, "Not signed in")
    with tenant_transaction(
        state.settings.database_url, tenant_id=tenant_id, user_id=user_id, actor_role=None, correlation_id=correlation_id
    ) as db:
        member = db.execute(text("SELECT role FROM memberships WHERE user_id = :u"), {"u": user_id}).scalar()
        role: Role | None = Role(member) if member else None
        if role is None and is_operator:
            grant = db.execute(
                text("SELECT 1 FROM operator_grants WHERE operator_user_id = :u AND revoked_at IS NULL AND expires_at > :now"),
                {"u": user_id, "now": now},
            ).first()
            role = Role.OPERATOR if grant else None
        tenant_ok = db.execute(text("SELECT status FROM tenants")).scalar()
    if role is None or tenant_ok is None:
        # No access to this tenant at all: indistinguishable from a missing resource.
        raise Problem(404, "Not found")
    return Ctx(state=state, user_id=user_id, tenant_id=tenant_id, role=role, correlation_id=correlation_id)
