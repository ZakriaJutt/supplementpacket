"""Packet review, freeze with fingerprint, supersede, mark sent, takedown (MH-06, MH-07, MH-11).

There is deliberately no function here, or anywhere, that transmits to an insurer
(AD-05). The Estimator downloads the packet and sends it personally.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem, StaleApprovals
from sp_api.services import inputs
from sp_api.services.common import get_or_404, lock_or_404, tenant_now_and_today, to_dict
from sp_api.services.documents import current_run, enqueue_job
from sp_api.services.lines import line_snapshots
from sp_core.approval import LineSnapshot, changed_components, freeze_blockers, review_components, review_fingerprint
from sp_core.email_draft import build_email_draft
from sp_core.evidence import FREE_TEXT_NOTICE
from sp_core.permissions import Action
from sp_core.reconcile import parse_feeds_packet
from sp_db.models import (
    DiffRun,
    Insurer,
    LineEvidence,
    Membership,
    Packet,
    PacketLine,
    Photo,
    ReferenceCitation,
    RepairOrder,
    SupplementLine,
    User,
)

__all__ = ["freeze_packet", "mark_sent", "packet_review", "packet_view", "takedown", "unmark_sent"]

SENT_CHANNELS = ("email", "insurer_portal", "estimating_system", "in_person", "other")
UNMARK_WINDOW = timedelta(hours=24)
REDACTED = "[redacted]"


def _recipient(db: Session, ro: RepairOrder) -> dict[str, str | None]:
    insurer = db.get(Insurer, ro.insurer_id) if ro.insurer_id else None
    return {
        "insurer": insurer.name if insurer else None,
        "claim_number": ro.claim_number,
        "adjuster_name": ro.adjuster_name,
        "adjuster_email": ro.adjuster_email,
    }


def _live_packet(db: Session, ro_id: uuid.UUID, *, lock: bool) -> Packet | None:
    query = select(Packet).where(Packet.ro_id == ro_id, Packet.status.in_(("frozen", "sent")))
    if lock:
        query = query.with_for_update()
    return db.execute(query).scalar_one_or_none()


def _withdrawn(db: Session, live: Packet | None, approved_ids: set[str]) -> list[PacketLine]:
    """Lines of the live packet that the next version no longer requests (B1-005)."""
    if live is None:
        return []
    rows = db.execute(select(PacketLine).where(PacketLine.packet_id == live.id).order_by(PacketLine.line_no)).scalars()
    return [pl for pl in rows if str(pl.supplement_line_id) not in approved_ids]


def _review_state(db: Session, ro: RepairOrder, snaps: list[LineSnapshot], live: Packet | None) -> dict[str, Any]:
    approved = [s for s in snaps if s.status == "approved"]
    total = sum(s.requested_cents for s in approved)
    withdrawn = _withdrawn(db, live, {s.line_id for s in approved})
    draft = build_email_draft(
        ro_number=ro.ro_number,
        claim_number=ro.claim_number,
        line_count=len(approved),
        requested_total_cents=total,
        free_paragraph=ro.email_free_paragraph,
        withdrawn_count=len(withdrawn),
    )
    recipient = _recipient(db, ro)
    components = review_components(snaps, email_draft=draft.text, recipient=recipient)
    return {
        "approved": approved,
        "withdrawn": withdrawn,
        "requested_total_cents": total,
        "email_draft": draft,
        "recipient": recipient,
        "components": components,
        "fingerprint": review_fingerprint(components),
    }


def packet_review(ctx: Ctx, db: Session, ro_id: uuid.UUID) -> dict[str, Any]:
    """What the review screen displays, with the fingerprint the freeze must carry."""
    ro = get_or_404(db, RepairOrder, ro_id)
    pairs = line_snapshots(db, ro.id, lock=False)
    snaps = [s for _, s in pairs]
    state = _review_state(db, ro, snaps, _live_packet(db, ro.id, lock=False))
    blockers = freeze_blockers(snaps)
    return {
        "ro_id": str(ro.id),
        "lines": [
            {
                "id": s.line_id,
                "row_version": s.row_version,
                "status": s.status,
                "match_state": s.match_state,
                "origin": s.origin,
                "category": s.category,
                "description": s.description,
                "requested_cents": s.requested_cents,
                "explanation": s.explanation,
                "evidence": [{"id": e.evidence_id, "kind": e.kind} for e in s.evidence],
                "evidence_label": None if s.evidence else "No attached evidence",
            }
            for s in snaps
        ],
        "requested_total_cents": state["requested_total_cents"],
        "withdrawn_lines": [
            {"supplement_line_id": str(pl.supplement_line_id), "description": pl.description, "requested_cents": pl.requested_cents}
            for pl in state["withdrawn"]
        ],
        "free_text_notice": FREE_TEXT_NOTICE,
        "email_draft": state["email_draft"].text,
        "email_draft_problems": list(state["email_draft"].problems),
        "recipient": state["recipient"],
        "review_components": state["components"],
        "review_fingerprint": state["fingerprint"],
        "blockers": [{"item": p.item, "reason": p.reason} for p in blockers],
    }


def _parse_problems(db: Session, lines: list[SupplementLine]) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    run_ids = {line.diff_run_id for line in lines if line.diff_run_id and line.status == "approved"}
    for run_id in sorted(run_ids, key=str):
        diff_run = db.get(DiffRun, run_id)
        if diff_run is None:
            continue
        for doc_id in (diff_run.insurer_document_id, diff_run.shop_document_id):
            run = current_run(db, doc_id)
            if run is None or not parse_feeds_packet(run.status, run.confirm_reason, run.confirmed_by):
                problems.append({"item": f"document:{doc_id}", "reason": "parse not reconciled"})
    return problems


def _evidence_snapshot(db: Session, line_id: uuid.UUID) -> dict[str, Any]:
    rows = db.execute(
        select(LineEvidence, Photo, ReferenceCitation)
        .outerjoin(Photo, Photo.id == LineEvidence.photo_id)
        .outerjoin(ReferenceCitation, ReferenceCitation.id == LineEvidence.reference_id)
        .where(LineEvidence.supplement_line_id == line_id)
        .order_by(LineEvidence.id)
    ).all()
    photos = [
        {"photo_id": str(p.id), "sha256": bytes(p.sha256).hex(), "storage_key": p.storage_key, "taken_by_shop": p.taken_by_shop}
        for _, p, _ in rows
        if p is not None
    ]
    refs = [
        {k: v for k, v in to_dict(r).items() if k in ("id", "material_type", "publisher", "title", "identifier", "url", "accessed_on")}
        for _, _, r in rows
        if r is not None
    ]
    return {"photos": photos, "references": refs}


def freeze_packet(ctx: Ctx, db: Session, ro_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Freeze under a lock. Refuses anything that differs from what the review displayed."""
    ro = lock_or_404(db, RepairOrder, ro_id)
    ctx.require(Action.FREEZE_PACKET, "repair_order", ro.id)
    shown_fp = str(body.get("review_fingerprint") or "")
    shown_components = body.get("review_components") or {}
    if not shown_fp or not isinstance(shown_components, dict):
        raise Problem(422, "Review fingerprint required", "freeze from the review screen")
    if review_fingerprint(shown_components) != shown_fp:
        raise Problem(422, "Review fingerprint does not match its components")

    pairs = line_snapshots(db, ro.id, lock=True)  # SELECT ... FOR UPDATE on every line of the RO
    lines = [line for line, _ in pairs]
    snaps = [s for _, s in pairs]

    problems = [{"item": p.item, "reason": p.reason} for p in freeze_blockers(snaps)]
    problems += _parse_problems(db, lines)
    stale = _stale_approvals(db, [line for line in lines if line.status == "approved"])
    if stale:
        raise StaleApprovals(stale)
    live = _live_packet(db, ro.id, lock=True)
    state = _review_state(db, ro, snaps, live)
    changes = changed_components(shown_components, state["components"])
    if problems or changes:
        raise Problem(
            409,
            "Packet cannot be frozen",
            "the review changed or some lines are not approved; reload the review",
            problems=problems,
            changed=changes,
        )
    draft = state["email_draft"]
    if not draft.ok:
        raise Problem(422, "Email draft refused", "; ".join(draft.problems), problems=list(draft.problems))

    approved = [line for line in lines if line.status == "approved"]
    previous_lines: dict[uuid.UUID, PacketLine] = {}
    if live is not None:
        previous_lines = {
            pl.supplement_line_id: pl for pl in db.execute(select(PacketLine).where(PacketLine.packet_id == live.id)).scalars()
        }
        same = {
            (pl.supplement_line_id, bytes(pl.approved_fingerprint)) for pl in previous_lines.values() if pl.request_state == "requested"
        } == {(line.id, bytes(line.approved_fingerprint or b"")) for line in approved}
        if same and live.email_draft == draft.text:
            raise Problem(409, "Nothing changed", "no approved line changed since the last packet")

    version = (db.execute(select(func.max(Packet.version)).where(Packet.ro_id == ro.id)).scalar() or 0) + 1
    if live is not None:
        live.status = "superseded"
        db.flush()
        ctx.audit(db, "packet.superseded", "packet", live.id, {"status": "frozen_or_sent"}, {"status": "superseded"})
    packet = Packet(
        tenant_id=ctx.tenant_id,
        ro_id=ro.id,
        version=version,
        review_fingerprint=bytes.fromhex(state["fingerprint"]),
        supersedes_packet_id=live.id if live else None,
        requested_total_cents=state["requested_total_cents"],
        line_count=len(approved),
        email_draft=draft.text,
        frozen_by=ctx.user_id,
    )
    db.add(packet)
    db.flush()
    carried = 0
    for number, line in enumerate(approved, start=1):
        prior = previous_lines.get(line.id)
        unchanged = (
            prior is not None
            and prior.request_state == "requested"
            and bytes(prior.approved_fingerprint) == bytes(line.approved_fingerprint or b"")
        )
        pl = PacketLine(
            tenant_id=ctx.tenant_id,
            packet_id=packet.id,
            supplement_line_id=line.id,
            line_no=number,
            origin=line.origin,
            category=line.category,
            description=line.description,
            requested_cents=line.requested_cents,
            evidence_snapshot=_evidence_snapshot(db, line.id),
            approved_by=line.approved_by,
            approved_at=line.approved_at,
            approved_fingerprint=line.approved_fingerprint,
        )
        if unchanged and prior is not None:
            # Carry the insurer's response forward; the old packet stops counting (MH-08, UT-17).
            pl.carried_from_packet_line_id = prior.id
            pl.response_status = prior.response_status
            pl.approved_cents = prior.approved_cents
            pl.denial_reason = prior.denial_reason
            pl.response_date = prior.response_date
            pl.response_document_id = prior.response_document_id
            pl.override_reason = prior.override_reason
            pl.response_recorded_by = prior.response_recorded_by
            carried += 1
        db.add(pl)
    withdrawn_rows = state["withdrawn"]
    for number, prior in enumerate(withdrawn_rows, start=len(approved) + 1):
        # Withdrawn through this superseding version: kept with its amount, outside the request (B1-005).
        db.add(
            PacketLine(
                tenant_id=ctx.tenant_id,
                packet_id=packet.id,
                supplement_line_id=prior.supplement_line_id,
                line_no=number,
                origin=prior.origin,
                category=prior.category,
                description=prior.description,
                requested_cents=prior.requested_cents,
                evidence_snapshot=prior.evidence_snapshot,
                approved_by=prior.approved_by,
                approved_at=prior.approved_at,
                approved_fingerprint=prior.approved_fingerprint,
                carried_from_packet_line_id=prior.id,
                request_state="withdrawn",
                response_status="withdrawn",
                approved_cents=0,
                response_recorded_by=ctx.user_id,
                response_recorded_at=datetime.now(UTC),
            )
        )
    db.flush()
    if live is not None:
        # Payments follow the successor packet; the trigger checks and audits each one.
        db.execute(text("UPDATE payments SET packet_id = :new WHERE packet_id = :old"), {"new": packet.id, "old": live.id})
    ctx.audit(
        db,
        "packet.frozen",
        "packet",
        packet.id,
        None,
        {
            "version": version,
            "line_count": len(approved),
            "supersedes": str(live.id) if live else None,
            "carried": carried,
            "withdrawn": len(withdrawn_rows),
        },
    )
    job = enqueue_job(ctx, db, "render_packet", packet.id, f"render:{packet.id}")
    db.refresh(packet)
    return {**packet_view(db, packet), "render_job_id": str(job.id)}


