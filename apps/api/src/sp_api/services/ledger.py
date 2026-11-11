"""Insurer responses, payments and the three-amount ledger per RO (MH-08; T-5.1.1)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem
from sp_api.services import inputs
from sp_api.services.common import check_version, get_or_404, lock_or_404, tenant_now_and_today, to_dict
from sp_core.ledger import (
    SUPPLEMENT_PAYMENT_KINDS,
    LedgerPacket,
    LedgerPacketLine,
    LedgerPayment,
    PaymentError,
    ResponseError,
    compute_ro_ledger,
    validate_response,
    validate_supplement_payment,
)
from sp_core.permissions import Action
from sp_db.models import Document, Packet, PacketLine, Payment, RepairOrder

__all__ = ["packet_chain", "record_payment", "record_response", "reverse_payment", "ro_ledger"]

PAYMENT_KINDS = ("supplement", "supplement_repayment", "original_estimate", "deductible", "other")


def packet_chain(db: Session, packet: Packet) -> set[uuid.UUID]:
    """The packet and every packet it superseded, directly or indirectly."""
    chain = {packet.id}
    current = packet
    while current.supersedes_packet_id and current.supersedes_packet_id not in chain:
        chain.add(current.supersedes_packet_id)
        nxt = db.get(Packet, current.supersedes_packet_id)
        if nxt is None:
            break
        current = nxt
    return chain


def record_response(ctx: Ctx, db: Session, packet_line_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    pl = lock_or_404(db, PacketLine, packet_line_id)
    ctx.require(Action.RECORD_RESPONSE, "packet_line", pl.id)
    check_version(pl, if_match)
    packet = get_or_404(db, Packet, pl.packet_id)
    if packet.status == "superseded":
        raise Problem(409, "Superseded packet", "record the response on the packet that superseded this one")
    if pl.request_state == "withdrawn":
        raise Problem(409, "Withdrawn line", "this line was withdrawn by the superseding packet and has no insurer response")
    denial = inputs.text_field(body, "denial_reason")
    override = inputs.text_field(body, "override_reason")
    approved_in = inputs.cents(body, "approved_cents", required=False)
    now, today = tenant_now_and_today(db)
    response_date = inputs.a_date(body, "response_date", required=False)
    if response_date is not None and response_date > today:
        raise Problem(422, "Response date in the future", "the insurer's response date cannot be after today")
    try:
        approved = validate_response(
            requested_cents=pl.requested_cents,
            response_status=str(body.get("response_status")),
            approved_cents=approved_in,
            denial_reason=denial,
            override_reason=override,
        )
    except ResponseError as exc:
        raise Problem(422, "Response refused", str(exc)) from exc
    doc_id = inputs.a_uuid(body, "response_document_id", required=False)
    if doc_id:
        doc = get_or_404(db, Document, doc_id)
        if doc.purpose != "response" or doc.packet_id not in packet_chain(db, packet):
            raise Problem(422, "Not a response document for this packet")
    before = {"response_status": pl.response_status, "approved_cents": pl.approved_cents}
    pl.response_status = str(body["response_status"])
    pl.approved_cents = approved
    pl.denial_reason = denial
    pl.override_reason = override
    pl.response_date = response_date
    pl.response_document_id = doc_id
    pl.response_recorded_by = ctx.user_id
    pl.response_recorded_at = now
    pl.row_version += 1
    db.flush()
    ctx.audit(db, "response.recorded", "packet_line", pl.id, before, {"response_status": pl.response_status, "approved_cents": approved})
    return to_dict(pl)


def _packet_totals(db: Session, packet_id: uuid.UUID) -> tuple[int, int]:
    approved = db.execute(
        select(func.coalesce(func.sum(PacketLine.approved_cents), 0)).where(
            PacketLine.packet_id == packet_id, PacketLine.response_status.notin_(("withdrawn", "preapproved"))
        )
    ).scalar()
    paid = db.execute(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.packet_id == packet_id, Payment.kind.in_(tuple(SUPPLEMENT_PAYMENT_KINDS))
        )
    ).scalar()
    return int(approved or 0), int(paid or 0)


def record_payment(ctx: Ctx, db: Session, ro_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    ro = lock_or_404(db, RepairOrder, ro_id)
    ctx.require(Action.RECORD_PAYMENT, "repair_order", ro.id)
    kind = body.get("kind")
    if kind not in PAYMENT_KINDS:
        raise Problem(422, "Invalid payment kind")
    packet_id = inputs.a_uuid(body, "packet_id", required=False)
    approved_total = paid_total = 0
    if packet_id is not None:
        packet = get_or_404(db, Packet, packet_id)
        if packet.ro_id != ro.id:
            raise Problem(404, "Not found")
        if packet.status == "superseded":
            raise Problem(409, "Superseded packet", "name the packet that superseded this one")
        approved_total, paid_total = _packet_totals(db, packet.id)
    remittance_id = inputs.a_uuid(body, "remittance_document_id", required=False)
    if remittance_id is not None:
        doc = get_or_404(db, Document, remittance_id)
        if doc.purpose != "remittance" or doc.ro_id != ro.id:
            raise Problem(422, "Not a remittance document for this RO")
    amount = inputs.cents(body, "amount_cents")
    assert amount is not None
    over_reason = inputs.text_field(body, "over_approved_reason")
    payer = body.get("payer", "insurer")
    if payer not in ("insurer", "customer", "other"):
        raise Problem(422, "Invalid payer")
    try:
        validate_supplement_payment(
            kind=str(kind),
            packet_id=str(packet_id) if packet_id else None,
            amount_cents=amount,
            reverses_payment_id=None,
            packet_insurer_approved_cents=approved_total,
            packet_supplement_paid_cents=paid_total,
            over_approved_reason=over_reason,
        )
    except PaymentError as exc:
        raise Problem(422, "Payment refused", str(exc)) from exc
    paid_on = inputs.a_date(body, "paid_on")
    assert paid_on is not None
    if paid_on > tenant_now_and_today(db)[1]:
        raise Problem(422, "Payment date in the future")
    reference = inputs.text_field(body, "reference")
    duplicate = db.execute(
        select(Payment.id).where(
            Payment.ro_id == ro.id,
            Payment.paid_on == paid_on,
            Payment.amount_cents == amount,
            Payment.reference.is_not_distinct_from(reference),
        )
    ).first()
    if duplicate is not None and body.get("confirm_duplicate") is not True:
        raise Problem(409, "Possible duplicate", "a payment with the same date, amount and reference exists; confirm to record it")
    payment = Payment(
        tenant_id=ctx.tenant_id,
        ro_id=ro.id,
        packet_id=packet_id,
        kind=kind,
        remittance_document_id=remittance_id,
        over_approved_reason=over_reason,
        payer=payer,
        amount_cents=amount,
        paid_on=paid_on,
        reference=reference,
        recorded_by=ctx.user_id,
    )
    db.add(payment)
    db.flush()
    ctx.audit(db, "payment.recorded", "payment", payment.id, None, {"kind": kind, "evidenced": remittance_id is not None})
    db.refresh(payment)
    return to_dict(payment)


def reverse_payment(ctx: Ctx, db: Session, payment_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    original = lock_or_404(db, Payment, payment_id)
    ctx.require(Action.RECORD_PAYMENT, "payment", original.id)
    if original.reverses_payment_id is not None or original.amount_cents < 0:
        raise Problem(409, "A reversal cannot be reversed")
    if db.execute(select(Payment.id).where(Payment.reverses_payment_id == original.id)).first():
        raise Problem(409, "Already reversed")
    if not (inputs.text_field(body, "reason") or "").strip():
        raise Problem(422, "Reason required")
    amount = inputs.cents(body, "amount_cents", required=False) or original.amount_cents  # full or partial reversal
    if amount <= 0 or amount > original.amount_cents:
        raise Problem(422, "Reversal amount must be above 0 and at most the original amount")
    reversal = Payment(
        tenant_id=ctx.tenant_id,
        ro_id=original.ro_id,
        packet_id=original.packet_id,
        kind=original.kind,
        remittance_document_id=original.remittance_document_id,
        payer=original.payer,
        amount_cents=-amount,
        paid_on=inputs.a_date(body, "paid_on", required=False) or original.paid_on,
        reference=original.reference,
        reverses_payment_id=original.id,
        recorded_by=ctx.user_id,
    )
    db.add(reversal)
    db.flush()
    ctx.audit(db, "payment.reversed", "payment", original.id, None, {"reversal_id": str(reversal.id)})
    db.refresh(reversal)
    return to_dict(reversal)


def ro_ledger(db: Session, ro_id: uuid.UUID) -> dict[str, Any]:
    ro = get_or_404(db, RepairOrder, ro_id)
    packets = list(db.execute(select(Packet).where(Packet.ro_id == ro.id)).scalars())
    lines = list(db.execute(select(PacketLine).where(PacketLine.packet_id.in_([p.id for p in packets]))).scalars()) if packets else []
    payments = list(db.execute(select(Payment).where(Payment.ro_id == ro.id)).scalars())
    ledger = compute_ro_ledger(
        [LedgerPacket(str(p.id), p.status) for p in packets],
        [LedgerPacketLine(str(pl.packet_id), pl.requested_cents, pl.response_status, pl.approved_cents, pl.origin) for pl in lines],
        [
            LedgerPayment(
                str(p.id),
                str(p.packet_id) if p.packet_id else None,
                p.kind,
                p.amount_cents,
                p.remittance_document_id is not None,
                str(p.reverses_payment_id) if p.reverses_payment_id else None,
            )
            for p in payments
        ],
    )
    return {
        "ro_id": str(ro.id),
        "requested_cents": ledger.requested_cents,
        "insurer_approved_cents": ledger.insurer_approved_cents,
        "collected_evidenced_cents": ledger.collected_evidenced_cents,
        "recorded_not_evidenced_cents": ledger.recorded_not_evidenced_cents,
        "withdrawn_cents": ledger.withdrawn_cents,
        "live_packet_ids": list(ledger.live_packet_ids),
        "labels": {
            "requested_cents": "Requested (excluding sales tax)",
            "insurer_approved_cents": "Insurer approved",
            "collected_evidenced_cents": "Collected (evidenced)",
            "recorded_not_evidenced_cents": "Recorded, not evidenced",
        },
    }
