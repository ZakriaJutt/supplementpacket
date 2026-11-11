"""Request input checks: typed, bounded, 422 on anything else (B1-009, B1-011; ASVS 2.2.1).

Money is integer cents only (a JSON integer or a string of digits); a JSON float, a bool
or a decimal string is refused, never truncated. Free text has a length cap, and every
response that carries free text the Estimator typed also carries the notice not to
paste procedure or estimating-guide text.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sp_api.context import Problem
from sp_core.evidence import FREE_TEXT_NOTICE
from sp_core.money import MoneyFormatError, cents_from_input

__all__ = [
    "FREE_TEXT_NOTICE",
    "LIMITS",
    "a_date",
    "a_uuid",
    "an_int",
    "cents",
    "hours",
    "req",
    "text_field",
    "with_notice",
]

LIMITS = {
    "description": 300,
    "explanation": 2000,
    "email_free_paragraph": 1000,
    "note": 300,
    "attestation_note": 300,
    "reason": 500,
    "denial_reason": 500,
    "override_reason": 500,
    "over_approved_reason": 500,
    "source_note": 300,
    "title": 300,
    "publisher": 200,
    "identifier": 100,
    "reference": 100,
    "ro_number": 50,
    "claim_number": 50,
    "adjuster_name": 120,
    "adjuster_email": 254,
    "vehicle_desc": 200,
    "counts_source_note": 300,
    "ro_label": 50,
    "insurer_name": 120,
    "part_number": 60,
    "labor_type": 40,
    "section": 60,
    "correction_note": 500,
}


def req(body: dict[str, Any], key: str) -> Any:
    if key not in body or body[key] is None or body[key] == "":
        raise Problem(422, "Missing field", f"{key} is required", field=key)
    return body[key]


def text_field(body: dict[str, Any], key: str, *, required: bool = False, limit: int | None = None) -> str | None:
    value = req(body, key) if required else body.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise Problem(422, "Invalid field", f"{key} must be text", field=key)
    cap = limit or LIMITS.get(key, 1000)
    if len(value) > cap:
        raise Problem(422, "Text too long", f"{key} is limited to {cap} characters. {FREE_TEXT_NOTICE}", field=key)
    return value


def cents(body: dict[str, Any], key: str, *, required: bool = True, allow_negative: bool = False) -> int | None:
    if not required and body.get(key) is None:
        return None
    value = req(body, key)
    try:
        return cents_from_input(value, field=key, allow_negative=allow_negative)
    except MoneyFormatError as exc:
        raise Problem(422, "Invalid amount", str(exc), field=key) from exc


def hours(body: dict[str, Any], key: str) -> Decimal | None:
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool | float):
        raise Problem(422, "Invalid hours", f'{key} must be a decimal string such as "1.20"', field=key)
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise Problem(422, "Invalid hours", f"{key} must be a decimal number", field=key) from exc
    if not number.is_finite() or number.as_tuple().exponent < -2 or abs(number) >= 10000:  # type: ignore[operator]
        raise Problem(422, "Invalid hours", f"{key} must be finite, with at most 2 decimals and below 10000", field=key)
    return number


def a_date(body: dict[str, Any], key: str, *, required: bool = True) -> date | None:
    value = body.get(key)
    if value in (None, ""):
        if required:
            raise Problem(422, "Missing field", f"{key} is required", field=key)
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise Problem(422, "Invalid date", f"{key} must be YYYY-MM-DD", field=key) from exc


def an_int(body: dict[str, Any], key: str, *, minimum: int = 0) -> int | None:
    value = body.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int | str) or (isinstance(value, str) and not value.strip().isdigit()):
        raise Problem(422, "Invalid number", f"{key} must be a whole number", field=key)
    number = int(value)
    if number < minimum:
        raise Problem(422, "Invalid number", f"{key} must be at least {minimum}", field=key)
    return number


def a_uuid(body: dict[str, Any], key: str, *, required: bool = True) -> uuid.UUID | None:
    value = body.get(key)
    if value in (None, ""):
        if required:
            raise Problem(422, "Missing field", f"{key} is required", field=key)
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise Problem(404, "Not found") from exc


def with_notice(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "free_text_notice": FREE_TEXT_NOTICE}