def _stale_approvals(db: Session, approved: list[SupplementLine]) -> list[uuid.UUID]:
    """Approved lines whose approver no longer holds Owner or Estimator, or is not active (B1-006)."""
    approvers = {line.approved_by for line in approved if line.approved_by}
    if not approvers:
        return []
    permitted = set(
        db.execute(
            select(Membership.user_id)
            .join(User, User.id == Membership.user_id)
            .where(Membership.user_id.in_(approvers), Membership.role.in_(("owner", "estimator")), User.status == "active")
        ).scalars()
    )
    return sorted((line.id for line in approved if line.approved_by not in permitted), key=str)


def packet_view(db: Session, packet: Packet) -> dict[str, Any]:
    lines = db.execute(select(PacketLine).where(PacketLine.packet_id == packet.id).order_by(PacketLine.line_no)).scalars()
    return {
        "packet": to_dict(packet, exclude=("pdf_storage_key",)),
        "lines": [to_dict(pl) for pl in lines],
    }


def mark_sent(ctx: Ctx, db: Session, packet_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    packet = lock_or_404(db, Packet, packet_id)
    ctx.require(Action.MARK_SENT, "packet", packet.id)
    if packet.status != "frozen":
        raise Problem(409, "Not sendable", f"packet is {packet.status}")
    channel = body.get("sent_channel")
    if channel not in SENT_CHANNELS:
        raise Problem(422, "Channel required")
    if body.get("confirm") is not True:
        raise Problem(422, "Confirmation required")
    shown_total = inputs.cents(body, "requested_total_cents")
    if shown_total != packet.requested_total_cents or body.get("line_count") != packet.line_count:
        raise Problem(409, "Confirm the packet total and line count shown", "they do not match this packet")
    sent_on = inputs.a_date(body, "sent_on")
    assert sent_on is not None
    now, today = tenant_now_and_today(db)
    if sent_on > today:
        raise Problem(422, "Sent date in the future", "a sent date in the future is refused")
    if sent_on < packet.frozen_at.astimezone(now.tzinfo).date():
        raise Problem(422, "Sent date before the freeze", "a packet cannot have been sent before it was frozen")
    packet.status = "sent"
    packet.sent_on = sent_on
    packet.sent_channel = channel
    packet.sent_marked_by = ctx.user_id
    packet.sent_marked_at = datetime.now(UTC)
    packet.row_version += 1
    db.flush()
    ctx.audit(db, "packet.marked_sent", "packet", packet.id, {"status": "frozen"}, {"status": "sent", "channel": channel})
    return packet_view(db, packet)


def unmark_sent(ctx: Ctx, db: Session, packet_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    packet = lock_or_404(db, Packet, packet_id)
    ctx.require(Action.UNMARK_SENT, "packet", packet.id)
    reason = (inputs.text_field(body, "reason") or "").strip()
    if packet.status != "sent" or packet.sent_marked_at is None:
        raise Problem(409, "Not marked sent")
    if datetime.now(UTC) - packet.sent_marked_at > UNMARK_WINDOW:
        raise Problem(409, "Too late to undo", "mark sent can be undone for 24 hours")
    if not reason:
        raise Problem(422, "Reason required")
    packet.status = "frozen"
    packet.sent_on = None
    packet.sent_channel = None
    packet.sent_marked_by = None
    packet.sent_marked_at = None
    packet.correction_note = reason
    packet.row_version += 1
    db.flush()
    ctx.audit(db, "packet.unmarked_sent", "packet", packet.id, {"status": "sent"}, {"status": "frozen"})
    return packet_view(db, packet)


def takedown(ctx: Ctx, db: Session, packet_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Licensed-content takedown: the only change ever made to a frozen packet (IT-19)."""
    packet = lock_or_404(db, Packet, packet_id)
    ctx.require(Action.TAKEDOWN, "packet", packet.id)
    reason = (inputs.text_field(body, "reason") or "").strip()
    if not reason:
        raise Problem(422, "Reason required")
    if packet.purged_at is not None:
        raise Problem(409, "Already taken down")
    lines = list(db.execute(select(PacketLine).where(PacketLine.packet_id == packet.id).with_for_update()).scalars())
    keys: list[str] = [packet.pdf_storage_key] if packet.pdf_storage_key else []
    photo_ids: set[uuid.UUID] = set()
    for pl in lines:
        for photo in (pl.evidence_snapshot or {}).get("photos", []):
            photo_ids.add(uuid.UUID(photo["photo_id"]))
            if photo.get("storage_key"):
                keys.append(photo["storage_key"])
    packet.purged_at = datetime.now(UTC)
    packet.purge_reason = reason
    packet.purged_by = ctx.user_id
    packet.email_draft = REDACTED
    packet.pdf_storage_key = None
    packet.row_version += 1
    db.flush()
    for pl in lines:
        pl.description = REDACTED
        pl.evidence_snapshot = {"redacted": True}
    for pid in sorted(photo_ids, key=str):
        photo = db.get(Photo, pid)
        if photo is not None and photo.storage_key is not None:
            photo.storage_key = None
            photo.purged_at = packet.purged_at
    db.flush()
    ctx.audit(db, "packet.takedown", "packet", packet.id, None, {"reason_given": True, "objects": len(keys)})
    job = enqueue_job(ctx, db, "takedown_purge", packet.id, f"takedown:{packet.id}", result={"keys": sorted(set(keys))})
    return {**packet_view(db, packet), "purge_job_id": str(job.id), "notice": "A copy already sent to an insurer cannot be recalled."}
