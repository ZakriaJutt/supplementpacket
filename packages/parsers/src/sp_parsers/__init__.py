"""Estimate parser interface (TRD 4, AD-04).

B1 ships the interface and a registry only. The CCC ONE layout parser (T-3.1.3) needs
the hand-transcribed fixture set from T-1.1.2, which waits on gate G1; until then an
upload with no registered parser fails cleanly and the Estimator uses manual entry
(MH-02 fallback). Tests register a fake parser.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

__all__ = ["EstimateParser", "ParsedEstimate", "ParsedLine", "ParserError", "clear_registry", "get_parser", "register"]


@dataclass(frozen=True)
class ParsedLine:
    line_no: int
    operation: str
    description: str
    line_total_cents: int
    page: int | None = None
    section: str | None = None
    part_number: str | None = None
    part_type: str | None = None
    part_price_cents: int | None = None
    labor_hours: Decimal | None = None
    labor_type: str | None = None
    labor_rate_cents: int | None = None


@dataclass(frozen=True)
class ParsedEstimate:
    parser_name: str
    parser_version: str
    lines: tuple[ParsedLine, ...]
    printed_total_cents: int | None
    page_count: int | None = None


class ParserError(Exception):
    """The document cannot be read by this parser; the job fails and manual entry is offered."""


class EstimateParser(Protocol):
    name: str
    version: str

    def parse(self, data: bytes) -> ParsedEstimate: ...


_REGISTRY: dict[str, Callable[[], EstimateParser]] = {}


def register(source_system: str, factory: Callable[[], EstimateParser]) -> None:
    _REGISTRY[source_system] = factory


def get_parser(source_system: str) -> EstimateParser | None:
    factory = _REGISTRY.get(source_system)
    return factory() if factory else None


def clear_registry() -> None:
    _REGISTRY.clear()
