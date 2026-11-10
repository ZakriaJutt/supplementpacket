"""Totals reconciliation for a parsed or manually entered estimate (MH-02, UT-02)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["TOLERANCE_CENTS", "Reconciliation", "parse_feeds_packet", "reconcile"]

TOLERANCE_CENTS = 1  # "a mismatch above USD 0.01 sets unreconciled"


@dataclass(frozen=True)
class Reconciliation:
    status: str  # "reconciled" | "unreconciled"
    parsed_total_cents: int
    printed_total_cents: int | None
    difference_cents: int | None


def reconcile(line_totals_cents: Iterable[int], printed_total_cents: int | None) -> Reconciliation:
    parsed = sum(line_totals_cents)
    if printed_total_cents is None:
        # No printed total to compare with: not reconciled until the Estimator confirms it.
        return Reconciliation("unreconciled", parsed, None, None)
    difference = printed_total_cents - parsed
    status = "reconciled" if abs(difference) <= TOLERANCE_CENTS else "unreconciled"
    return Reconciliation(status, parsed, printed_total_cents, difference)


def parse_feeds_packet(status: str, confirm_reason: str | None, confirmed_by: object | None) -> bool:
    """A parse may feed a packet when reconciled, manual, or unreconciled with a confirmed reason."""
    if status in ("reconciled", "manual"):
        return True
    if status == "unreconciled":
        return bool(confirm_reason and confirm_reason.strip()) and confirmed_by is not None
    return False
