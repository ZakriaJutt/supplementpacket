"""Baseline rows, pilot counts and the pilot report (MH-09; T-5.1.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem
from sp_api.services import inputs
from sp_api.services.common import check_version, get_or_404, lock_or_404, to_dict
from sp_core.dates import pilot_day_date, pilot_day_end
from sp_core.ledger import SUPPLEMENT_PAYMENT_KINDS
from sp_core.permissions import Action
from sp_core.pilot import (
    BaselineRow,
    PilotCounts,
    PilotPacket,
    PilotTerms,
    pm1_incremental_collected,
    pm2_checklist_collected,
    refund_test,
)
from sp_db.models import BaselineRo, Document, Location, Packet, PacketLine, Payment, Pilot, RepairOrder, Tenant

__all__ = ["add_baseline_row", "list_baseline", "pilot_report", "set_counts", "set_vendor_late_drafts"]


def add_baseline_row(ctx: Ctx, db: Session, body: dict[str, Any]) -> dict[str, Any]:
    ctx.require(Action.EDIT_BASELINE, "baseline_ro", uuid.UUID(int=0))
    location_id = inputs.a_uuid(body, "location_id")
    assert location_id is not None
    location = get_or_404(db, Location, location_id)
    source_note = (inputs.text_field(body, "source_note") or "").strip()
    if not source_note:
        raise Problem(422, "Source note required")
    ro_label = inputs.text_field(body, "ro_label", required=True)
    closed_month = inputs.a_date(body, "closed_month")
    row = BaselineRo(
        tenant_id=ctx.tenant_id,
        location_id=location.id,
        ro_label=ro_label,
        closed_month=closed_month,
        insurer_name=inputs.text_field(body, "insurer_name"),
        requested_cents=inputs.cents(body, "requested_cents", required=False),  # missing stays missing: never a placeholder
        approved_cents=inputs.cents(body, "approved_cents", required=False),
        collected_cents=inputs.cents(body, "collected_cents", required=False),
        first_request_on=inputs.a_date(body, "first_request_on", required=False),
        approved_on=inputs.a_date(body, "approved_on", required=False),
        collected_on=inputs.a_date(body, "collected_on", required=False),
        source_note=source_note,
        entered_by=ctx.user_id,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    ctx.audit(db, "baseline.row_added", "baseline_ro", row.id, None, {"ro_label": row.ro_label})
    return inputs.with_notice(to_dict(row))


def list_baseline(db: Session) -> list[dict[str, Any]]:
    return [to_dict(r) for r in db.execute(select(BaselineRo).order_by(BaselineRo.ro_label)).scalars()]


COUNT_KEYS = ("baseline_insurer_ro_count", "baseline_supplemented_ro_count", "window_insurer_ro_count")


def set_counts(ctx: Ctx, db: Session, pilot_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    pilot = lock_or_404(db, Pilot, pilot_id)
    ctx.require(Action.EDIT_BASELINE, "pilot", pilot.id)
    check_version(pilot, if_match)
    before = to_dict(pilot)
    for key in COUNT_KEYS:
        if key in body:
            setattr(pilot, key, inputs.an_int(body, key))
    if "counts_source_note" in body:
        pilot.counts_source_note = inputs.text_field(body, "counts_source_note")
    if (
        pilot.baseline_counts_supplied_at is None
        and pilot.baseline_insurer_ro_count is not None
        and pilot.baseline_supplemented_ro_count is not None
    ):
        # When the two baseline counts were first both supplied: condition (a) needs it (B1-003).
        pilot.baseline_counts_supplied_at = datetime.now(UTC)
    pilot.row_version += 1
    db.flush()
    keys = (*COUNT_KEYS, "baseline_counts_supplied_at")
    ctx.audit(db, "pilot.counts_set", "pilot", pilot.id, {k: before[k] for k in keys}, {k: to_dict(pilot)[k] for k in keys})
    return to_dict(pilot)


def set_vendor_late_drafts(ctx: Ctx, db: Session, pilot_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    """The vendor records how many drafts it returned later than 1 business day (condition (b), B1-003)."""
    pilot = lock_or_404(db, Pilot, pilot_id)
    ctx.require(Action.RECORD_VENDOR_DRAFTS, "pilot", pilot.id)
    check_version(pilot, if_match)
    count = inputs.an_int(body, "vendor_late_draft_count")
    if count is None:
        raise Problem(422, "Missing field", "vendor_late_draft_count is required (0 when none were late)")
    before = {"vendor_late_draft_count": pilot.vendor_late_draft_count}
    pilot.vendor_late_draft_count = count
    pilot.vendor_late_drafts_recorded_at = datetime.now(UTC)
    pilot.vendor_late_drafts_recorded_by = ctx.user_id
    pilot.row_version += 1
    db.flush()
    ctx.audit(db, "pilot.vendor_late_drafts_set", "pilot", pilot.id, before, {"vendor_late_draft_count": count})
    return to_dict(pilot)


_APPROVED = ("approved_full", "approved_partial")


def _pilot_packets(db: Session, pilot: Pilot, timezone: str) -> tuple[list[PilotPacket], list[dict[str, str]]]:
    """One qualifying unit per supersede chain whose first in-window send is in days 1 to 30 (B1-001).

    Amounts come from the chain's live packet only (carried responses, re-pointed payments), so a
    sent packet is never dropped by a correction and never counted twice. An insurer approval counts
    in A only with a response date in the window and a response document uploaded by day 60 (B1-002).
    """
    window_end = pilot_day_date(pilot.start_date, 30)
    day60 = pilot_day_date(pilot.start_date, 60)
    day60_end = pilot_day_end(pilot.start_date, 60, timezone)
    day90 = pilot_day_date(pilot.start_date, 90)
    ro_ids = list(db.execute(select(RepairOrder.id).where(RepairOrder.location_id == pilot.location_id)).scalars())
    # Drafts the vendor returned later than 1 business day count as qualifying for (b) and join (c)'s denominator.
    out: list[PilotPacket] = [
        PilotPacket(f"vendor-late-draft-{i + 1}", 0, False, False, vendor_draft_late=True)
        for i in range(pilot.vendor_late_draft_count or 0)
    ]
    excluded: list[dict[str, str]] = []
    if not ro_ids:
        return out, excluded
    by_ro: dict[uuid.UUID, list[Packet]] = {}
    for packet in db.execute(select(Packet).where(Packet.ro_id.in_(ro_ids)).order_by(Packet.version)).scalars():
        by_ro.setdefault(packet.ro_id, []).append(packet)
    for chain in by_ro.values():
        sent_in_window = [p for p in chain if p.sent_on is not None and pilot.start_date <= p.sent_on <= window_end]
        live = next((p for p in chain if p.status in ("frozen", "sent")), None)
        if not sent_in_window or live is None:
            continue
        first = min(sent_in_window, key=lambda p: (p.sent_on, p.version))
        sent_line_ids = set(
            db.execute(
                select(PacketLine.supplement_line_id).where(
                    PacketLine.packet_id.in_([p.id for p in sent_in_window]), PacketLine.request_state == "requested"
                )
            ).scalars()
        )
        lines = [
            pl
            for pl in db.execute(select(PacketLine).where(PacketLine.packet_id == live.id)).scalars()
            if pl.request_state == "requested" and pl.supplement_line_id in sent_line_ids
        ]
        doc_ids = {pl.response_document_id for pl in lines if pl.response_document_id}
        docs_on_time = (
            set(db.execute(select(Document.id).where(Document.id.in_(doc_ids), Document.uploaded_at <= day60_end)).scalars())
            if doc_ids
            else set()
        )
        approved = checklist = 0
        for pl in lines:
            if pl.response_status not in _APPROVED or not pl.approved_cents:
                continue
            reason = None
            if pl.response_date is None:
                reason = "no response date"
            elif not pilot.start_date <= pl.response_date <= day60:
                reason = "response date outside days 1 to 60"
            elif pl.response_document_id is None:
                reason = "no response document"
            elif pl.response_document_id not in docs_on_time:
                reason = "response document uploaded after day 60"
            if reason:
                excluded.append({"packet_line_id": str(pl.id), "reason": reason})
                continue
            approved += pl.approved_cents
            if pl.origin == "checklist":
                checklist += pl.approved_cents
        chain_ids = [p.id for p in chain]
        collected = sum(
            p.amount_cents
            for p in db.execute(
                select(Payment).where(
                    Payment.packet_id.in_(chain_ids),
                    Payment.kind.in_(tuple(SUPPLEMENT_PAYMENT_KINDS)),
                    Payment.remittance_document_id.is_not(None),
                    Payment.paid_on <= day90,
                )
            ).scalars()
        )
        out.append(
            PilotPacket(
                packet_id=str(first.id),
                insurer_approved_cents_day60=approved,
                response_document_by_day60=bool(docs_on_time),
                sent_in_window=True,
                collected_evidenced_cents_day90=collected,
                checklist_approved_cents=checklist,
            )
        )
    return out, excluded


def pilot_report(db: Session, pilot_id: uuid.UUID) -> dict[str, Any]:
    pilot = get_or_404(db, Pilot, pilot_id)
    tenant = db.execute(select(Tenant)).scalar_one()
    rows = [
        BaselineRow(
            ro_label=r.ro_label,
            requested_cents=r.requested_cents,
            approved_cents=r.approved_cents,
            collected_cents=r.collected_cents,
            created_at=r.created_at,
            first_request_on=r.first_request_on,
            approved_on=r.approved_on,
            collected_on=r.collected_on,
        )
        for r in db.execute(select(BaselineRo).where(BaselineRo.location_id == pilot.location_id)).scalars()
    ]
    counts = PilotCounts(pilot.baseline_insurer_ro_count, pilot.baseline_supplemented_ro_count, pilot.window_insurer_ro_count)
    terms = PilotTerms(
        start_date=pilot.start_date,
        timezone=tenant.timezone,
        threshold_cents=pilot.threshold_cents,
        min_packets=pilot.min_packets,
        min_baseline=pilot.min_baseline,
        min_response_share=Fraction(pilot.min_response_share),
    )
    packets, excluded = _pilot_packets(db, pilot, tenant.timezone)
    test = refund_test(
        terms,
        counts,
        rows,
        packets,
        counts_supplied_at=pilot.baseline_counts_supplied_at,
        late_drafts_recorded=pilot.vendor_late_drafts_recorded_at is not None,
    )
    pm1 = pm1_incremental_collected(counts, rows, packets, pilot.min_baseline)
    pm2 = pm2_checklist_collected(packets)
    return {
        "pilot_id": str(pilot.id),
        "terms_version": pilot.terms_version,
        "refund_test": {
            "computable": test.computable,
            "missing": list(test.missing),
            "pilot_insurer_approved_cents": test.pilot_approved_cents,
            "excluded_approvals": excluded,
            "baseline_rate_cents": test.baseline_rate_cents,
            "expected_cents": test.expected_cents,
            "incremental_approved_cents": test.incremental_approved_cents if test.computable else "not computable",
            "conditions": [
                {"name": c.name, "met": "undetermined" if c.met is None else c.met, "detail": c.detail} for c in test.conditions
            ],
            "refund_due": "undetermined" if test.refund_due is None else test.refund_due,
            "refund_result": test.refund_result,
            "counted_packet_ids": list(test.counted_packet_ids),
            "flags": list(test.flags),
        },
        "pm1_incremental_collected_cents": pm1.value_cents if pm1.computable else "not computable",
        "pm1_missing": list(pm1.missing),
        "pm2_checklist_collected_cents": pm2.value_cents,
        "baseline_rows": [{"ro_label": r.ro_label, "complete": r.complete, "entered_at": r.created_at.isoformat()} for r in rows],
    }
