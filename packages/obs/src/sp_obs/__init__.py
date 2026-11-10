"""Structured JSON logging with correlation IDs and redaction (TRD 8.8, R-07, R-12).

No web-framework import here: the worker uses this package too (IT-13).
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

__all__ = [
    "JsonFormatter",
    "configure_logging",
    "correlation_id",
    "correlation_scope",
    "get_logger",
    "new_correlation_id",
    "redact",
    "set_correlation_id",
]

_correlation: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

# Field names whose values never reach a log line.
_DENY_KEYS = frozenset(
    {
        "claim_number",
        "vin",
        "name",
        "owner_name",
        "adjuster_name",
        "adjuster_email",
        "email",
        "address",
        "phone",
        "policy_number",
        "description",
        "explanation",
        "note",
        "text",
        "file_name",
        "filename",
        "email_draft",
        "password",
        "token",
        "session",
        "amount",
        "amount_cents",
        "requested_cents",
        "approved_cents",
        "collected_cents",
        "line_total_cents",
        "body",
    }
)
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_MONEY_RE = re.compile(r"(?:USD|US\$|\$)\s?-?\d[\d,]*(?:\.\d{1,2})?", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CLAIM_RE = re.compile(r"\bclaim\s*(?:no\.?|number|#)?\s*[:#]?\s*[A-Z0-9-]{4,}\b", re.IGNORECASE)
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def correlation_id() -> str | None:
    return _correlation.get()


def set_correlation_id(value: str | None) -> contextvars.Token[str | None]:
    return _correlation.set(value)


@contextmanager
def correlation_scope(value: str | None) -> Iterator[str]:
    cid = value or new_correlation_id()
    token = _correlation.set(cid)
    try:
        yield cid
    finally:
        _correlation.reset(token)


def _scrub_text(text: str) -> str:
    text = _VIN_RE.sub("[redacted-vin]", text)
    text = _MONEY_RE.sub("[redacted-amount]", text)
    text = _EMAIL_RE.sub("[redacted-email]", text)
    return _CLAIM_RE.sub("[redacted-claim]", text)


def redact(value: Any, key: str | None = None) -> Any:
    """Drop denied keys and scrub VIN, amount, email and claim-number patterns."""
    if key is not None and key.lower() in _DENY_KEYS:
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _scrub_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": _scrub_text(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", None) or _correlation.get(),
        }
        for attr, val in record.__dict__.items():
            if attr not in _STANDARD_ATTRS and attr != "correlation_id" and not attr.startswith("_"):
                payload[attr] = redact(val, attr)
        if record.exc_info and record.exc_info[0] is not None:
            payload["error_type"] = record.exc_info[0].__name__  # no message: it may hold document text
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: str = "INFO", stream: Any = None) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_sp_handler", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._sp_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
