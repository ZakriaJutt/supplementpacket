"""Unit tests for pure domain rules: UT-01, UT-02, UT-04, UT-05, UT-06, UT-13, UT-14, UT-16, UT-19."""

from __future__ import annotations

import random
import uuid
from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from sp_core.approval import LineSnapshot, freeze_blockers, review_components, review_fingerprint
from sp_core.dates import business_days_between
from sp_core.diff import EstimateLine, diff_estimates
from sp_core.email_draft import build_email_draft
from sp_core.jobs import decide_transition
from sp_core.money import format_cents, hours_times_rate_cents, parse_cents, round_half_up
from sp_core.reconcile import reconcile
from sp_files import build_object_key


# UT-01 -------------------------------------------------------------------------------------
def test_ut01_money_parse_and_format_round_trip() -> None:
    assert parse_cents("1,284.50") == 128450
    assert parse_cents("0.1") == 10
    assert parse_cents("-3.00") == -300
    for cents in (128450, 10, -300, 0, 1, 99, 123456789):
        assert parse_cents(format_cents(cents)) == cents


@given(st.integers(min_value=-(10**12), max_value=10**12))
def test_ut01_round_trip_property(cents: int) -> None:
    assert parse_cents(format_cents(cents)) == cents


def test_ut01_half_up_rounding_is_exact() -> None:
    assert hours_times_rate_cents(Decimal("1.25"), 5) == 6  # 6.25 -> 6
    assert hours_times_rate_cents(Decimal("0.50"), 5) == 3  # 2.5 -> 3
    assert round_half_up(Decimal("-2.5")) == -3


# UT-02 -------------------------------------------------------------------------------------
def test_ut02_reconcile_flags_difference() -> None:
    lines = [400000, 21210]
    rec = reconcile(lines, 426210)
    assert sum(lines) == 421210
    assert rec.status == "unreconciled"
    assert rec.difference_cents == 5000
    assert reconcile(lines, 421211).status == "reconciled"  # within USD 0.01
    assert reconcile(lines, 421212).status == "unreconciled"


# UT-04 -------------------------------------------------------------------------------------
def test_ut04_missing_blend_operation() -> None:
    shop = [EstimateLine("s1", 1, "blend", "Blend fender 1.2 h refinish", 6480, labor_hours=Decimal("1.2"), labor_rate_cents=5400)]
    result = diff_estimates(shop, [])
    assert len(result.lines) == 1
    line = result.lines[0]
    assert line.category == "missing_operation"
    assert line.requested_cents == hours_times_rate_cents(Decimal("1.2"), 5400) == 6480
    assert line.match_state == "matched"


# UT-05 -------------------------------------------------------------------------------------
_OPS = ["replace", "repair", "refinish", "blend", "materials", "other", "scan"]


def _line(draw: st.DrawFn, prefix: str, index: int) -> EstimateLine:
    op = draw(st.sampled_from(_OPS))
    hours = draw(st.one_of(st.none(), st.decimals(min_value=0, max_value=20, places=2)))
    rate = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=20000)))
    price = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=200000)))
    return EstimateLine(
        line_id=f"{prefix}{index}",
        line_no=index,
        operation=op,
        description=draw(st.sampled_from(["Bumper", "Fender", "Hood", "Door shell", "Corrosion protection", "Misc"])),
        line_total_cents=draw(st.integers(min_value=0, max_value=300000)),
        part_number=draw(st.one_of(st.none(), st.sampled_from(["P-1", "P-2", "P-3"]))),
        part_type=draw(st.one_of(st.none(), st.sampled_from(["oem", "aftermarket"]))),
        part_price_cents=price,
        labor_hours=hours,
        labor_rate_cents=rate,
    )


@st.composite
def estimate_pair(draw: st.DrawFn) -> tuple[list[EstimateLine], list[EstimateLine]]:
    shop = [_line(draw, "s", i) for i in range(1, draw(st.integers(1, 12)) + 1)]
    insurer = [_line(draw, "i", i) for i in range(1, draw(st.integers(0, 12)) + 1)]
    return shop, insurer


@settings(max_examples=60, deadline=None)
@given(estimate_pair(), st.randoms(use_true_random=False))
def test_ut05_diff_is_reproducible_and_order_independent(pair: tuple[list[EstimateLine], list[EstimateLine]], rnd: random.Random) -> None:
    shop, insurer = pair
    first = diff_estimates(shop, insurer)
    for _ in range(100):
        assert diff_estimates(shop, insurer) == first
    shuffled_shop, shuffled_ins = shop[:], insurer[:]
    rnd.shuffle(shuffled_shop)
    rnd.shuffle(shuffled_ins)
    assert diff_estimates(shuffled_shop, shuffled_ins) == first
    assert all(line.requested_cents >= 0 for line in first.lines)


