"""ROs, uploads, parse review, manual entry and jobs (MH-01, MH-02, MH-12; T-3.1.1, T-3.1.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem
from sp_api.services.common import check_version, get_or_404, lock_or_404, to_dict
from sp_core.jobs import decide_transition
from sp_core.permissions import Action
from sp_core.reconcile import reconcile
from sp_db.models import Document, EstimateLine, Job, Location, ParseRun, RepairOrder
from sp_files import build_object_key, sha256_hex, sniff_type

__all__ = [
    "ESTIMATE_PURPOSES",
    "confirm_reconcile",
    "create_ro",
    "current_run",
    "enqueue_job",
    "manual_entry",
    "patch_estimate_line",
    "patch_ro",
    "retry_job",
    "store_document",
]

ESTIMATE_PURPOSES = ("insurer_estimate", "shop_estimate")
RO_EDITABLE = (
    "ro_number",
    "insurer_id",
    "claim_number",
    "adjuster_name",
    "adjuster_email",
    "vin",
    "vehicle_desc",
    "email_free_paragraph",
    "status",
)
LINE_EDITABLE = (
    "operation",
    "description",
    "part_number",
    "part_type",
    "part_price_cents",
    "labor_hours",
    "labor_type",
    "labor_rate_cents",
    "line_total_cents",
)


def create_ro(ctx: Ctx, db: Session, body: dict[str, Any]) -> dict[str, Any]:
    ctx.require(Action.EDIT_RO, "repair_order", uuid.UUID(int=0))
    location_id = uuid.UUID(str(body["location_id"]))
    get_or_404(db, Location, location_id)
    ro = RepairOrder(
        tenant_id=ctx.tenant_id,
        location_id=location_id,
        ro_number=str(body["ro_number"]).strip(),
        insurer_id=uuid.UUID(str(body["insurer_id"])) if body.get("insurer_id") else None,
        claim_number=body.get("claim_number") or None,  # "not provided" stays null
        adjuster_name=body.get("adjuster_name") or None,
        adjuster_email=body.get("adjuster_email") or None,
        vin=body.get("vin") or None,
        vehicle_desc=body.get("vehicle_desc") or None,
        created_by=ctx.user_id,
    )
    db.add(ro)
    db.flush()
    ctx.audit(db, "ro.created", "repair_order", ro.id, None, {"ro_number": ro.ro_number})
    db.refresh(ro)
    return to_dict(ro)


def patch_ro(ctx: Ctx, db: Session, ro_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    ro = lock_or_404(db, RepairOrder, ro_id)
    ctx.require(Action.EDIT_RO, "repair_order", ro.id)
    check_version(ro, if_match)
    before = {k: getattr(ro, k) for k in RO_EDITABLE if k in body}
    for key in RO_EDITABLE:
        if key in body:
            value = body[key]
            if key == "insurer_id" and value:
                value = uuid.UUID(str(value))
            setattr(ro, key, value if value != "" else None)
    ro.row_version += 1
    db.flush()
    ctx.audit(db, "ro.updated", "repair_order", ro.id, before, {k: getattr(ro, k) for k in before})
    return to_dict(ro)


def enqueue_job(ctx: Ctx, db: Session, kind: str, subject_id: uuid.UUID, idempotency_key: str, result: Any = None) -> Job:
    existing = db.execute(select(Job).where(Job.kind == kind, Job.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing is not None:
        return existing
    job = Job(
        tenant_id=ctx.tenant_id,
        kind=kind,
        subject_id=subject_id,
        idempotency_key=idempotency_key,
        correlation_id=uuid.UUID(ctx.correlation_id),
        result=result,
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return job


def store_document(
    ctx: Ctx,
    db: Session,
    *,
    ro: RepairOrder,
    purpose: str,
    data: bytes,
    source_system: str,
    packet_id: uuid.UUID | None,
    allowed_types: tuple[str, ...],
    job_key: str | None,
) -> tuple[Document, Job | None, bool]:
    """Register a file: same file for the same RO and purpose returns the existing row."""
    if not data:
        raise Problem(422, "Empty file")
    if len(data) > ctx.state.settings.max_pdf_bytes:
        raise Problem(413, "File too large", "at most 25 MB per file")
    content_type = sniff_type(data)
    if content_type not in allowed_types:
        raise Problem(415, "Unsupported file type", "the file content is not an accepted type")
    digest = sha256_hex(data)
    existing = db.execute(
        select(Document).where(Document.ro_id == ro.id, Document.purpose == purpose, Document.sha256 == bytes.fromhex(digest))
    ).scalar_one_or_none()
    if existing is not None:
        job = (
            db.execute(select(Job).where(Job.subject_id == existing.id, Job.kind == "parse_document").order_by(Job.created_at))
            .scalars()
            .first()
        )
        return existing, job, False
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"doc:{ro.id}:{purpose}"})
    version = (db.execute(select(func.max(Document.version)).where(Document.ro_id == ro.id, Document.purpose == purpose)).scalar() or 0) + 1
    doc_id = uuid.uuid4()
    key = build_object_key(
        tenant_id=ctx.tenant_id, ro_id=ro.id, purpose=purpose, document_id=doc_id, sha256=digest, content_type=content_type
    )
    ctx.state.store.put(key, data)
    doc = Document(
        id=doc_id,
        tenant_id=ctx.tenant_id,
        ro_id=ro.id,
        packet_id=packet_id,
        purpose=purpose,
        version=version,
        source_system=source_system,
        content_type=content_type,
        storage_key=key,
        sha256=bytes.fromhex(digest),
        size_bytes=len(data),
        uploaded_by=ctx.user_id,
    )
    db.add(doc)
    db.flush()
    ctx.audit(db, "document.uploaded", "document", doc.id, None, {"purpose": purpose, "version": version})
    job = None
    if purpose in ESTIMATE_PURPOSES and job_key:
        job = enqueue_job(ctx, db, "parse_document", doc.id, job_key)
    db.refresh(doc)
    return doc, job, True


def current_run(db: Session, document_id: uuid.UUID) -> ParseRun | None:
    return db.execute(select(ParseRun).where(ParseRun.document_id == document_id, ParseRun.is_current.is_(True))).scalar_one_or_none()


def _line_from(body: dict[str, Any], index: int) -> dict[str, Any]:
    hours = body.get("labor_hours")
    return {
        "line_no": int(body.get("line_no", index + 1)),
        "page": body.get("page"),
        "section": body.get("section"),
        "operation": body["operation"],
        "description": str(body["description"]),
        "part_number": body.get("part_number"),
        "part_type": body.get("part_type"),
        "part_price_cents": body.get("part_price_cents"),
        "labor_hours": Decimal(str(hours)) if hours is not None else None,
        "labor_type": body.get("labor_type"),
        "labor_rate_cents": body.get("labor_rate_cents"),
        "line_total_cents": int(body["line_total_cents"]),
    }


def manual_entry(ctx: Ctx, db: Session, document_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Manual line entry: the fallback when the parser cannot read a file (MH-02, E2E-02)."""
    doc = lock_or_404(db, Document, document_id)
    ctx.require(Action.EDIT_RO, "document", doc.id)
    if doc.purpose not in ESTIMATE_PURPOSES:
        raise Problem(422, "Not an estimate")
    lines = [_line_from(item, i) for i, item in enumerate(body.get("lines", []))]
    if not lines:
        raise Problem(422, "No lines")
    printed = body.get("printed_total_cents")
    rec = reconcile((x["line_total_cents"] for x in lines), int(printed) if printed is not None else None)
    db.execute(text("UPDATE parse_runs SET is_current = false WHERE document_id = :d AND is_current"), {"d": doc.id})
    run = ParseRun(
        tenant_id=ctx.tenant_id,
        document_id=doc.id,
        parser_name="manual",
        parser_version="manual-1",
        status="manual" if rec.status == "reconciled" else "unreconciled",
        printed_total_cents=rec.printed_total_cents,
        parsed_total_cents=rec.parsed_total_cents,
    )
    db.add(run)
    db.flush()
    for line in lines:
        db.add(EstimateLine(tenant_id=ctx.tenant_id, parse_run_id=run.id, source="manual", edited_by=ctx.user_id, **line))
    db.flush()
    ctx.audit(db, "parse_run.manual_entry", "parse_run", run.id, None, {"lines": len(lines), "status": run.status})
    return {"parse_run": to_dict(run), "difference_cents": rec.difference_cents}


