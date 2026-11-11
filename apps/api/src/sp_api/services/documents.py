"""ROs, uploads, parse review, manual entry and jobs (MH-01, MH-02, MH-12; T-3.1.1, T-3.1.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem
from sp_api.services import inputs
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
    location_id = inputs.a_uuid(body, "location_id")
    assert location_id is not None
    get_or_404(db, Location, location_id)
    ro_number = inputs.text_field(body, "ro_number", required=True)
    assert ro_number is not None
    ro = RepairOrder(
        tenant_id=ctx.tenant_id,
        location_id=location_id,
        ro_number=ro_number.strip(),
        insurer_id=inputs.a_uuid(body, "insurer_id", required=False),
        claim_number=inputs.text_field(body, "claim_number"),  # "not provided" stays null
        adjuster_name=inputs.text_field(body, "adjuster_name"),
        adjuster_email=inputs.text_field(body, "adjuster_email"),
        vin=inputs.text_field(body, "vin", limit=17),
        vehicle_desc=inputs.text_field(body, "vehicle_desc"),
        email_free_paragraph=inputs.text_field(body, "email_free_paragraph"),
        created_by=ctx.user_id,
    )
    db.add(ro)
    db.flush()
    ctx.audit(db, "ro.created", "repair_order", ro.id, None, {"ro_number": ro.ro_number})
    db.refresh(ro)
    return inputs.with_notice(to_dict(ro))


def patch_ro(ctx: Ctx, db: Session, ro_id: uuid.UUID, body: dict[str, Any], if_match: int | None) -> dict[str, Any]:
    ro = lock_or_404(db, RepairOrder, ro_id)
    ctx.require(Action.EDIT_RO, "repair_order", ro.id)
    check_version(ro, if_match)
    before = {k: getattr(ro, k) for k in RO_EDITABLE if k in body}
    for key in RO_EDITABLE:
        if key in body:
            if key == "insurer_id":
                value: Any = inputs.a_uuid(body, key, required=False)
            elif key == "status":
                value = body[key]
                if value not in ("open", "closed"):
                    raise Problem(422, "Invalid status")
            else:
                value = inputs.text_field(body, key, limit=17 if key == "vin" else None)
                if key == "ro_number" and value is None:
                    raise Problem(422, "Missing field", "ro_number is required")
            setattr(ro, key, value)
    ro.row_version += 1
    db.flush()
    ctx.audit(db, "ro.updated", "repair_order", ro.id, before, {k: getattr(ro, k) for k in before})
    return inputs.with_notice(to_dict(ro))


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
    # Lock before the existence check so concurrent uploads of the same file under different keys
    # all receive the existing document instead of a unique-constraint conflict.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"doc:{ro.id}:{purpose}"})
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


_OPERATIONS = ("replace", "repair", "remove_install", "refinish", "blend", "sublet", "scan", "calibrate", "materials", "other")
_PART_TYPES = ("oem", "aftermarket", "recycled", "remanufactured")


def _line_fields(body: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        if key not in body:
            continue
        if key in ("part_price_cents", "labor_rate_cents"):
            out[key] = inputs.cents(body, key, required=False)
        elif key == "line_total_cents":
            out[key] = inputs.cents(body, key, allow_negative=True)
        elif key == "labor_hours":
            out[key] = inputs.hours(body, key)
        elif key == "operation":
            if body[key] not in _OPERATIONS:
                raise Problem(422, "Invalid operation", field=key)
            out[key] = body[key]
        elif key == "part_type":
            if body[key] is not None and body[key] not in _PART_TYPES:
                raise Problem(422, "Invalid part type", field=key)
            out[key] = body[key]
        elif key == "description":
            out[key] = inputs.text_field(body, key, required=True)
        elif key in ("page", "line_no"):
            out[key] = inputs.an_int(body, key, minimum=1)
        else:
            out[key] = inputs.text_field(body, key)
    return out


def _line_from(body: Any, index: int) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise Problem(422, "Invalid line")
    for key in ("operation", "description", "line_total_cents"):
        inputs.req(body, key)
    fields = _line_fields(body, ("line_no", "page", "section", *LINE_EDITABLE))
    fields.setdefault("line_no", index + 1)
    if fields["line_no"] is None:
        fields["line_no"] = index + 1
    return fields


def manual_entry(ctx: Ctx, db: Session, document_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """Manual line entry: the fallback when the parser cannot read a file (MH-02, E2E-02)."""
    doc = lock_or_404(db, Document, document_id)
    ctx.require(Action.EDIT_RO, "document", doc.id)
    if doc.purpose not in ESTIMATE_PURPOSES:
        raise Problem(422, "Not an estimate")
    raw_lines = body.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise Problem(422, "No lines")
    lines = [_line_from(item, i) for i, item in enumerate(raw_lines)]
    printed = inputs.cents(body, "printed_total_cents", required=False, allow_negative=True)
    rec = reconcile((x["line_total_cents"] for x in lines), printed)
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
    for key, value in _line_fields(body, LINE_EDITABLE).items():
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
    if len(reason) > inputs.LIMITS["reason"]:
        raise Problem(422, "Text too long", "reason is limited to 500 characters")
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
