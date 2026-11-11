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
from sp_core.money import round_half_up, round_up

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
    method: str  # "scaled_mean" | "highest_row_valuation" | "not_computable"
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
    undated = 0

    def value_of(row: BaselineRow) -> int | None:
        nonlocal undated
        raw = row.approved_cents if measure == "approved" else row.collected_cents
        if raw is None:
            return None
        paid_on = row.approved_on if measure == "approved" else row.collected_on
        value, dated = _cut_amount(row, raw, paid_on, cutoff)
        if not dated:
            undated += 1
        return value

    ordered = sorted(rows, key=lambda r: r.ro_label)
    complete_values = [v for r in ordered if r.complete and (v := value_of(r)) is not None]
    incomplete_values = [value_of(r) for r in ordered if not r.complete]
    if undated:
        flags.append(f"uncensored: {undated} baseline rows without dates count in full")

    declared = counts.baseline_supplemented_ro_count
    assert declared is not None
    if declared < len(ordered):
        flags.append("declared supplemented count is below the number of baseline rows entered; the rows entered are used")
        declared = len(ordered)
    c = len(complete_values)
    highest = max(complete_values)
    missing_rows = declared - len(ordered)
    # Candidate (i): complete rows scaled to the declared count.
    scaled = Fraction(sum(complete_values), c) * declared
    # Candidate (ii): each incomplete or missing row valued at the highest complete row, or at its own
    # supplied amount for this measure when that is higher. (ii) is never below (i) and never below the
    # sum of supplied amounts, so incomplete rows can never lower the baseline (B1-004 ruling).
    valued_incomplete = [max(v, highest) if v is not None else highest for v in incomplete_values]
    highest_valuation = Fraction(sum(complete_values) + sum(valued_incomplete) + missing_rows * highest)
    total = max(scaled, highest_valuation)
    method = "highest_row_valuation" if highest_valuation >= scaled else "scaled_mean"
    if c < declared:
        flags.append(
            f"incomplete baseline ({c} of {declared} rows complete): baseline is the higher of complete rows scaled "
            f"({c} rows totalling {sum(complete_values)} x {declared}/{c} = {float_free(scaled)}) and the highest-row valuation "
            f"({sum(complete_values)} + {len(valued_incomplete)} incomplete rows at {sum(valued_incomplete)} + {missing_rows} missing rows "
            f"x {highest} = {float_free(highest_valuation)}); resolved in the shop's favour"
        )
    return BaselineTotal(True, total, (), c, declared, method, tuple(flags))


def float_free(value: Fraction) -> str:
    """Exact display of a fraction of cents (no floats)."""
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


@dataclass(frozen=True)
class Condition:
    name: str
    met: bool | None  # None: undetermined, an input the condition needs is not recorded (B1-003)
    detail: str


@dataclass(frozen=True)
class RefundTest:
    computable: bool
    missing: tuple[str, ...]
    pilot_approved_cents: int  # A
    baseline_rate_cents: int | None  # b, rounded up (shop's favour) for display
    expected_cents: int | None  # b x N, rounded up once from the exact fraction
    incremental_approved_cents: int | None  # A - expected_cents, i.e. the exact increment rounded down
    conditions: tuple[Condition, ...]
    refund_due: bool | None  # None: undetermined
    refund_result: str  # "due" | "not_due" | "undetermined"
    counted_packet_ids: tuple[str, ...]
    flags: tuple[str, ...]


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0%"
    return f"{round_half_up(Fraction(100 * numerator, denominator))}%"


