"""Three-amount ledger and refund test: UT-09, UT-10, UT-11 (and variants), UT-12, UT-17, UT-18."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from sp_core.ledger import (
    LedgerPacket,
    LedgerPacketLine,
    LedgerPayment,
    PaymentError,
    ResponseError,
    compute_ro_ledger,
    validate_response,
    validate_supplement_payment,
)
from sp_core.pilot import (
    BaselineRow,
    PilotCounts,
    PilotPacket,
    PilotTerms,
    pm1_incremental_collected,
    pm2_checklist_collected,
    refund_test,
)

START = date(2026, 9, 1)
ON_TIME = datetime(2026, 9, 3, 12, tzinfo=UTC)


# UT-09 -------------------------------------------------------------------------------------
def test_ut09_response_rules() -> None:
    with pytest.raises(ResponseError):
        validate_response(requested_cents=15000, response_status="approved_partial", approved_cents=16000)
    assert (
        validate_response(
            requested_cents=15000, response_status="approved_partial", approved_cents=16000, override_reason="adjuster added tax line"
        )
        == 16000
    )
    assert validate_response(requested_cents=15000, response_status="denied", approved_cents=None, denial_reason="not related") == 0
    assert validate_response(requested_cents=15000, response_status="approved_full", approved_cents=None) == 15000
    with pytest.raises(ResponseError):
        validate_response(requested_cents=15000, response_status="approved_full", approved_cents=14000)
    with pytest.raises(ResponseError):
        validate_response(requested_cents=15000, response_status="denied", approved_cents=500, denial_reason="x")


# UT-10 -------------------------------------------------------------------------------------
def test_ut10_live_packet_only_and_reversal() -> None:
    packets = [LedgerPacket("p1", "superseded"), LedgerPacket("p2", "sent")]
    lines = [
        LedgerPacketLine("p1", 30000, "approved_full", 30000),
        LedgerPacketLine("p2", 30000, "approved_full", 30000),
        LedgerPacketLine("p2", 20000, "no_response", None),
    ]
    payments = [
        LedgerPayment("pay1", "p2", "supplement", 40000, True),
        LedgerPayment("pay2", "p2", "supplement", -5000, False, reverses_payment_id="pay1"),
        LedgerPayment("pay3", None, "original_estimate", 99999, True),
    ]
    ledger = compute_ro_ledger(packets, lines, payments)
    assert ledger.requested_cents == 50000  # live packet only
    assert ledger.insurer_approved_cents == 30000
    assert ledger.collected_evidenced_cents == 35000
    assert ledger.recorded_not_evidenced_cents == 0
    assert ledger.live_packet_ids == ("p2",)
    assert {"requested_cents", "insurer_approved_cents", "collected_evidenced_cents"} <= set(vars(ledger))


# UT-17 -------------------------------------------------------------------------------------
def test_ut17_superseded_packet_contributes_nothing() -> None:
    packets = [LedgerPacket("p1", "superseded"), LedgerPacket("p2", "frozen")]
    lines = [
        LedgerPacketLine("p1", 15000, "approved_full", 15000),  # A
        LedgerPacketLine("p1", 9000, "denied", 0),  # B
        LedgerPacketLine("p2", 15000, "approved_full", 15000),  # A carried forward
        LedgerPacketLine("p2", 7000, "no_response", None),  # B amended
    ]
    payments = [LedgerPayment("pay", "p2", "supplement", 15000, True)]  # re-attributed to p2
    ledger = compute_ro_ledger(packets, lines, payments)
    assert ledger.insurer_approved_cents == 15000
    assert ledger.requested_cents == 22000
    assert ledger.collected_evidenced_cents == 15000


# UT-18 -------------------------------------------------------------------------------------
def test_ut18_payment_evidence_and_over_approved_reason() -> None:
    validate_supplement_payment(
        kind="supplement",
        packet_id="p",
        amount_cents=20000,
        reverses_payment_id=None,
        packet_insurer_approved_cents=20000,
        packet_supplement_paid_cents=0,
        over_approved_reason=None,
    )
    with pytest.raises(PaymentError, match="exceed"):
        validate_supplement_payment(
            kind="supplement",
            packet_id="p",
            amount_cents=5000,
            reverses_payment_id=None,
            packet_insurer_approved_cents=20000,
            packet_supplement_paid_cents=20000,
            over_approved_reason=None,
        )
    validate_supplement_payment(
        kind="supplement",
        packet_id="p",
        amount_cents=5000,
        reverses_payment_id=None,
        packet_insurer_approved_cents=20000,
        packet_supplement_paid_cents=20000,
        over_approved_reason="storage paid on supplement",
    )
    with pytest.raises(PaymentError, match="name the packet"):
        validate_supplement_payment(
            kind="supplement",
            packet_id=None,
            amount_cents=100,
            reverses_payment_id=None,
            packet_insurer_approved_cents=0,
            packet_supplement_paid_cents=0,
            over_approved_reason=None,
        )
    ledger = compute_ro_ledger(
        [LedgerPacket("p", "sent")],
        [LedgerPacketLine("p", 20000, "approved_full", 20000)],
        [LedgerPayment("a", "p", "supplement", 20000, True), LedgerPayment("b", "p", "supplement", 5000, False)],
    )
    assert ledger.collected_evidenced_cents == 20000
    assert ledger.recorded_not_evidenced_cents == 5000


# UT-11 -------------------------------------------------------------------------------------
def _packets(docs: int) -> list[PilotPacket]:
    approved = [22500] * 8 + [0]  # 180000 over 9 qualifying packets
    out = []
    for i in range(9):
        out.append(
            PilotPacket(
                packet_id=f"p{i}",
                insurer_approved_cents_day60=approved[i],
                response_document_by_day60=i < docs,
                sent_in_window=i < 8,
                vendor_draft_late=i == 8,  # drafted late by the vendor and not sent: counted
            )
        )
    return out


def _rows(complete: list[int], incomplete: int) -> list[BaselineRow]:
    rows = [BaselineRow(f"B{i:02d}", v, v, v, ON_TIME) for i, v in enumerate(complete)]
    rows += [BaselineRow(f"X{i:02d}", None, None, None, ON_TIME) for i in range(incomplete)]
    return rows


COUNTS = PilotCounts(baseline_insurer_ro_count=150, baseline_supplemented_ro_count=30, window_insurer_ro_count=40)
TERMS = PilotTerms(start_date=START)


def test_ut11_refund_test_base_case() -> None:
    result = refund_test(TERMS, COUNTS, _rows([15000] * 30, 0), _packets(6))
    assert result.pilot_approved_cents == 180000
    assert result.baseline_rate_cents == 3000
    assert result.expected_cents == 120000
    assert result.incremental_approved_cents == 60000
    a, b, c = result.conditions
    assert a.met and b.met and not c.met
    assert "67%" in c.detail
    assert len(result.counted_packet_ids) == 9
    assert result.refund_due is False


def test_ut11_with_eight_documents_refund_due() -> None:
    result = refund_test(TERMS, COUNTS, _rows([15000] * 30, 0), _packets(8))
    assert "89%" in result.conditions[2].detail
    assert all(c.met for c in result.conditions)
    assert result.refund_due is True


def test_ut11_variant_80_percent_complete_scales_mean() -> None:
    result = refund_test(TERMS, COUNTS, _rows([15000] * 24, 6), _packets(6))
    assert result.baseline_rate_cents == 3000  # 15000 x 30 = 450000 over 150
    assert result.expected_cents == 120000
    assert result.incremental_approved_cents == 60000
    assert result.refund_due is False


def test_ut11_variant_67_percent_complete_uses_highest_row() -> None:
    complete = [40000] + [13000] * 18 + [26000]  # 20 rows totalling 300000, highest 40000
    assert sum(complete) == 300000 and len(complete) == 20
    result = refund_test(TERMS, COUNTS, _rows(complete, 10), _packets(6))
    assert result.baseline_rate_cents == 4667  # 700000 / 150
    assert result.expected_cents == 186667
    assert result.incremental_approved_cents is not None and result.incremental_approved_cents < 0
    assert any("shop's favour" in f for f in result.flags)
    assert result.refund_due is False  # condition (c) still not met


def test_ut11_late_rows_fail_condition_a() -> None:
    late = datetime(2026, 9, 9, tzinfo=UTC)  # after the end of day 7 (2026-09-07 Pacific)
    rows = [BaselineRow(f"B{i:02d}", 15000, 15000, 15000, late) for i in range(30)]
    result = refund_test(TERMS, COUNTS, rows, _packets(8))
    assert not result.conditions[0].met and result.refund_due is False


# UT-12 -------------------------------------------------------------------------------------
def test_ut12_not_computable_names_missing_item() -> None:
    packets = [PilotPacket("p", 10000, True, True, collected_evidenced_cents_day90=10000, checklist_approved_cents=5000)]
    nine = refund_test(TERMS, COUNTS, _rows([15000] * 9, 0), packets)
    assert not nine.computable and any("10 complete baseline rows" in m for m in nine.missing)
    assert nine.incremental_approved_cents is None
    pm1 = pm1_incremental_collected(COUNTS, _rows([15000] * 9, 0), packets)
    assert not pm1.computable and pm1.value_cents is None
    no_window = PilotCounts(150, 30, None)
    twelve = refund_test(TERMS, no_window, _rows([15000] * 12, 0), packets)
    assert not twelve.computable and any("window insurer-paid RO count" in m for m in twelve.missing)
    assert pm2_checklist_collected(packets).value_cents == 5000  # PM-2 still computed


def test_ut12_undated_row_sets_uncensored_flag_and_cutoff_applies() -> None:
    dated = [BaselineRow(f"D{i}", 15000, 15000, 15000, ON_TIME, date(2026, 6, 1), date(2026, 6, 20), date(2026, 7, 1)) for i in range(10)]
    late = BaselineRow("LATE", 15000, 15000, 15000, ON_TIME, date(2026, 6, 1), date(2026, 6, 1) + timedelta(days=61), None)
    undated = BaselineRow("U", 15000, 15000, 15000, ON_TIME)
    result = refund_test(TERMS, PilotCounts(120, 12, 40), [*dated, late, undated], _packets(8))
    assert any("uncensored" in f for f in result.flags)
    # 11 of 12 rows count 15000; the late approval is cut at 60 days: 165000 over 120 ROs.
    assert result.baseline_rate_cents == 1375
