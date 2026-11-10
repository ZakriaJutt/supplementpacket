"""Shared service helpers: lookups that 404 under row-level security, serialisation."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from sp_api.context import Problem
from sp_db.models import Base

__all__ = ["check_version", "get_or_404", "lock_or_404", "parse_uuid", "to_dict"]

M = TypeVar("M", bound=Base)


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise Problem(404, "Not found") from exc


def get_or_404(db: Session, model: type[M], ident: uuid.UUID) -> M:
    obj = db.get(model, ident)
    if obj is None:
        raise Problem(404, "Not found")
    return obj


def lock_or_404(db: Session, model: type[M], ident: uuid.UUID) -> M:
    obj = db.execute(select(model).where(model.id == ident).with_for_update()).scalar_one_or_none()  # type: ignore[attr-defined]
    if obj is None:
        raise Problem(404, "Not found")
    return obj


def check_version(obj: Any, if_match: int | None) -> None:
    if if_match is None:
        raise Problem(428, "If-Match required", "send the row_version you edited")
    if obj.row_version != if_match:
        raise Problem(409, "Conflict", "this record changed since you loaded it", current_row_version=obj.row_version)


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes | memoryview):
        return bytes(value).hex()
    return value


def to_dict(obj: Base, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    return {c.key: _plain(getattr(obj, c.key)) for c in mapper.column_attrs if c.key not in exclude}