def refund_test(
    terms: PilotTerms,
    counts: PilotCounts,
    baseline_rows: Sequence[BaselineRow],
    packets: Sequence[PilotPacket],
    *,
    counts_supplied_at: datetime | None = None,
    late_drafts_recorded: bool = False,
) -> RefundTest:
    """Decision 5.1 refund test.

    Rounding resolves in the shop's favour (B1-007): the rate and the expected amount are rounded up,
    and the increment shown is A minus the expected amount shown, so it equals the exact increment
    rounded down; ``incremental < threshold`` then holds exactly when the exact increment is under it.
    A condition whose inputs are not recorded is undetermined, never a definite answer (B1-003).
    """
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
        rate = round_up(exact_rate)
        expected = round_up(exact_rate * n)
        incremental = pilot_approved - expected
        if incremental < 0:
            flags.append("incremental approved dollars are negative")

    # (a) the two baseline counts and >= min complete rows supplied by day 7.
    day7_end = pilot_day_end(terms.start_date, 7, terms.timezone)
    on_time_complete = [r for r in baseline_rows if r.complete and r.created_at <= day7_end]
    counts_given = counts.baseline_insurer_ro_count is not None and counts.baseline_supplemented_ro_count is not None
    a_met: bool | None
    if not counts_given:
        a_met, a_counts = False, "missing"
    elif counts_supplied_at is None:
        a_met, a_counts = None, "present, but when they were supplied is not recorded"
    elif counts_supplied_at > day7_end:
        a_met, a_counts = False, "supplied after day 7"
    else:
        a_met, a_counts = True, "supplied by day 7"
    if len(on_time_complete) < terms.min_baseline:
        a_met = False
    cond_a = Condition("a", a_met, f"{len(on_time_complete)} complete baseline rows entered by day 7; counts {a_counts}")

    late = [p for p in qualifying if p.vendor_draft_late and not p.sent_in_window]
    b_met: bool | None = len(qualifying) >= terms.min_packets
    b_detail = f"{len(qualifying)} qualifying packets (minimum {terms.min_packets}), of which {len(late)} vendor-late drafts"
    if not b_met and not late_drafts_recorded:
        b_met = None
        b_detail += "; vendor-late drafts are not recorded, so undetermined"
    cond_b = Condition("b", b_met, b_detail)

    with_docs = sum(1 for p in qualifying if p.response_document_by_day60)
    c_met: bool | None = bool(qualifying) and Fraction(with_docs, len(qualifying)) >= terms.min_response_share
    c_detail = (
        f"{with_docs} of {len(qualifying)} qualifying packets have a response document by day 60 ({_percent(with_docs, len(qualifying))})"
    )
    if c_met and not late_drafts_recorded:
        c_met = None  # unrecorded late drafts would join the denominator without documents
        c_detail += "; vendor-late drafts are not recorded, so undetermined"
    cond_c = Condition("c", c_met, c_detail)
    conditions = (cond_a, cond_b, cond_c)

    refund_due: bool | None
    if missing or incremental is None:
        refund_due = None
    elif incremental >= terms.threshold_cents or any(c.met is False for c in conditions):
        refund_due = False
    elif any(c.met is None for c in conditions):
        refund_due = None
    else:
        refund_due = True
    result = {True: "due", False: "not_due", None: "undetermined"}[refund_due]
    return RefundTest(
        computable=not missing,
        missing=tuple(missing),
        pilot_approved_cents=pilot_approved,
        baseline_rate_cents=rate,
        expected_cents=expected,
        incremental_approved_cents=incremental,
        conditions=conditions,
        refund_due=refund_due,
        refund_result=result,
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
    expected = round_up(base.total_cents / counts.baseline_insurer_ro_count * counts.window_insurer_ro_count)
    return PilotMetrics(True, (), collected - expected, base.flags)


def pm2_checklist_collected(packets: Sequence[PilotPacket]) -> PilotMetrics:
    """PM-2: collected x (checklist-approved / all approved), summed; an allocation."""
    total = Fraction(0)
    for p in packets:
        if p.qualifying and p.insurer_approved_cents_day60 > 0:
            total += Fraction(p.collected_evidenced_cents_day90 * p.checklist_approved_cents, p.insurer_approved_cents_day60)
    return PilotMetrics(True, (), round_half_up(total), ("allocation: payments arrive per RO",))