# UT-06 -------------------------------------------------------------------------------------
def test_ut06_ambiguous_free_text_line_needs_review() -> None:
    shop = [
        EstimateLine(f"s{i}", i, "repair", f"Panel {i}", 10000 + i, labor_hours=Decimal("2.0"), labor_rate_cents=5000) for i in range(1, 30)
    ]
    insurer = [
        EstimateLine(f"i{i}", i, "repair", f"Panel {i}", 9000, labor_hours=Decimal("1.5"), labor_rate_cents=5000) for i in range(1, 30)
    ]
    shop.append(EstimateLine("s30", 30, "other", "Additional labour as discussed", 25000))
    result = diff_estimates(shop, insurer)
    review = [line for line in result.lines if line.match_state == "needs_review"]
    assert len(review) == 1 and review[0].shop_line_id == "s30"
    assert result.compared_shop_lines == 29
    compared = {line.shop_line_id for line in result.lines if line.match_state == "matched"}
    assert compared == {f"s{i}" for i in range(1, 30)}
    assert result.differences_total_cents == 29 * hours_times_rate_cents(Decimal("0.5"), 5000)  # excludes the needs_review line


def test_ut06_two_candidates_are_ambiguous() -> None:
    shop = [EstimateLine("s1", 1, "repair", "Door", 10000)]
    insurer = [EstimateLine("i1", 1, "repair", "Door", 5000), EstimateLine("i2", 2, "repair", "Door", 6000)]
    result = diff_estimates(shop, insurer)
    assert [line.match_state for line in result.lines] == ["needs_review"]
    assert result.differences_total_cents == 0


# UT-08 (pure part) -------------------------------------------------------------------------
def _snap(line_id: str, status: str, match: str = "matched") -> LineSnapshot:
    return LineSnapshot(line_id, 1, status, match, "diff", "other", "x", 100, None, "explanation long enough here", ())


def test_ut08_freeze_blockers_list_draft_and_needs_review() -> None:
    problems = freeze_blockers([_snap("a", "draft"), _snap("b", "draft", "needs_review")])
    assert {p.item for p in problems} == {"line:a", "line:b"}
    assert {p.reason for p in problems} == {"not approved", "needs review"}


# UT-13 -------------------------------------------------------------------------------------
def test_ut13_stale_completion_discarded() -> None:
    decision = decide_transition("running", 3, "succeeded", 2)
    assert not decision.accepted and "stale" in decision.reason
    assert decide_transition("running", 3, "succeeded", 3).new_version == 4
    assert not decide_transition("succeeded", 4, "running", 4).accepted


# UT-14 -------------------------------------------------------------------------------------
def test_ut14_keys_are_tenant_prefixed_without_file_names() -> None:
    sha = "ab" * 32
    ro, doc = uuid.uuid4(), uuid.uuid4()
    a, b = uuid.uuid4(), uuid.uuid4()
    key_a = build_object_key(tenant_id=a, ro_id=ro, purpose="photo", document_id=doc, sha256=sha, content_type="image/jpeg")
    key_b = build_object_key(tenant_id=b, ro_id=ro, purpose="photo", document_id=doc, sha256=sha, content_type="image/jpeg")
    assert key_a.startswith(f"t/{a}/") and key_b.startswith(f"t/{b}/") and key_a != key_b
    assert key_a == f"t/{a}/ro/{ro}/photo/{doc}/{sha}.jpg"
    for bad in ("../etc/passwd", "IMG 0001.JPG"):
        try:
            build_object_key(tenant_id=a, ro_id=ro, purpose="photo", document_id=doc, sha256=bad, content_type="image/jpeg")
        except ValueError:
            continue
        raise AssertionError("a non-hash value was accepted into a key")


# UT-16 -------------------------------------------------------------------------------------
def test_ut16_business_days() -> None:
    friday = date(2026, 11, 6)
    assert friday.weekday() == 4
    assert business_days_between(friday, date(2026, 11, 11)) == 3


# UT-19 -------------------------------------------------------------------------------------
def test_ut19_email_draft_amount_rule_and_fingerprint() -> None:
    base = {"ro_number": "RO-1", "claim_number": None, "line_count": 3, "requested_total_cents": 128450}
    bad = build_email_draft(**base, free_paragraph="Please also consider USD 1,500 for storage.")
    assert not bad.ok and "USD 1,500" in bad.problems[0]
    same_total = build_email_draft(**base, free_paragraph="The requested total is USD 1,284.50.")
    assert same_total.ok
    first = build_email_draft(**base, free_paragraph="Photos attached for each line.")
    second = build_email_draft(**base, free_paragraph="Photos are attached for every line.")
    assert first.ok and second.ok
    lines = [_snap("a", "approved")]
    fp1 = review_fingerprint(review_components(lines, email_draft=first.text, recipient={"claim_number": None}))
    fp2 = review_fingerprint(review_components(lines, email_draft=second.text, recipient={"claim_number": None}))
    assert fp1 != fp2
    assert "claim" not in first.text  # a missing claim number is left out, never a placeholder


def test_b1_008_email_guard_catches_trailing_symbols_and_spelled_amounts() -> None:
    base = {"ro_number": "RO-1", "claim_number": None, "line_count": 1, "requested_total_cents": 128450}
    for text in (
        "We ask 1500$ for storage.",
        "Storage is $ 1 500.",
        "Add fifteen hundred dollars for storage.",
        "Storage 1.500,00 USD",
        "Two hundred bucks extra.",
    ):
        assert not build_email_draft(**base, free_paragraph=text).ok, text
    for text in ("Total USD 1,284.50 as requested.", "The total is 1,284.50 USD.", "Photos attached for each line."):
        assert build_email_draft(**base, free_paragraph=text).ok, text
