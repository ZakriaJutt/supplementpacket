"""Diff runs, supplement lines, per-line approval and evidence (MH-03..MH-06; T-4.1.1, T-4.2.1, T-4.2.2).

The approval reset rule lives in the database triggers (one function, sp_reset_line);
this module never leaves a changed line approved because it cannot: the triggers and
the check constraint refuse it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem
from sp_api.services.common import check_version, get_or_404, lock_or_404, to_dict
from sp_api.services.documents import current_run
from sp_core.approval import (
    EvidenceItem,
    LineSnapshot,
    approval_blockers,
    line_fingerprint,
    photo_content_hash,
    reference_content_hash,
)
from sp_core.diff import CATEGORIES, ENGINE_VERSION, diff_estimates
from sp_core.diff import EstimateLine as DiffInput
from sp_core.evidence import EvidenceError, validate_photo_attestation, validate_reference
from sp_core.permissions import Action
from sp_core.reconcile import parse_feeds_packet
from sp_db.models import (
    ChecklistItem,
    DiffRun,
    Document,
    EstimateLine,
    LineEvidence,
    Photo,
    ReferenceCitation,
    RepairOrder,
    SupplementLine,
)
from sp_files import build_object_key, sha256_hex, sniff_type

__all__ = [
    "add_photos",
    "add_reference",
    "approve_line",
    "create_line",
    "delete_evidence",
    "exclude_line",
    "latest_estimate",
    "line_snapshots",
    "patch_line",
    "patch_photo",
    "patch_reference",
    "run_diff",
]

LINE_EDITABLE = ("category", "description", "requested_cents", "hours_delta", "explanation", "match_state")


def latest_estimate(db: Session, ro_id: uuid.UUID, purpose: str) -> Document | None:
    return (
        db.execute(select(Document).where(Document.ro_id == ro_id, Document.purpose == purpose).order_by(Document.version.desc()))
        .scalars()
        .first()
    )


def _diff_inputs(db: Session, run_id: uuid.UUID) -> list[DiffInput]:
    rows = db.execute(select(EstimateLine).where(EstimateLine.parse_run_id == run_id)).scalars().all()
    return [
        DiffInput(
            line_id=str(r.id),
            line_no=r.line_no,
            operation=r.operation,
            description=r.description,
            line_total_cents=r.line_total_cents,
            part_number=r.part_number,
            part_type=r.part_type,
            part_price_cents=r.part_price_cents,
            labor_hours=r.labor_hours,
            labor_rate_cents=r.labor_rate_cents,
        )
        for r in rows
    ]


def run_diff(ctx: Ctx, db: Session, ro_id: uuid.UUID) -> dict[str, Any]:
    ro = lock_or_404(db, RepairOrder, ro_id)
    ctx.require(Action.EDIT_LINE, "repair_order", ro.id)
    insurer_doc = latest_estimate(db, ro.id, "insurer_estimate")
    shop_doc = latest_estimate(db, ro.id, "shop_estimate")
    if insurer_doc is None or shop_doc is None:
        raise Problem(409, "Both estimates are needed", "upload the insurer estimate and the shop estimate")
    runs = {}
    for label, doc in (("insurer estimate", insurer_doc), ("shop estimate", shop_doc)):
        run = current_run(db, doc.id)
        if run is None or not parse_feeds_packet(run.status, run.confirm_reason, run.confirmed_by):
            raise Problem(409, "Parse not ready", f"correct or confirm the {label} lines and totals first")
        runs[label] = run
    diff_run = db.execute(
        select(DiffRun).where(
            DiffRun.insurer_document_id == insurer_doc.id,
            DiffRun.shop_document_id == shop_doc.id,
            DiffRun.engine_version == ENGINE_VERSION,
        )
    ).scalar_one_or_none()
    if diff_run is None:
        diff_run = DiffRun(
            tenant_id=ctx.tenant_id,
            ro_id=ro.id,
            insurer_document_id=insurer_doc.id,
            shop_document_id=shop_doc.id,
            engine_version=ENGINE_VERSION,
            created_by=ctx.user_id,
        )
        db.add(diff_run)
        db.flush()
    result = diff_estimates(_diff_inputs(db, runs["shop estimate"].id), _diff_inputs(db, runs["insurer estimate"].id))

    existing = {
        line.diff_key: line
        for line in db.execute(
            select(SupplementLine).where(SupplementLine.ro_id == ro.id, SupplementLine.origin == "diff").with_for_update()
        ).scalars()
        if line.diff_key
    }
    created = changed = orphaned = 0
    seen: set[str] = set()
    for out in result.lines:
        seen.add(out.key)
        values = {
            "diff_run_id": diff_run.id,
            "category": out.category,
            "match_state": out.match_state,
            "description": out.description,
            "requested_cents": out.requested_cents,
            "hours_delta": out.hours_delta,
            "shop_line_id": uuid.UUID(out.shop_line_id),
            "insurer_line_id": uuid.UUID(out.insurer_line_id) if out.insurer_line_id else None,
        }
        line = existing.get(out.key)
        if line is None:
            db.add(SupplementLine(tenant_id=ctx.tenant_id, ro_id=ro.id, origin="diff", diff_key=out.key, created_by=ctx.user_id, **values))
            created += 1
            continue
        if any(getattr(line, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(line, k, v)
            changed += 1  # the trigger returns it to draft and audits a reset
    for key, line in existing.items():
        if key not in seen and line.match_state != "needs_review":
            line.match_state = "needs_review"  # no longer produced: draft and needs review
            orphaned += 1
    db.flush()
    ctx.audit(
        db,
        "diff.run",
        "diff_run",
        diff_run.id,
        None,
        {"created": created, "changed": changed, "no_longer_produced": orphaned, "needs_review": result.needs_review_count},
    )
    return {
        "diff_run": to_dict(diff_run),
        "engine_version": result.engine_version,
        "lines_created": created,
        "lines_changed": changed,
        "lines_no_longer_produced": orphaned,
        "needs_review": result.needs_review_count,
        "differences_total_cents": result.differences_total_cents,
    }


def create_line(ctx: Ctx, db: Session, ro_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    ro = get_or_404(db, RepairOrder, ro_id)
    ctx.require(Action.EDIT_LINE, "repair_order", ro.id)
    origin = body.get("origin", "manual")
    if origin not in ("manual", "checklist"):
        raise Problem(422, "Invalid origin", "lines are added manually or from the checklist")
    category = body.get("category", "missing_operation")
    if category not in CATEGORIES:
        raise Problem(422, "Invalid category")
    checklist_item_id = None
    description = str(body.get("description") or "").strip()
    if origin == "checklist":
        if not body.get("checklist_item_id"):
            raise Problem(422, "Checklist item required")
        item = get_or_404(db, ChecklistItem, uuid.UUID(str(body["checklist_item_id"])))
        checklist_item_id = item.id
        description = description or item.operation_name
    if "requested_cents" not in body:
        raise Problem(422, "Amount required", "the Estimator types the amount")
    requested = int(body["requested_cents"])
    if requested < 0 or not description:
        raise Problem(422, "Invalid line")
    hours = body.get("hours_delta")
    line = SupplementLine(
        tenant_id=ctx.tenant_id,
        ro_id=ro.id,
        origin=origin,
        category=category,
        checklist_item_id=checklist_item_id,
        description=description,
        requested_cents=requested,
        hours_delta=Decimal(str(hours)) if hours is not None else None,
        explanation=body.get("explanation"),
        created_by=ctx.user_id,
    )
    db.add(line)
    db.flush()
    ctx.audit(db, "line.created", "supplement_line", line.id, None, {"origin": origin, "category": category})
    db.refresh(line)
    return to_dict(line)


def patch_line(ctx: Ctx, db: Session, line_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    line = lock_or_404(db, SupplementLine, line_id)
    ctx.require(Action.EDIT_LINE, "supplement_line", line.id)
    check_version(line, if_match)
    if "match_state" in body and body["match_state"] not in ("matched", "not_applicable"):
        raise Problem(422, "Invalid match state", "a line can be marked matched or not applicable")
    if "category" in body and body["category"] not in CATEGORIES:
        raise Problem(422, "Invalid category")
    before = {k: to_dict(line)[k] for k in LINE_EDITABLE if k in body}
    for key in LINE_EDITABLE:
        if key in body:
            value = body[key]
            if key == "hours_delta" and value is not None:
                value = Decimal(str(value))
            if key == "requested_cents":
                value = int(value)
            setattr(line, key, value)
    line.row_version += 1  # any edit returns the line to draft (trigger)
    db.flush()
    db.refresh(line)
    ctx.audit(db, "line.edited", "supplement_line", line.id, before, {k: to_dict(line)[k] for k in before})
    return to_dict(line)


def _evidence_items(db: Session, line_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[EvidenceItem]]:
    out: dict[uuid.UUID, list[EvidenceItem]] = {lid: [] for lid in line_ids}
    if not line_ids:
        return out
    rows = db.execute(
        select(LineEvidence, Photo, ReferenceCitation)
        .outerjoin(Photo, Photo.id == LineEvidence.photo_id)
        .outerjoin(ReferenceCitation, ReferenceCitation.id == LineEvidence.reference_id)
        .where(LineEvidence.supplement_line_id.in_(line_ids))
    ).all()
    for ev, photo, ref in rows:
        if photo is not None:
            content = photo_content_hash(
                sha256_hex=bytes(photo.sha256).hex(),
                taken_by_shop=photo.taken_by_shop,
                attested=photo.not_licensed_copy_attested,
                attestation_note=photo.attestation_note,
            )
            out[ev.supplement_line_id].append(EvidenceItem(str(ev.id), "photo", content))
        elif ref is not None:
            content = reference_content_hash(to_dict(ref))
            out[ev.supplement_line_id].append(EvidenceItem(str(ev.id), "reference", content))
    return out


def snapshot_of(line: SupplementLine, evidence: list[EvidenceItem]) -> LineSnapshot:
    return LineSnapshot(
        line_id=str(line.id),
        row_version=line.row_version,
        status=line.status,
        match_state=line.match_state,
        origin=line.origin,
        category=line.category,
        description=line.description,
        requested_cents=line.requested_cents,
        hours_delta=line.hours_delta,
        explanation=line.explanation,
        evidence=tuple(sorted(evidence, key=lambda e: e.evidence_id)),
        approved_row_version=line.approved_row_version,
        approved_fingerprint=bytes(line.approved_fingerprint).hex() if line.approved_fingerprint else None,
    )


def line_snapshots(db: Session, ro_id: uuid.UUID, *, lock: bool) -> list[tuple[SupplementLine, LineSnapshot]]:
    query = select(SupplementLine).where(SupplementLine.ro_id == ro_id).order_by(SupplementLine.created_at, SupplementLine.id)
    if lock:
        query = query.with_for_update()
    lines = list(db.execute(query).scalars())
    evidence = _evidence_items(db, [line.id for line in lines])
    return [(line, snapshot_of(line, evidence[line.id])) for line in lines]


def approve_line(ctx: Ctx, db: Session, line_id: uuid.UUID, if_match: int | None) -> dict[str, Any]:
    """One line at a time, by an Owner or Estimator, against the version they saw."""
    line = lock_or_404(db, SupplementLine, line_id)
    ctx.require(Action.APPROVE_LINE, "supplement_line", line.id)
    check_version(line, if_match)
    if line.status == "approved":
        return to_dict(line)
    snap = snapshot_of(line, _evidence_items(db, [line.id])[line.id])
    blockers = approval_blockers(snap)
    if blockers:
        raise Problem(422, "Cannot approve", "; ".join(blockers), problems=blockers)
    line.status = "approved"
    line.approved_by = ctx.user_id
    line.approved_at = datetime.now(UTC)
    line.approved_row_version = line.row_version
    line.approved_fingerprint = bytes.fromhex(line_fingerprint(snap))
    db.flush()
    ctx.audit(
        db, "line.approved", "supplement_line", line.id, {"status": snap.status}, {"status": "approved", "row_version": line.row_version}
    )
    return to_dict(line)


def exclude_line(ctx: Ctx, db: Session, line_id: uuid.UUID, if_match: int | None) -> dict[str, Any]:
    line = lock_or_404(db, SupplementLine, line_id)
    ctx.require(Action.EXCLUDE_LINE, "supplement_line", line.id)
    check_version(line, if_match)
    before = line.status
    line.status = "excluded"
    line.approved_by = None
    line.approved_at = None
    line.approved_row_version = None
    line.approved_fingerprint = None
    db.flush()
    ctx.audit(db, "line.excluded", "supplement_line", line.id, {"status": before}, {"status": "excluded"})
    return to_dict(line)


def add_photos(
    ctx: Ctx,
    db: Session,
    line_id: uuid.UUID,
    files: list[tuple[str, bytes]],
    *,
    attested: bool | None,
    taken_by_shop: bool | None,
    attestation_note: str | None,
) -> dict[str, Any]:
    """Bulk photo upload with per-file results; retry never attaches a file twice (IT-05)."""
    line = lock_or_404(db, SupplementLine, line_id)
    ctx.require(Action.EDIT_LINE, "supplement_line", line.id)
    try:
        validate_photo_attestation(attested=attested, taken_by_shop=taken_by_shop, attestation_note=attestation_note)
    except EvidenceError as exc:
        raise Problem(422, "Attestation required", str(exc)) from exc
    results: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for index, (_client_name, data) in enumerate(files):  # the client file name is never stored or keyed
        outcome: dict[str, Any] = {"index": index}
        content_type = sniff_type(data) if data else None
        if content_type not in ("image/jpeg", "image/png", "image/heic"):
            outcome.update(status="rejected", reason="not a JPEG, PNG or HEIC image")
            results.append(outcome)
            continue
        if len(data) > ctx.state.settings.max_photo_bytes:
            outcome.update(status="rejected", reason="larger than 15 MB")
            results.append(outcome)
            continue
        digest = sha256_hex(data)
        photo = db.execute(select(Photo).where(Photo.ro_id == line.ro_id, Photo.sha256 == bytes.fromhex(digest))).scalar_one_or_none()
        if photo is None:
            photo_id = uuid.uuid4()
            key = build_object_key(
                tenant_id=ctx.tenant_id, ro_id=line.ro_id, purpose="photo", document_id=photo_id, sha256=digest, content_type=content_type
            )
            ctx.state.store.put(key, data)
            photo = Photo(
                id=photo_id,
                tenant_id=ctx.tenant_id,
                ro_id=line.ro_id,
                storage_key=key,
                sha256=bytes.fromhex(digest),
                content_type=content_type,
                taken_by_shop=bool(taken_by_shop),
                not_licensed_copy_attested=True,
                attested_by=ctx.user_id,
                attested_at=now,
                attestation_note=attestation_note,
                uploaded_by=ctx.user_id,
            )
            db.add(photo)
            db.flush()
        linked = db.execute(
            select(LineEvidence.id).where(LineEvidence.supplement_line_id == line.id, LineEvidence.photo_id == photo.id)
        ).scalar_one_or_none()
        if linked is not None:
            outcome.update(status="already_attached", photo_id=str(photo.id), evidence_id=str(linked))
        else:
            ev = LineEvidence(
                tenant_id=ctx.tenant_id, ro_id=line.ro_id, supplement_line_id=line.id, photo_id=photo.id, created_by=ctx.user_id
            )
            db.add(ev)
            db.flush()  # trigger: evidence added, approval reset
            ctx.audit(db, "evidence.photo_attached", "supplement_line", line.id, None, {"photo_id": str(photo.id)})
            outcome.update(status="attached", photo_id=str(photo.id), evidence_id=str(ev.id))
        results.append(outcome)
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("attached", "already_attached", "rejected")}
    return {"results": results, **counts}


def _reference_fields(body: dict[str, Any]) -> dict[str, Any]:
    url = body.get("url") or None
    note = body.get("note") or None
    try:
        validate_reference(
            material_type=str(body.get("material_type", "")),
            publisher=str(body.get("publisher", "")),
            title=str(body.get("title", "")),
            url=url,
            note=note,
        )
    except EvidenceError as exc:
        raise Problem(422, "Reference refused", str(exc)) from exc
    accessed = body.get("accessed_on")
    if not accessed:
        raise Problem(422, "Date accessed required")
    return {
        "material_type": body["material_type"],
        "publisher": str(body["publisher"]).strip(),
        "title": str(body["title"]).strip(),
        "identifier": body.get("identifier") or None,
        "url": url,
        "accessed_on": date.fromisoformat(str(accessed)),
        "note": note,
    }


def add_reference(ctx: Ctx, db: Session, line_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    line = lock_or_404(db, SupplementLine, line_id)
    ctx.require(Action.EDIT_LINE, "supplement_line", line.id)
    if body.get("reference_id"):
        ref = get_or_404(db, ReferenceCitation, uuid.UUID(str(body["reference_id"])))
    else:
        ref = ReferenceCitation(tenant_id=ctx.tenant_id, created_by=ctx.user_id, **_reference_fields(body))
        db.add(ref)
        db.flush()
    ev = LineEvidence(tenant_id=ctx.tenant_id, ro_id=line.ro_id, supplement_line_id=line.id, reference_id=ref.id, created_by=ctx.user_id)
    db.add(ev)
    db.flush()
    ctx.audit(db, "evidence.reference_attached", "supplement_line", line.id, None, {"reference_id": str(ref.id)})
    return {"reference": to_dict(ref), "evidence_id": str(ev.id)}


def patch_reference(ctx: Ctx, db: Session, ref_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    ref = lock_or_404(db, ReferenceCitation, ref_id)
    ctx.require(Action.EDIT_LINE, "reference_citation", ref.id)
    check_version(ref, if_match)
    merged = {**to_dict(ref), **body}
    fields = _reference_fields(merged)
    before = to_dict(ref)
    for key, value in fields.items():
        setattr(ref, key, value)
    ref.row_version += 1
    db.flush()  # trigger resets every line citing this reference
    ctx.audit(db, "reference.edited", "reference_citation", ref.id, {k: before[k] for k in fields}, {k: to_dict(ref)[k] for k in fields})
    return to_dict(ref)


def patch_photo(ctx: Ctx, db: Session, photo_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    """Change the attestation answers of a photo; every line using it returns to draft."""
    photo = lock_or_404(db, Photo, photo_id)
    ctx.require(Action.EDIT_LINE, "photo", photo.id)
    check_version(photo, if_match)
    taken = body.get("taken_by_shop", photo.taken_by_shop)
    note = body.get("attestation_note", photo.attestation_note)
    try:
        validate_photo_attestation(attested=body.get("attested"), taken_by_shop=taken, attestation_note=note)
    except EvidenceError as exc:
        raise Problem(422, "Attestation required", str(exc)) from exc
    before = {"taken_by_shop": photo.taken_by_shop, "attestation_note": photo.attestation_note}
    photo.taken_by_shop = bool(taken)
    photo.attestation_note = note
    photo.attested_by = ctx.user_id
    photo.attested_at = datetime.now(UTC)
    photo.row_version += 1
    db.flush()
    ctx.audit(db, "photo.attestation_changed", "photo", photo.id, before, {"taken_by_shop": photo.taken_by_shop})
    return to_dict(photo, exclude=("storage_key",))


def delete_evidence(ctx: Ctx, db: Session, evidence_id: uuid.UUID) -> dict[str, Any]:
    ev = get_or_404(db, LineEvidence, evidence_id)
    ctx.require(Action.EDIT_LINE, "supplement_line", ev.supplement_line_id)
    line_id = ev.supplement_line_id
    db.delete(ev)
    db.flush()  # trigger: evidence removed, approval reset
    ctx.audit(db, "evidence.removed", "supplement_line", line_id, {"evidence_id": str(evidence_id)}, None)
    count = db.execute(select(func.count()).select_from(LineEvidence).where(LineEvidence.supplement_line_id == line_id)).scalar()
    return {"removed": str(evidence_id), "line_id": str(line_id), "remaining_evidence": count}
