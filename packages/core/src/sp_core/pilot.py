"""Baseline, refund test and pilot metrics (MH-09, Decision 5.1, PRD section 11).

Deterministic. No model, no floats. "Not computable" is a valid result and names the
missing item; a missing baseline amount is never filled with a placeholder.

Rounding rule (recorded in verification-report-fixing.md B1): every derived amount is
computed as an exact fraction and rounded half away from zero to the cent once, at the
point it is reported. The expected amount is ``baseline_total x N / R`` from the exact
fraction, not from the rounded per-RO rate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction

from sp_core.dates import pilot_day_end
from sp_core.money import round_half_up

__all__ = [
    "APPROVED_CUTOFF_DAYS",
    "COLLECTED_CUTOFF_DAYS",
    "BaselineRow",
    "BaselineTotal",
    "Condition",
    "PilotCounts",
    "PilotMetrics",
    "PilotPacket",
    "PilotTerms",
    "RefundTest",
    "baseline_total",
    "pm1_incremental_collected",
    "pm2_checklist_collected",
    "refund_test",
]

APPROVED_CUTOFF_DAYS = 60
COLLECTED_CUTOFF_DAYS = 90
COMPLETENESS_SCALING_SHARE = Fraction(80, 100)


@dataclass(frozen=True)
class BaselineRow:
    ro_label: str
    requested_cents: int | None
    approved_cents: int | None
    collected_cents: int | None
    created_at: datetime
    first_request_on: date | None = None
    approved_on: date | None = None
    collected_on: date | None = None

    @property
    def complete(self) -> bool:
        return None not in (self.requested_cents, self.approved_cents, self.collected_cents)


@dataclass(frozen=True)
class PilotTerms:
    start_date: date
    timezone: str = "America/Los_Angeles"
    threshold_cents: int = 100_000
    min_packets: int = 8
    min_baseline: int = 10
    min_response_share: Fraction = Fraction(80, 100)


@dataclass(frozen=True)
class PilotCounts:
    baseline_insurer_ro_count: int | None  # R
    baseline_supplemented_ro_count: int | None  # S
    window_insurer_ro_count: int | None  # N


@dataclass(frozen=True)
class PilotPacket:
    packet_id: str
    insurer_approved_cents_day60: int
    response_document_by_day60: bool
    sent_in_window: bool
    vendor_draft_late: bool = False  # vendor returned the draft later than 1 business day
    collected_evidenced_cents_day90: int = 0
    checklist_approved_cents: int = 0

    @property
    def qualifying(self) -> bool:
        return self.sent_in_window or self.vendor_draft_late


@dataclass(frozen=True)
class BaselineTotal:
    computable: bool
    total_cents: Fraction | None
    missing: tuple[str, ...]
    complete_rows: int
    declared_supplemented: int | None
    method: str  # "scaled_mean" | "highest_row_for_missing" | "not_computable"
    flags: tuple[str, ...] = field(default_factory=tuple)


def _cut_amount(row: BaselineRow, amount: int, paid_on: date | None, cutoff_days: int) -> tuple[int, bool]:
    """Apply the cut-off rule; returns (amount within the cut, row_had_dates)."""
    if row.first_request_on is None or paid_on is None:
        return amount, False
    if paid_on > row.first_request_on + timedelta(days=cutoff_days):
        return 0, True
    return amount, True


def baseline_total(rows: Sequence[BaselineRow], counts: PilotCounts, measure: str, min_rows: int = 10) -> BaselineTotal:
    """Baseline total for ``measure`` in ("approved", "collected") under Decision 5.1."""
    if measure not in ("approved", "collected"):
        raise ValueError("measure must be approved or collected")
    missing: list[str] = []
    if counts.baseline_insurer_ro_count is None:
        missing.append("baseline insurer-paid RO count")
    if counts.baseline_supplemented_ro_count is None:
        missing.append("declared supplemented RO count")
    complete = [r for r in rows if r.complete]
    if len(complete) < min_rows:
        missing.append(f"at least {min_rows} complete baseline rows (have {len(complete)})")
    flags: list[str] = []
    if missing:
        return BaselineTotal(False, None, tuple(missing), len(complete), counts.baseline_supplemented_ro_count, "not_computable")

    cutoff = APPROVED_CUTOFF_DAYS if measure == "approved" else COLLECTED_CUTOFF_DAYS
    values: list[int] = []
    undated = 0
    for row in sorted(complete, key=lambda r: r.ro_label):
        raw = row.approved_cents if measure == "approved" else row.collected_cents
        assert raw is not None
        paid_on = row.approved_on if measure == "approved" else row.collected_on
        value, dated = _cut_amount(row, raw, paid_on, cutoff)
        if not dated:
            undated += 1
        values.append(value)
    if undated:
        flags.append(f"uncensored: {undated} baseline rows without dates count in full")

    declared = counts.baseline_supplemented_ro_count
    assert declared is not None
    if declared < len(complete):
        flags.append("declared supplemented count is below the number of complete rows; complete rows used")
        declared = len(complete)
    c = len(complete)
    if Fraction(c, declared) >= COMPLETENESS_SCALING_SHARE:
        total = Fraction(sum(values), c) * declared
        method = "scaled_mean"
    else:
        total = Fraction(sum(values) + (declared - c) * max(values))
        method = "highest_row_for_missing"
        flags.append(
            f"incomplete baseline ({c} of {declared} rows complete): each missing row valued at the highest "
            "complete row, resolved in the shop's favour"
        )
    return BaselineTotal(True, total, (), c, declared, method, tuple(flags))


@dataclass(frozen=True)
class Condition:
    name: str
    met: bool
    detail: str


@dataclass(frozen=True)
class RefundTest:
    computable: bool
    missing: tuple[str, ...]
    pilot_approved_cents: int  # A
    baseline_rate_cents: int | None  # b, rounded for display
    expected_cents: int | None  # b x N, rounded once from the exact fraction
    incremental_approved_cents: int | None  # A - b x N
    conditions: tuple[Condition, ...]
    refund_due: bool
    counted_packet_ids: tuple[str, ...]
    flags: tuple[str, ...]


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0%"
    return f"{round_half_up(Fraction(100 * numerator, denominator))}%"


def refund_test(terms: PilotTerms, counts: PilotCounts, baseline_rows: Sequence[BaselineRow], packets: Sequence[PilotPacket]) -> RefundTest:
    qualifying = sorted((p for p in packets if p.qualifying), key=lambda p: p.packet_id)
    pilot_approved = sum(p.insurer_approved_cents_day60 for p in qualifying)

    base = baseline_total(baseline_rows, counts, "approved", terms.min_baseline)
    missing = list(base.missing)
    if counts.window_insurer_ro_count is None:
        missing.append("window insurer-paid RO count (N)")
    if counts.baseline_insurer_ro_count == 0:
        missing.append("baseline insurer-paid RO count is 0")

    rate = expected = incremental = None
    flags = list(base.flags)
    if not missing:
        assert base.total_cents is not None
        r = counts.baseline_insurer_ro_count
        n = counts.window_insurer_ro_count
        assert r is not None and n is not None
        exact_rate = base.total_cents / r
        exact_expected = exact_rate * n
        rate = round_half_up(exact_rate)
        expected = round_half_up(exact_expected)
        incremental = round_half_up(pilot_approved - exact_expected)
        if incremental < 0:
            flags.append("incremental approved dollars are negative")

    # (a) the two baseline counts and >= min complete rows supplied by day 7.
    day7_end = pilot_day_end(terms.start_date, 7, terms.timezone)
    on_time_complete = [r for r in baseline_rows if r.complete and r.created_at <= day7_end]
    counts_given = counts.baseline_insurer_ro_count is not None and counts.baseline_supplemented_ro_count is not None
    cond_a = Condition(
        "a",
        counts_given and len(on_time_complete) >= terms.min_baseline,
        f"{len(on_time_complete)} complete baseline rows entered by day 7; counts {'supplied' if counts_given else 'missing'}",
    )
    cond_b = Condition(
        "b",
        len(qualifying) >= terms.min_packets,
        f"{len(qualifying)} qualifying packets (minimum {terms.min_packets})",
    )
    with_docs = sum(1 for p in qualifying if p.response_document_by_day60)
    share_ok = bool(qualifying) and Fraction(with_docs, len(qualifying)) >= terms.min_response_share
    cond_c = Condition(
        "c",
        share_ok,
        f"{with_docs} of {len(qualifying)} qualifying packets have a response document by day 60 ({_percent(with_docs, len(qualifying))})",
    )
    conditions = (cond_a, cond_b, cond_c)
    refund_due = not missing and incremental is not None and incremental < terms.threshold_cents and all(c.met for c in conditions)
    return RefundTest(
        computable=not missing,
        missing=tuple(missing),
        pilot_approved_cents=pilot_approved,
        baseline_rate_cents=rate,
        expected_cents=expected,
        incremental_approved_cents=incremental,
        conditions=conditions,
        refund_due=refund_due,
        counted_packet_ids=tuple(p.packet_id for p in qualifying),
        flags=tuple(flags),
    )


@dataclass(frozen=True)
class PilotMetrics:
    computable: bool
    missing: tuple[str, ...]
    value_cents: int | None
    flags: tuple[str, ...]


def pm1_incremental_collected(
    counts: PilotCounts, baseline_rows: Sequence[BaselineRow], packets: Sequence[PilotPacket], min_rows: int = 10
) -> PilotMetrics:
    """PM-1: evidenced collected on qualifying packets minus baseline collected rate x N."""
    base = baseline_total(baseline_rows, counts, "collected", min_rows)
    missing = list(base.missing)
    if counts.window_insurer_ro_count is None:
        missing.append("window insurer-paid RO count (N)")
    if counts.baseline_insurer_ro_count == 0:
        missing.append("baseline insurer-paid RO count is 0")
    if missing:
        return PilotMetrics(False, tuple(missing), None, base.flags)
    assert base.total_cents is not None and counts.baseline_insurer_ro_count and counts.window_insurer_ro_count is not None
    collected = sum(p.collected_evidenced_cents_day90 for p in packets if p.qualifying)
    exact = collected - base.total_cents / counts.baseline_insurer_ro_count * counts.window_insurer_ro_count
    return PilotMetrics(True, (), round_half_up(exact), base.flags)


def pm2_checklist_collected(packets: Sequence[PilotPacket]) -> PilotMetrics:
    """PM-2: collected x (checklist-approved / all approved), summed; an allocation."""
    total = Fraction(0)
    for p in packets:
        if p.qualifying and p.insurer_approved_cents_day60 > 0:
            total += Fraction(p.collected_evidenced_cents_day90 * p.checklist_approved_cents, p.insurer_approved_cents_day60)
    return PilotMetrics(True, (), round_half_up(total), ("allocation: payments arrive per RO",))
