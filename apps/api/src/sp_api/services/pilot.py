"""Baseline rows, pilot counts and the pilot report (MH-09; T-5.1.3)."""

from __future__ import annotations

import uuid
from datetime import date
from fractions import Fraction
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem
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

__all__ = ["add_baseline_row", "list_baseline", "pilot_report", "set_counts"]


def _opt_int(body: dict[str, Any], key: str) -> int | None:
    value = body.get(key)
    return None if value is None or value == "" else int(value)


def _opt_date(body: dict[str, Any], key: str) -> date | None:
    value = body.get(key)
    return date.fromisoformat(str(value)) if value else None


def add_baseline_row(ctx: Ctx, db: Session, body: dict[str, Any]) -> dict[str, Any]:
    ctx.require(Action.EDIT_BASELINE, "baseline_ro", uuid.UUID(int=0))
    location = get_or_404(db, Location, uuid.UUID(str(body["location_id"])))
    if not str(body.get("source_note") or "").strip():
        raise Problem(422, "Source note required")
    row = BaselineRo(
        tenant_id=ctx.tenant_id,
        location_id=location.id,
        ro_label=str(body["ro_label"]),
        closed_month=date.fromisoformat(str(body["closed_month"])),
        insurer_name=body.get("insurer_name"),
        requested_cents=_opt_int(body, "requested_cents"),  # missing stays missing: never a placeholder
        approved_cents=_opt_int(body, "approved_cents"),
        collected_cents=_opt_int(body, "collected_cents"),
        first_request_on=_opt_date(body, "first_request_on"),
        approved_on=_opt_date(body, "approved_on"),
        collected_on=_opt_date(body, "collected_on"),
        source_note=str(body["source_note"]),
        entered_by=ctx.user_id,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    ctx.audit(db, "baseline.row_added", "baseline_ro", row.id, None, {"ro_label": row.ro_label})
    return to_dict(row)


def list_baseline(db: Session) -> list[dict[str, Any]]:
    return [to_dict(r) for r in db.execute(select(BaselineRo).order_by(BaselineRo.ro_label)).scalars()]


def set_counts(ctx: Ctx, db: Session, pilot_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    pilot = lock_or_404(db, Pilot, pilot_id)
    ctx.require(Action.EDIT_BASELINE, "pilot", pilot.id)
    check_version(pilot, if_match)
    before = to_dict(pilot)
    for key in ("baseline_insurer_ro_count", "baseline_supplemented_ro_count", "window_insurer_ro_count"):
        if key in body:
            setattr(pilot, key, _opt_int(body, key))
    if "counts_source_note" in body:
        pilot.counts_source_note = body["counts_source_note"]
    pilot.row_version += 1
    db.flush()
    keys = ("baseline_insurer_ro_count", "baseline_supplemented_ro_count", "window_insurer_ro_count")
    ctx.audit(db, "pilot.counts_set", "pilot", pilot.id, {k: before[k] for k in keys}, {k: to_dict(pilot)[k] for k in keys})
    return to_dict(pilot)


def _pilot_packets(db: Session, pilot: Pilot, timezone: str) -> list[PilotPacket]:
    window_end = pilot_day_date(pilot.start_date, 30)
    day60 = pilot_day_date(pilot.start_date, 60)
    day60_end = pilot_day_end(pilot.start_date, 60, timezone)
    day90 = pilot_day_date(pilot.start_date, 90)
    ro_ids = [r for r in db.execute(select(RepairOrder.id).where(RepairOrder.location_id == pilot.location_id)).scalars()]
    if not ro_ids:
        return []
    packets = db.execute(select(Packet).where(Packet.ro_id.in_(ro_ids), Packet.status == "sent", Packet.sent_on.is_not(None))).scalars()
    out: list[PilotPacket] = []
    for packet in packets:
        assert packet.sent_on is not None
        in_window = pilot.start_date <= packet.sent_on <= window_end
        if not in_window:
            continue
        lines = list(db.execute(select(PacketLine).where(PacketLine.packet_id == packet.id)).scalars())
        counted = [pl for pl in lines if pl.response_status not in ("withdrawn", "preapproved")]
        approved = sum(pl.approved_cents or 0 for pl in counted if pl.response_date is None or pl.response_date <= day60)
        checklist = sum(
            pl.approved_cents or 0 for pl in counted if pl.origin == "checklist" and (pl.response_date is None or pl.response_date <= day60)
        )
        doc_ids = [pl.response_document_id for pl in lines if pl.response_document_id]
        has_doc = False
        if doc_ids:
            has_doc = db.execute(select(Document.id).where(Document.id.in_(doc_ids), Document.uploaded_at <= day60_end)).first() is not None
        collected = sum(
            p.amount_cents
            for p in db.execute(
                select(Payment).where(
                    Payment.packet_id == packet.id,
                    Payment.kind.in_(tuple(SUPPLEMENT_PAYMENT_KINDS)),
                    Payment.remittance_document_id.is_not(None),
                    Payment.paid_on <= day90,
                )
            ).scalars()
        )
        out.append(
            PilotPacket(
                packet_id=str(packet.id),
                insurer_approved_cents_day60=approved,
                response_document_by_day60=has_doc,
                sent_in_window=True,
                collected_evidenced_cents_day90=collected,
                checklist_approved_cents=checklist,
            )
        )
    return out


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
    packets = _pilot_packets(db, pilot, tenant.timezone)
    test = refund_test(terms, counts, rows, packets)
    pm1 = pm1_incremental_collected(counts, rows, packets, pilot.min_baseline)
    pm2 = pm2_checklist_collected(packets)
    return {
        "pilot_id": str(pilot.id),
        "terms_version": pilot.terms_version,
        "refund_test": {
            "computable": test.computable,
            "missing": list(test.missing),
            "pilot_insurer_approved_cents": test.pilot_approved_cents,
            "baseline_rate_cents": test.baseline_rate_cents,
            "expected_cents": test.expected_cents,
            "incremental_approved_cents": test.incremental_approved_cents if test.computable else "not computable",
            "conditions": [{"name": c.name, "met": c.met, "detail": c.detail} for c in test.conditions],
            "refund_due": test.refund_due,
            "counted_packet_ids": list(test.counted_packet_ids),
            "flags": list(test.flags),
        },
        "pm1_incremental_collected_cents": pm1.value_cents if pm1.computable else "not computable",
        "pm1_missing": list(pm1.missing),
        "pm2_checklist_collected_cents": pm2.value_cents,
        "baseline_rows": [{"ro_label": r.ro_label, "complete": r.complete, "entered_at": r.created_at.isoformat()} for r in rows],
    }
