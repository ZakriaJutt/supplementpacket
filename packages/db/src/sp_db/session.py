"""Engine and tenant-scoped transactions (TRD 8.3, AGENTS 5).

Every transaction that touches tenant data starts with SET LOCAL of the tenant, the
acting user, the actor role and the correlation ID. The tenant always comes from the
session or the job row, never from request input.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["get_engine", "global_transaction", "session_factory", "set_context", "tenant_transaction"]


@lru_cache(maxsize=4)
def get_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)


@lru_cache(maxsize=4)
def session_factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)


def set_context(
    db: Session,
    *,
    tenant_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    actor_role: str | None,
    correlation_id: str | None,
) -> None:
    db.execute(
        text(
            "SELECT set_config('app.tenant_id', :t, true), set_config('app.user_id', :u, true), "
            "set_config('app.actor_role', :r, true), set_config('app.correlation_id', :c, true)"
        ),
        {
            "t": str(tenant_id) if tenant_id else "",
            "u": str(user_id) if user_id else "",
            "r": actor_role or "",
            "c": correlation_id or "",
        },
    )


@contextmanager
def tenant_transaction(
    url: str,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    actor_role: str | None,
    correlation_id: str | None,
) -> Iterator[Session]:
    """One business operation, one transaction, one tenant. Commits on success."""
    factory = session_factory(url)
    with factory() as db, db.begin():
        set_context(db, tenant_id=tenant_id, user_id=user_id, actor_role=actor_role, correlation_id=correlation_id)
        yield db


@contextmanager
def global_transaction(url: str) -> Iterator[Session]:
    """A transaction with no tenant set: tenant tables return zero rows here."""
    factory = session_factory(url)
    with factory() as db, db.begin():
        yield db
