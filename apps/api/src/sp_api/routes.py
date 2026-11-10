"""Routes for the B1 core path. Every mutation takes an Idempotency-Key; edits take If-Match.

Route inventory (IT-01, IT-02, IT-15): there is no route that emails, uploads to or
otherwise contacts an insurer, and no route that accepts a procedure document.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import Response as RawResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from sp_api.context import Ctx, Problem, authenticate
from sp_api.services import documents as docs
from sp_api.services import ledger, lines, packets, pilot
from sp_api.services.common import get_or_404, parse_uuid, to_dict
from sp_core.permissions import Action
from sp_db.models import ChecklistItem, Document, EstimateLine, Job, Packet, RepairOrder, SupplementLine
from sp_files import sha256_hex, sign_download_url, verify_download_signature

router = APIRouter()

JsonBody = dict[str, Any]


def get_ctx(request: Request) -> Ctx:
    ctx = authenticate(request, request.app.state.sp, request.state.correlation_id)
    request.state.ctx = ctx
    return ctx


def _json(status_body: tuple[int, dict[str, Any]]) -> JSONResponse:
    status, body = status_body
    return JSONResponse(body, status_code=status)


def _mutate(
    ctx: Ctx, request: Request, key: str | None, payload: Any, fn: Callable[[Session], dict[str, Any]], status: int = 200
) -> JSONResponse:
    return _json(ctx.idempotent(key, request.method, request.url.path, payload, lambda db: (status, fn(db))))


def _if_match(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip('"W/ '))
    except ValueError as exc:
        raise Problem(428, "If-Match must be the row_version") from exc


IdemKey = Header(default=None, alias="Idempotency-Key")
IfMatch = Header(default=None, alias="If-Match")


# Repair orders ---------------------------------------------------------------------------
@router.get("/ros")
def list_ros(ctx: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    with ctx.tx() as db:
        rows = db.execute(select(RepairOrder).order_by(RepairOrder.status, RepairOrder.created_at.desc()).limit(200)).scalars()
        return [to_dict(r) for r in rows]


@router.post("/ros")
def create_ro(request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey) -> JSONResponse:
    return _mutate(ctx, request, key, body, lambda db: docs.create_ro(ctx, db, body), 201)


@router.get("/ros/{ro_id}")
def get_ro(ro_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        return to_dict(get_or_404(db, RepairOrder, parse_uuid(ro_id)))


@router.patch("/ros/{ro_id}")
def patch_ro(
    ro_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    rid = parse_uuid(ro_id)
    return _mutate(ctx, request, key, body, lambda db: docs.patch_ro(ctx, db, rid, body, _if_match(if_match)))


# Documents and parse review ---------------------------------------------------------------
@router.post("/ros/{ro_id}/documents")
def upload_document(
    ro_id: str,
    request: Request,
    purpose: str = Form(...),
    source_system: str = Form("unknown"),
    file: UploadFile = File(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
) -> JSONResponse:
    rid = parse_uuid(ro_id)
    if purpose not in docs.ESTIMATE_PURPOSES:
        raise Problem(422, "Invalid purpose", "upload an insurer_estimate or shop_estimate")
    if source_system not in ("ccc_one", "mitchell", "audatex", "unknown"):
        raise Problem(422, "Invalid source system")
    data = file.file.read()

    def run(db: Session) -> dict[str, Any]:
        ro = get_or_404(db, RepairOrder, rid)
        ctx.require(Action.EDIT_RO, "repair_order", ro.id)
        doc, job, created = docs.store_document(
            ctx,
            db,
            ro=ro,
            purpose=purpose,
            data=data,
            source_system=source_system,
            packet_id=None,
            allowed_types=("application/pdf",),
            job_key=key,
        )
        return {"document": to_dict(doc, exclude=("storage_key",)), "job": to_dict(job) if job else None, "created": created}

    return _mutate(ctx, request, key, {"purpose": purpose, "sha256": sha256_hex(data)}, run, 202)


@router.get("/documents/{document_id}")
def get_document(document_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        doc = get_or_404(db, Document, parse_uuid(document_id))
        run = docs.current_run(db, doc.id)
        return {"document": to_dict(doc, exclude=("storage_key",)), "parse_run": to_dict(run) if run else None}


@router.get("/documents/{document_id}/lines")
def get_document_lines(document_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        doc = get_or_404(db, Document, parse_uuid(document_id))
        run = docs.current_run(db, doc.id)
        rows = []
        if run is not None:
            rows = [
                to_dict(r)
                for r in db.execute(
                    select(EstimateLine).where(EstimateLine.parse_run_id == run.id).order_by(EstimateLine.line_no)
                ).scalars()
            ]
        return {"parse_run": to_dict(run) if run else None, "lines": rows}


@router.post("/documents/{document_id}/manual-lines")
def manual_lines(
    document_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    did = parse_uuid(document_id)
    return _mutate(ctx, request, key, body, lambda db: docs.manual_entry(ctx, db, did, body), 201)


@router.patch("/estimate-lines/{line_id}")
def patch_estimate_line(
    line_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    lid = parse_uuid(line_id)
    return _mutate(ctx, request, key, body, lambda db: docs.patch_estimate_line(ctx, db, lid, body, _if_match(if_match)))


@router.post("/documents/{document_id}/reconcile")
def reconcile(
    document_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    did = parse_uuid(document_id)
    return _mutate(ctx, request, key, body, lambda db: docs.confirm_reconcile(ctx, db, did, str(body.get("reason", ""))))


@router.get("/jobs/{job_id}")
def get_job(job_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        return to_dict(get_or_404(db, Job, parse_uuid(job_id)))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, request: Request, ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey) -> JSONResponse:
    jid = parse_uuid(job_id)
    return _mutate(ctx, request, key, {}, lambda db: docs.retry_job(ctx, db, jid))


# Diff, lines and approval -------------------------------------------------------------------
@router.post("/ros/{ro_id}/diff")
def run_diff(ro_id: str, request: Request, ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey) -> JSONResponse:
    rid = parse_uuid(ro_id)
    return _mutate(ctx, request, key, {}, lambda db: lines.run_diff(ctx, db, rid))


@router.get("/ros/{ro_id}/lines")
def list_lines(ro_id: str, ctx: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    with ctx.tx() as db:
        ro = get_or_404(db, RepairOrder, parse_uuid(ro_id))
        rows = db.execute(
            select(SupplementLine).where(SupplementLine.ro_id == ro.id).order_by(SupplementLine.created_at, SupplementLine.id)
        ).scalars()
        return [to_dict(r) for r in rows]


@router.post("/ros/{ro_id}/lines")
def create_line(
    ro_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    rid = parse_uuid(ro_id)
    return _mutate(ctx, request, key, body, lambda db: lines.create_line(ctx, db, rid, body), 201)


@router.patch("/lines/{line_id}")
def patch_line(
    line_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    lid = parse_uuid(line_id)
    return _mutate(ctx, request, key, body, lambda db: lines.patch_line(ctx, db, lid, body, _if_match(if_match)))


@router.post("/lines/{line_id}/approve")
def approve_line(
    line_id: str, request: Request, ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey, if_match: str | None = IfMatch
) -> JSONResponse:
    lid = parse_uuid(line_id)
    return _mutate(ctx, request, key, {"if_match": if_match}, lambda db: lines.approve_line(ctx, db, lid, _if_match(if_match)))


@router.post("/lines/{line_id}/exclude")
def exclude_line(
    line_id: str, request: Request, ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey, if_match: str | None = IfMatch
) -> JSONResponse:
    lid = parse_uuid(line_id)
    return _mutate(ctx, request, key, {"if_match": if_match}, lambda db: lines.exclude_line(ctx, db, lid, _if_match(if_match)))


@router.get("/checklist")
def checklist(ctx: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    with ctx.tx() as db:
        return [
            to_dict(i)
            for i in db.execute(select(ChecklistItem).order_by(ChecklistItem.repair_type, ChecklistItem.operation_name)).scalars()
        ]


# Evidence -----------------------------------------------------------------------------------
@router.post("/lines/{line_id}/photos")
def add_photos(
    line_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    attested: bool | None = Form(None),
    taken_by_shop: bool | None = Form(None),
    attestation_note: str | None = Form(None),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
) -> JSONResponse:
    lid = parse_uuid(line_id)
    payload_files = [("", f.file.read()) for f in files]
    payload = {"files": [sha256_hex(d) for _, d in payload_files], "attested": attested, "taken": taken_by_shop, "note": attestation_note}
    return _mutate(
        ctx,
        request,
        key,
        payload,
        lambda db: lines.add_photos(
            ctx, db, lid, payload_files, attested=attested, taken_by_shop=taken_by_shop, attestation_note=attestation_note
        ),
    )


@router.post("/lines/{line_id}/references")
def add_reference(
    line_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    lid = parse_uuid(line_id)
    return _mutate(ctx, request, key, body, lambda db: lines.add_reference(ctx, db, lid, body), 201)


@router.patch("/references/{reference_id}")
def patch_reference(
    reference_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    rid = parse_uuid(reference_id)
    return _mutate(ctx, request, key, body, lambda db: lines.patch_reference(ctx, db, rid, body, _if_match(if_match)))


@router.patch("/photos/{photo_id}")
def patch_photo(
    photo_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    pid = parse_uuid(photo_id)
    return _mutate(ctx, request, key, body, lambda db: lines.patch_photo(ctx, db, pid, body, _if_match(if_match)))


@router.delete("/evidence/{evidence_id}")
def delete_evidence(evidence_id: str, request: Request, ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey) -> JSONResponse:
    eid = parse_uuid(evidence_id)
    return _mutate(ctx, request, key, {}, lambda db: lines.delete_evidence(ctx, db, eid))


# Packets ------------------------------------------------------------------------------------
@router.get("/ros/{ro_id}/packet-review")
def packet_review(ro_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        return packets.packet_review(ctx, db, parse_uuid(ro_id))


@router.post("/ros/{ro_id}/packets")
def freeze(
    ro_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    rid = parse_uuid(ro_id)
    return _mutate(ctx, request, key, body, lambda db: packets.freeze_packet(ctx, db, rid, body), 201)


@router.get("/packets/{packet_id}")
def get_packet(packet_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        return packets.packet_view(db, get_or_404(db, Packet, parse_uuid(packet_id)))


@router.get("/packets/{packet_id}/pdf")
def packet_pdf_link(packet_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        packet = get_or_404(db, Packet, parse_uuid(packet_id))
        if packet.pdf_storage_key is None:
            raise Problem(409, "PDF not available", "the PDF is still rendering or was taken down")
        settings = ctx.state.settings
        path = f"/api/v1/packets/{packet.id}/pdf/download"
        return {"url": sign_download_url(public_base_url=settings.public_base_url, path=path, secret=settings.session_key)}


@router.get("/packets/{packet_id}/pdf/download")
def packet_pdf_download(packet_id: str, expires: int, sig: str, ctx: Ctx = Depends(get_ctx)) -> Any:
    with ctx.tx() as db:
        packet = get_or_404(db, Packet, parse_uuid(packet_id))
        path = f"/api/v1/packets/{packet.id}/pdf/download"
        if not verify_download_signature(path=path, expires=expires, sig=sig, secret=ctx.state.settings.session_key):
            raise Problem(403, "Link expired")
        if packet.pdf_storage_key is None:
            raise Problem(409, "PDF not available")
        return RawResponse(ctx.state.store.get(packet.pdf_storage_key), media_type="application/pdf")


@router.post("/packets/{packet_id}/mark-sent")
def mark_sent(
    packet_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    pid = parse_uuid(packet_id)
    return _mutate(ctx, request, key, body, lambda db: packets.mark_sent(ctx, db, pid, body))


@router.post("/packets/{packet_id}/unmark-sent")
def unmark_sent(
    packet_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    pid = parse_uuid(packet_id)
    return _mutate(ctx, request, key, body, lambda db: packets.unmark_sent(ctx, db, pid, body))


@router.post("/packets/{packet_id}/takedown")
def takedown(
    packet_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    pid = parse_uuid(packet_id)
    return _mutate(ctx, request, key, body, lambda db: packets.takedown(ctx, db, pid, body))


# Ledger -------------------------------------------------------------------------------------
@router.put("/packet-lines/{packet_line_id}/response")
def record_response(
    packet_line_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    plid = parse_uuid(packet_line_id)
    return _mutate(ctx, request, key, body, lambda db: ledger.record_response(ctx, db, plid, body, _if_match(if_match)))


def _packet_document(purpose: str, action: Action) -> Callable[..., JSONResponse]:
    def handler(
        packet_id: str, request: Request, file: UploadFile = File(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
    ) -> JSONResponse:
        pid = parse_uuid(packet_id)
        data = file.file.read()

        def run(db: Session) -> dict[str, Any]:
            packet = get_or_404(db, Packet, pid)
            ctx.require(action, "packet", packet.id)
            ro = get_or_404(db, RepairOrder, packet.ro_id)
            doc, _, created = docs.store_document(
                ctx,
                db,
                ro=ro,
                purpose=purpose,
                data=data,
                source_system="unknown",
                packet_id=packet.id,
                allowed_types=("application/pdf", "image/jpeg", "image/png"),
                job_key=None,
            )
            return {"document": to_dict(doc, exclude=("storage_key",)), "created": created}

        return _mutate(ctx, request, key, {"sha256": sha256_hex(data)}, run, 201)

    return handler


router.add_api_route("/packets/{packet_id}/response-documents", _packet_document("response", Action.RECORD_RESPONSE), methods=["POST"])
router.add_api_route("/packets/{packet_id}/remittance-documents", _packet_document("remittance", Action.RECORD_PAYMENT), methods=["POST"])


@router.post("/ros/{ro_id}/payments")
def record_payment(
    ro_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    rid = parse_uuid(ro_id)
    return _mutate(ctx, request, key, body, lambda db: ledger.record_payment(ctx, db, rid, body), 201)


@router.post("/payments/{payment_id}/reverse")
def reverse_payment(
    payment_id: str, request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey
) -> JSONResponse:
    pid = parse_uuid(payment_id)
    return _mutate(ctx, request, key, body, lambda db: ledger.reverse_payment(ctx, db, pid, body), 201)


@router.get("/ros/{ro_id}/ledger")
def ro_ledger(ro_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        return ledger.ro_ledger(db, parse_uuid(ro_id))


# Pilot --------------------------------------------------------------------------------------
@router.get("/baseline-ros")
def list_baseline(ctx: Ctx = Depends(get_ctx)) -> list[dict[str, Any]]:
    with ctx.tx() as db:
        return pilot.list_baseline(db)


@router.post("/baseline-ros")
def add_baseline(request: Request, body: JsonBody = Body(...), ctx: Ctx = Depends(get_ctx), key: str | None = IdemKey) -> JSONResponse:
    return _mutate(ctx, request, key, body, lambda db: pilot.add_baseline_row(ctx, db, body), 201)


@router.patch("/pilots/{pilot_id}/counts")
def set_counts(
    pilot_id: str,
    request: Request,
    body: JsonBody = Body(...),
    ctx: Ctx = Depends(get_ctx),
    key: str | None = IdemKey,
    if_match: str | None = IfMatch,
) -> JSONResponse:
    pid = parse_uuid(pilot_id)
    return _mutate(ctx, request, key, body, lambda db: pilot.set_counts(ctx, db, pid, body, _if_match(if_match)))


@router.get("/pilots/{pilot_id}/report")
def pilot_report(pilot_id: str, ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.tx() as db:
        return pilot.pilot_report(db, parse_uuid(pilot_id))