def _refresh_run_totals(db: Session, run: ParseRun) -> None:
    totals = db.execute(select(EstimateLine.line_total_cents).where(EstimateLine.parse_run_id == run.id)).scalars().all()
    rec = reconcile(totals, run.printed_total_cents)
    run.parsed_total_cents = rec.parsed_total_cents
    if run.status != "failed":
        if rec.status == "reconciled":
            run.status = "manual" if run.parser_name == "manual" else "reconciled"
            run.confirm_reason = None
            run.confirmed_by = None
        else:
            run.status = "unreconciled"


def patch_estimate_line(ctx: Ctx, db: Session, line_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    line = lock_or_404(db, EstimateLine, line_id)
    ctx.require(Action.EDIT_RO, "estimate_line", line.id)
    check_version(line, if_match)
    before = {k: to_dict(line)[k] for k in LINE_EDITABLE if k in body}
    for key in LINE_EDITABLE:
        if key in body:
            value = body[key]
            if key == "labor_hours" and value is not None:
                value = Decimal(str(value))
            setattr(line, key, value)
    line.row_version += 1
    line.edited_by = ctx.user_id
    db.flush()  # the trigger resets every supplement line that depends on this source line
    run = get_or_404(db, ParseRun, line.parse_run_id)
    _refresh_run_totals(db, run)
    db.flush()
    ctx.audit(db, "estimate_line.corrected", "estimate_line", line.id, before, {k: to_dict(line)[k] for k in before})
    return {"line": to_dict(line), "parse_run": to_dict(run)}


def confirm_reconcile(ctx: Ctx, db: Session, document_id: uuid.UUID, reason: str) -> dict[str, Any]:
    doc = get_or_404(db, Document, document_id)
    ctx.require(Action.EDIT_RO, "document", doc.id)
    run = current_run(db, doc.id)
    if run is None or run.status != "unreconciled":
        raise Problem(409, "Nothing to confirm", "the current parse is not unreconciled")
    if len((reason or "").strip()) < 10:
        raise Problem(422, "Reason required", "confirm each total with a reason of at least 10 characters")
    run.confirm_reason = reason.strip()
    run.confirmed_by = ctx.user_id
    db.flush()
    ctx.audit(db, "parse_run.totals_confirmed", "parse_run", run.id, None, {"difference_cents": None})
    return to_dict(run)


def retry_job(ctx: Ctx, db: Session, job_id: uuid.UUID) -> dict[str, Any]:
    job = lock_or_404(db, Job, job_id)
    ctx.require(Action.EDIT_RO, "job", job.id)
    decision = decide_transition(job.state, job.state_version, "queued", job.state_version)
    if not decision.accepted:
        raise Problem(409, "Cannot retry", decision.reason)
    job.state = "queued"
    job.state_version = decision.new_version or job.state_version + 1
    job.attempt = 0
    job.error_code = None
    job.locked_until = None
    job.updated_at = datetime.now(UTC)
    db.flush()
    ctx.audit(db, "job.retried", "job", job.id, None, {"state": "queued"})
    return to_dict(job)
