"""Job handlers: parse_document, render_packet, takedown_purge (TRD 8.5).

Each handler runs inside the job's tenant transaction. A job naming another tenant's
row finds nothing under row-level security and fails with ``not_found`` (IT-01).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from sp_core.reconcile import reconcile
from sp_db.models import Document, EstimateLine, Packet, PacketLine, ParseRun
from sp_files import ObjectStore, build_object_key, sha256_hex
from sp_files.render import DeterministicRenderer, PacketRenderer
from sp_parsers import ParserError, get_parser
from sp_worker.runner import ClaimedJob, Handler, JobFailure, Outcome

__all__ = ["default_handlers", "parse_document", "render_packet", "takedown_purge"]


def parse_document(db: Session, job: ClaimedJob, store: ObjectStore, _: dict[str, Any] | None) -> Outcome:
    doc = db.get(Document, job.subject_id)
    if doc is None:
        raise JobFailure("not_found", retryable=False)
    if doc.storage_key is None:
        raise JobFailure("purged", retryable=False)
    parser = get_parser(doc.source_system)
    if parser is None:
        raise JobFailure("no_parser_manual_entry_offered", retryable=False)
    current = db.execute(select(ParseRun).where(ParseRun.document_id == doc.id, ParseRun.is_current.is_(True))).scalar_one_or_none()
    if current is not None and current.parser_name == parser.name and current.parser_version == parser.version:
        return Outcome("succeeded", {"parse_run_id": str(current.id), "status": current.status, "repeat": True})
    try:
        parsed = parser.parse(store.get(doc.storage_key))
    except ParserError as exc:
        raise JobFailure("unreadable_manual_entry_offered", retryable=False) from exc
    rec = reconcile((line.line_total_cents for line in parsed.lines), parsed.printed_total_cents)
    if current is not None:
        current.is_current = False
        db.flush()
    run = ParseRun(
        tenant_id=job.tenant_id,
        document_id=doc.id,
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        status=rec.status,
        printed_total_cents=rec.printed_total_cents,
        parsed_total_cents=rec.parsed_total_cents,
    )
    db.add(run)
    db.flush()
    for line in parsed.lines:
        db.add(
            EstimateLine(
                tenant_id=job.tenant_id,
                parse_run_id=run.id,
                line_no=line.line_no,
                page=line.page,
                section=line.section,
                operation=line.operation,
                description=line.description,
                part_number=line.part_number,
                part_type=line.part_type,
                part_price_cents=line.part_price_cents,
                labor_hours=line.labor_hours,
                labor_type=line.labor_type,
                labor_rate_cents=line.labor_rate_cents,
                line_total_cents=line.line_total_cents,
                source="parser",
            )
        )
    doc.page_count = parsed.page_count
    db.flush()
    return Outcome("succeeded", {"parse_run_id": str(run.id), "status": run.status, "lines": len(parsed.lines)})


def make_render_packet(renderer: PacketRenderer) -> Handler:
    def render_packet(db: Session, job: ClaimedJob, store: ObjectStore, _: dict[str, Any] | None) -> Outcome:
        packet = db.get(Packet, job.subject_id)
        if packet is None:
            raise JobFailure("not_found", retryable=False)
        if packet.purged_at is not None:
            return Outcome("succeeded", {"skipped": "taken_down"})
        lines = db.execute(select(PacketLine).where(PacketLine.packet_id == packet.id).order_by(PacketLine.line_no)).scalars()
        snapshot = {
            "packet_id": str(packet.id),
            "version": packet.version,
            "requested_total_cents": packet.requested_total_cents,
            "lines": [
                {
                    "line_no": pl.line_no,
                    "description": pl.description,
                    "requested_cents": pl.requested_cents,
                    "approved_by": str(pl.approved_by),
                    "evidence": pl.evidence_snapshot,
                }
                for pl in lines
            ],
            "renderer": renderer.name,
        }
        data = renderer.render(snapshot)
        digest = sha256_hex(data)
        if packet.pdf_sha256 is not None:
            # Hash stored at first success; a re-render must match it (R-01).
            if bytes(packet.pdf_sha256).hex() != digest:
                raise JobFailure("render_hash_mismatch", retryable=False)
            return Outcome("succeeded", {"pdf_sha256": digest, "repeat": True})
        key = build_object_key(
            tenant_id=job.tenant_id,
            ro_id=packet.ro_id,
            purpose="packet",
            document_id=packet.id,
            sha256=digest,
            content_type="application/pdf",
        )
        store.put(key, data)
        db.execute(
            text("UPDATE packets SET pdf_storage_key = :k, pdf_sha256 = :h WHERE id = :id AND pdf_sha256 IS NULL"),
            {"k": key, "h": bytes.fromhex(digest), "id": packet.id},
        )
        return Outcome("succeeded", {"pdf_sha256": digest})

    return render_packet


def takedown_purge(db: Session, job: ClaimedJob, store: ObjectStore, stored: dict[str, Any] | None) -> Outcome:
    packet = db.get(Packet, job.subject_id)
    if packet is None:
        raise JobFailure("not_found", retryable=False)
    prefix = f"t/{job.tenant_id}/"
    keys = [k for k in (stored or {}).get("keys", []) if isinstance(k, str) and k.startswith(prefix)]
    for key in keys:
        store.delete(key)
    return Outcome("succeeded", {"keys": keys, "deleted": len(keys)})


render_packet = make_render_packet(DeterministicRenderer())


def default_handlers() -> dict[str, Handler]:
    return {"parse_document": parse_document, "render_packet": render_packet, "takedown_purge": takedown_purge}
