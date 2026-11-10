"""Deterministic estimate diff: shop repair plan versus insurer estimate (MH-03, T-4.1.1).

No model is involved. The same two inputs always give the same output regardless of
input order (UT-05). A shop line that cannot be paired confidently becomes
``needs_review``; it is never counted as matched or as a difference and never stops the
other lines from being compared (UT-06).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from sp_core.money import hours_times_rate_cents

__all__ = [
    "CATEGORIES",
    "ENGINE_VERSION",
    "DiffLine",
    "DiffResult",
    "EstimateLine",
    "diff_estimates",
    "normalise_description",
]

ENGINE_VERSION = "diff-1.0.0"

CATEGORIES = (
    "missing_operation",
    "labor_hours_gap",
    "refinish_hours_gap",
    "part_price_gap",
    "part_type_difference",
    "rate_difference",
    "materials_gap",
    "other",
)
_CATEGORY_ORDER = {name: index for index, name in enumerate(CATEGORIES)}
_REFINISH_OPERATIONS = frozenset({"refinish", "blend"})


@dataclass(frozen=True)
class EstimateLine:
    """One parsed or manually entered estimate line, amounts in cents."""

    line_id: str
    line_no: int
    operation: str
    description: str
    line_total_cents: int
    part_number: str | None = None
    part_type: str | None = None
    part_price_cents: int | None = None
    labor_hours: Decimal | None = None
    labor_rate_cents: int | None = None


@dataclass(frozen=True)
class DiffLine:
    """One proposed supplement line. ``key`` is stable across document versions."""

    key: str
    category: str
    match_state: str  # "matched" | "needs_review"
    description: str
    requested_cents: int
    hours_delta: Decimal | None
    shop_line_id: str
    insurer_line_id: str | None
    reason: str = ""


@dataclass(frozen=True)
class DiffResult:
    engine_version: str
    lines: tuple[DiffLine, ...]
    compared_shop_lines: int
    needs_review_count: int
    differences_total_cents: int  # excludes needs_review lines
    matched_without_difference: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_SPACE_RE = re.compile(r"\s+")


def normalise_description(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return _SPACE_RE.sub(" ", _PUNCT_RE.sub(" ", folded)).strip()


def _norm_part(part_number: str | None) -> str | None:
    if not part_number:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", part_number).upper()
    return cleaned or None


def _line_key(line: EstimateLine) -> str:
    part = _norm_part(line.part_number) or "-"
    return f"{line.operation}|{normalise_description(line.description)}|{part}"


def _labor_cents(line: EstimateLine) -> int | None:
    if line.labor_hours is None or line.labor_rate_cents is None:
        return None
    return hours_times_rate_cents(line.labor_hours, line.labor_rate_cents)


def _requested_for_missing(line: EstimateLine) -> int:
    labor = _labor_cents(line)
    if labor is None:
        return max(line.line_total_cents, 0)
    return max(labor + (line.part_price_cents or 0), 0)


def _candidates(shop: EstimateLine, insurer_lines: Sequence[EstimateLine]) -> list[EstimateLine]:
    shop_desc = normalise_description(shop.description)
    shop_part = _norm_part(shop.part_number)
    found: dict[str, EstimateLine] = {}
    for ins in insurer_lines:
        if ins.operation != shop.operation:
            continue
        same_desc = normalise_description(ins.description) == shop_desc
        same_part = shop_part is not None and _norm_part(ins.part_number) == shop_part
        if same_desc or same_part:
            found[ins.line_id] = ins
    return [found[k] for k in sorted(found)]


def _compare_pair(shop: EstimateLine, ins: EstimateLine, base_key: str) -> list[DiffLine]:
    out: list[DiffLine] = []

    def add(category: str, cents: int, hours: Decimal | None, why: str, *, keep_zero: bool = False) -> None:
        if cents > 0 or (keep_zero and cents == 0):
            out.append(
                DiffLine(
                    key=f"{base_key}#{category}",
                    category=category,
                    match_state="matched",
                    description=shop.description,
                    requested_cents=cents,
                    hours_delta=hours,
                    shop_line_id=shop.line_id,
                    insurer_line_id=ins.line_id,
                    reason=why,
                )
            )

    if shop.operation == "materials":
        add("materials_gap", shop.line_total_cents - ins.line_total_cents, None, "materials total above insurer")
        return out

    labor_explained = False
    if shop.labor_hours is not None and shop.labor_rate_cents is not None:
        ins_hours = ins.labor_hours if ins.labor_hours is not None else Decimal("0")
        ins_rate = ins.labor_rate_cents if ins.labor_rate_cents is not None else shop.labor_rate_cents
        hours_gap = shop.labor_hours - ins_hours
        if hours_gap > 0:
            category = "refinish_hours_gap" if shop.operation in _REFINISH_OPERATIONS else "labor_hours_gap"
            add(category, hours_times_rate_cents(hours_gap, shop.labor_rate_cents), hours_gap, "more hours")
            labor_explained = True
        rate_gap = shop.labor_rate_cents - ins_rate
        if rate_gap > 0 and ins_hours > 0:
            add("rate_difference", hours_times_rate_cents(min(ins_hours, shop.labor_hours), rate_gap), None, "higher rate")
            labor_explained = True

    shop_price = shop.part_price_cents
    ins_price = ins.part_price_cents
    part_explained = False
    if shop.part_type and ins.part_type and shop.part_type != ins.part_type:
        # A part-type change is a difference the Estimator must see even with no price gap.
        gap = max((shop_price or 0) - (ins_price or 0), 0)
        add("part_type_difference", gap, None, "part type differs", keep_zero=True)
        part_explained = True
    elif shop_price is not None and ins_price is not None and shop_price > ins_price:
        add("part_price_gap", shop_price - ins_price, None, "higher part price")
        part_explained = True

    if not out and not labor_explained and not part_explained:
        add("other", shop.line_total_cents - ins.line_total_cents, None, "line total above insurer")
    return out


def diff_estimates(shop_lines: Sequence[EstimateLine], insurer_lines: Sequence[EstimateLine]) -> DiffResult:
    """Compare every shop line with the insurer estimate. Order-independent and pure."""
    shop_sorted = sorted(shop_lines, key=lambda line: (line.line_no, line.line_id))
    ins_sorted = sorted(insurer_lines, key=lambda line: (line.line_no, line.line_id))
    key_counts: dict[str, int] = {}
    produced: list[DiffLine] = []
    needs_review = 0
    matched_clean = 0

    for shop in shop_sorted:
        base = _line_key(shop)
        occurrence = key_counts.get(base, 0)
        key_counts[base] = occurrence + 1
        base_key = f"{base}@{occurrence}"
        candidates = _candidates(shop, ins_sorted)
        free_text = shop.operation == "other" and _norm_part(shop.part_number) is None

        if len(candidates) > 1 or (free_text and not candidates):
            needs_review += 1
            produced.append(
                DiffLine(
                    key=f"{base_key}#review",
                    category="other",
                    match_state="needs_review",
                    description=shop.description,
                    requested_cents=max(shop.line_total_cents, 0),
                    hours_delta=None,
                    shop_line_id=shop.line_id,
                    insurer_line_id=None,
                    reason="ambiguous pairing" if candidates else "free-text line cannot be paired",
                )
            )
            continue
        if not candidates:
            requested = _requested_for_missing(shop)
            produced.append(
                DiffLine(
                    key=f"{base_key}#missing_operation",
                    category="missing_operation",
                    match_state="matched",
                    description=shop.description,
                    requested_cents=requested,
                    hours_delta=shop.labor_hours,
                    shop_line_id=shop.line_id,
                    insurer_line_id=None,
                    reason="not on insurer estimate",
                )
            )
            continue
        pair_lines = _compare_pair(shop, candidates[0], base_key)
        if not pair_lines:
            matched_clean += 1
        produced.extend(pair_lines)

    produced.sort(key=lambda d: (d.key.split("#")[0], _CATEGORY_ORDER[d.category], d.key))
    total = sum(d.requested_cents for d in produced if d.match_state != "needs_review")
    return DiffResult(
        engine_version=ENGINE_VERSION,
        lines=tuple(produced),
        compared_shop_lines=len(shop_sorted) - needs_review,
        needs_review_count=needs_review,
        differences_total_cents=total,
        matched_without_difference=matched_clean,
    )
