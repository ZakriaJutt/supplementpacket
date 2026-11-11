"""ORM models. Kept in parity with the migrations by scripts/orm_parity.py (R-08, IT-07).

Money is BIGINT cents (AD-08); hours NUMERIC(6,2). Every tenant-owned table carries
tenant_id and composite foreign keys repeating it (schema section 1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["TENANT_TABLES", "Base"]

UUIDT = UUID(as_uuid=True)
TS = DateTime(timezone=True)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDT, primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant() -> Mapped[uuid.UUID]:
    return mapped_column(UUIDT, ForeignKey("tenants.id"), nullable=False)


def _user_fk(nullable: bool = True) -> Mapped[Any]:
    return mapped_column(UUIDT, ForeignKey("users.id"), nullable=nullable)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="America/Los_Angeles")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    ai_consent_at: Mapped[datetime | None] = mapped_column(TS)
    ai_consent_by: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("status IN ('active','read_only','deleting')", name="ck_tenants_status"),
        CheckConstraint("retention_days BETWEEN 30 AND 730", name="ck_tenants_retention"),
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(TS)
    display_name: Mapped[str | None] = mapped_column(Text)
    is_operator: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(CHAR(2), nullable=False, server_default="WA")
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_locations_tenant_id"),
        UniqueConstraint("tenant_id", "name", name="uq_locations_name"),
    )


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        CheckConstraint("role IN ('owner','estimator','office')", name="ck_memberships_role"),
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_user"),
    )


class OperatorGrant(Base):
    __tablename__ = "operator_grants"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    operator_user_id: Mapped[uuid.UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)
    __table_args__ = (CheckConstraint("expires_at <= created_at + interval '30 days'", name="ck_operator_grants_30d"),)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUIDT, ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT, ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)


class Insurer(Base):
    __tablename__ = "insurers"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_insurers_tenant_id"),
        Index("uq_insurers_name", "tenant_id", func.lower(text("name")), unique=True),
    )


class RepairOrder(Base):
    __tablename__ = "repair_orders"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    location_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    ro_number: Mapped[str] = mapped_column(Text, nullable=False)
    insurer_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    claim_number: Mapped[str | None] = mapped_column(Text)
    adjuster_name: Mapped[str | None] = mapped_column(Text)
    adjuster_email: Mapped[str | None] = mapped_column(CITEXT)
    vin: Mapped[str | None] = mapped_column(Text)
    vehicle_desc: Mapped[str | None] = mapped_column(Text)
    email_free_paragraph: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("vin IS NULL OR length(vin) = 17", name="ck_repair_orders_vin"),
        CheckConstraint("status IN ('open','closed')", name="ck_repair_orders_status"),
        UniqueConstraint("tenant_id", "id", name="uq_repair_orders_tenant_id"),
        UniqueConstraint("tenant_id", "location_id", "ro_number", name="uq_repair_orders_number"),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"], name="fk_repair_orders_location"),
        ForeignKeyConstraint(["tenant_id", "insurer_id"], ["insurers.tenant_id", "insurers.id"], name="fk_repair_orders_insurer"),
        Index("ix_repair_orders_list", "tenant_id", "status", text("created_at DESC")),
        Index("ix_repair_orders_insurer", "tenant_id", "insurer_id"),
    )


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    packet_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    purged_at: Mapped[datetime | None] = mapped_column(TS)
    __table_args__ = (
        CheckConstraint("purpose IN ('insurer_estimate','shop_estimate','response','remittance')", name="ck_documents_purpose"),
        CheckConstraint("source_system IN ('ccc_one','mitchell','audatex','unknown')", name="ck_documents_source"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 26214400", name="ck_documents_size"),
        CheckConstraint("purpose NOT IN ('response','remittance') OR packet_id IS NOT NULL", name="ck_documents_packet"),
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id"),
        UniqueConstraint("tenant_id", "ro_id", "id", name="uq_documents_ro_id"),
        UniqueConstraint("tenant_id", "packet_id", "id", name="uq_documents_packet_id"),
        UniqueConstraint("tenant_id", "ro_id", "purpose", "version", name="uq_documents_version"),
        UniqueConstraint("tenant_id", "ro_id", "purpose", "sha256", name="uq_documents_sha"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_documents_ro"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "packet_id"],
            ["packets.tenant_id", "packets.ro_id", "packets.id"],
            name="fk_documents_packet",
            use_alter=True,
        ),
        Index("ix_documents_latest", "tenant_id", "ro_id", "purpose", text("version DESC")),
        Index("ix_documents_retention", "purged_at", "uploaded_at", postgresql_where=text("storage_key IS NOT NULL")),
    )


class ParseRun(Base):
    __tablename__ = "parse_runs"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    document_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    parser_name: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    printed_total_cents: Mapped[int | None] = mapped_column(BigInteger)
    parsed_total_cents: Mapped[int | None] = mapped_column(BigInteger)
    confirm_reason: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[uuid.UUID | None] = _user_fk()
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("status IN ('reconciled','unreconciled','failed','manual')", name="ck_parse_runs_status"),
        UniqueConstraint("tenant_id", "id", name="uq_parse_runs_tenant_id"),
        ForeignKeyConstraint(["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"], name="fk_parse_runs_document"),
        Index("uq_parse_runs_current", "document_id", unique=True, postgresql_where=text("is_current")),
    )


_OPERATIONS = "('replace','repair','remove_install','refinish','blend','sublet','scan','calibrate','materials','other')"


class EstimateLine(Base):
    __tablename__ = "estimate_lines"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    parse_run_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    part_number: Mapped[str | None] = mapped_column(Text)
    part_type: Mapped[str | None] = mapped_column(Text)
    part_price_cents: Mapped[int | None] = mapped_column(BigInteger)
    labor_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    labor_type: Mapped[str | None] = mapped_column(Text)
    labor_rate_cents: Mapped[int | None] = mapped_column(BigInteger)
    line_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="parser")
    edited_by: Mapped[uuid.UUID | None] = _user_fk()
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint(f"operation IN {_OPERATIONS}", name="ck_estimate_lines_operation"),
        CheckConstraint("part_type IN ('oem','aftermarket','recycled','remanufactured')", name="ck_estimate_lines_part_type"),
        CheckConstraint("source IN ('parser','manual','ai_suggested')", name="ck_estimate_lines_source"),
        UniqueConstraint("tenant_id", "id", name="uq_estimate_lines_tenant_id"),
        UniqueConstraint("parse_run_id", "line_no", name="uq_estimate_lines_line_no"),
        ForeignKeyConstraint(["tenant_id", "parse_run_id"], ["parse_runs.tenant_id", "parse_runs.id"], name="fk_estimate_lines_run"),
        Index("ix_estimate_lines_review", "tenant_id", "parse_run_id", "line_no"),
    )


class DiffRun(Base):
    __tablename__ = "diff_runs"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    insurer_document_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    shop_document_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_diff_runs_tenant_id"),
        UniqueConstraint("tenant_id", "ro_id", "id", name="uq_diff_runs_ro_id"),
        UniqueConstraint("tenant_id", "insurer_document_id", "shop_document_id", "engine_version", name="uq_diff_runs_inputs"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_diff_runs_ro"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "insurer_document_id"],
            ["documents.tenant_id", "documents.ro_id", "documents.id"],
            name="fk_diff_runs_insurer_doc",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "shop_document_id"],
            ["documents.tenant_id", "documents.ro_id", "documents.id"],
            name="fk_diff_runs_shop_doc",
        ),
    )


class ChecklistVersion(Base):
    __tablename__ = "checklist_versions"
    id: Mapped[uuid.UUID] = _pk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    author: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("version", name="uq_checklist_versions_version"),)


class ChecklistItem(Base):
    """Operation names only: no labour-time, price or procedure-text column (AD-12)."""

    __tablename__ = "checklist_items"
    id: Mapped[uuid.UUID] = _pk()
    checklist_version_id: Mapped[uuid.UUID] = mapped_column(UUIDT, ForeignKey("checklist_versions.id"), nullable=False)
    repair_type: Mapped[str] = mapped_column(Text, nullable=False)
    operation_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)


_CATEGORIES = (
    "('missing_operation','labor_hours_gap','refinish_hours_gap','part_price_gap','part_type_difference',"
    "'rate_difference','materials_gap','other')"
)


class SupplementLine(Base):
    __tablename__ = "supplement_lines"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    diff_run_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    diff_key: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    shop_line_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    insurer_line_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    checklist_item_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT, ForeignKey("checklist_items.id"))
    match_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="matched")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hours_delta: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    explanation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    approved_by: Mapped[uuid.UUID | None] = _user_fk()
    approved_at: Mapped[datetime | None] = mapped_column(TS)
    approved_row_version: Mapped[int | None] = mapped_column(Integer)
    approved_fingerprint: Mapped[bytes | None] = mapped_column(LargeBinary)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("origin IN ('diff','checklist','manual','ai_suggested')", name="ck_supplement_lines_origin"),
        CheckConstraint(f"category IN {_CATEGORIES}", name="ck_supplement_lines_category"),
        CheckConstraint("match_state IN ('matched','needs_review','not_applicable')", name="ck_supplement_lines_match"),
        CheckConstraint("requested_cents >= 0", name="ck_supplement_lines_requested"),
        CheckConstraint("status IN ('draft','approved','excluded')", name="ck_supplement_lines_status"),
        CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND approved_fingerprint IS NOT NULL "
            "AND approved_row_version = row_version AND match_state <> 'needs_review')",
            name="ck_supplement_lines_approved",
        ),
        CheckConstraint("origin <> 'checklist' OR checklist_item_id IS NOT NULL", name="ck_supplement_lines_checklist"),
        CheckConstraint("origin <> 'diff' OR diff_run_id IS NOT NULL", name="ck_supplement_lines_diff"),
        UniqueConstraint("tenant_id", "id", name="uq_supplement_lines_tenant_id"),
        UniqueConstraint("tenant_id", "ro_id", "id", name="uq_supplement_lines_ro_id"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_supplement_lines_ro"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "diff_run_id"],
            ["diff_runs.tenant_id", "diff_runs.ro_id", "diff_runs.id"],
            name="fk_supplement_lines_diff",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "shop_line_id"], ["estimate_lines.tenant_id", "estimate_lines.id"], name="fk_supplement_lines_shop_line"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "insurer_line_id"], ["estimate_lines.tenant_id", "estimate_lines.id"], name="fk_supplement_lines_insurer_line"
        ),
        Index("ix_supplement_lines_status", "tenant_id", "ro_id", "status"),
        Index("ix_supplement_lines_needs_review", "tenant_id", "ro_id", postgresql_where=text("match_state = 'needs_review'")),
        Index("uq_supplement_lines_diff_key", "tenant_id", "ro_id", "diff_key", unique=True, postgresql_where=text("diff_key IS NOT NULL")),
    )


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    taken_by_shop: Mapped[bool] = mapped_column(Boolean, nullable=False)
    not_licensed_copy_attested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attested_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    attested_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    attestation_note: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    purged_at: Mapped[datetime | None] = mapped_column(TS)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint("not_licensed_copy_attested", name="ck_photos_attested"),
        CheckConstraint("taken_by_shop OR attestation_note IS NOT NULL", name="ck_photos_note"),
        UniqueConstraint("tenant_id", "id", name="uq_photos_tenant_id"),
        UniqueConstraint("tenant_id", "ro_id", "id", name="uq_photos_ro_id"),
        UniqueConstraint("tenant_id", "ro_id", "sha256", name="uq_photos_sha"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_photos_ro"),
    )


class ReferenceCitation(Base):
    """Typed citation only. No body-text column (AD-06)."""

    __tablename__ = "reference_citations"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    material_type: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    identifier: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    accessed_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "material_type IN ('oem_procedure_subscription','oem_position_statement','estimating_guide','industry_body','other')",
            name="ck_reference_citations_type",
        ),
        CheckConstraint("note IS NULL OR length(note) <= 300", name="ck_reference_citations_note"),
        CheckConstraint(
            "url IS NULL OR (url LIKE 'https://%' AND material_type NOT IN ('oem_procedure_subscription','estimating_guide'))",
            name="ck_reference_citations_url",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_reference_citations_tenant_id"),
    )


class LineEvidence(Base):
    __tablename__ = "line_evidence"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    supplement_line_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    photo_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    created_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("num_nonnulls(photo_id, reference_id) = 1", name="ck_line_evidence_one"),
        UniqueConstraint("supplement_line_id", "photo_id", name="uq_line_evidence_photo"),
        UniqueConstraint("supplement_line_id", "reference_id", name="uq_line_evidence_reference"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "supplement_line_id"],
            ["supplement_lines.tenant_id", "supplement_lines.ro_id", "supplement_lines.id"],
            name="fk_line_evidence_line",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "photo_id"], ["photos.tenant_id", "photos.ro_id", "photos.id"], name="fk_line_evidence_photo"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "reference_id"],
            ["reference_citations.tenant_id", "reference_citations.id"],
            name="fk_line_evidence_reference",
        ),
    )


class Packet(Base):
    __tablename__ = "packets"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="frozen")
    review_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    supersedes_packet_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    requested_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    email_draft: Mapped[str] = mapped_column(Text, nullable=False)
    frozen_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    pdf_storage_key: Mapped[str | None] = mapped_column(Text)
    pdf_sha256: Mapped[bytes | None] = mapped_column(LargeBinary)
    sent_on: Mapped[date | None] = mapped_column(Date)
    sent_channel: Mapped[str | None] = mapped_column(Text)
    sent_marked_by: Mapped[uuid.UUID | None] = _user_fk()
    sent_marked_at: Mapped[datetime | None] = mapped_column(TS)
    correction_note: Mapped[str | None] = mapped_column(Text)
    purged_at: Mapped[datetime | None] = mapped_column(TS)
    purge_reason: Mapped[str | None] = mapped_column(Text)
    purged_by: Mapped[uuid.UUID | None] = _user_fk()
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint("status IN ('frozen','sent','superseded')", name="ck_packets_status"),
        CheckConstraint("line_count > 0", name="ck_packets_line_count"),
        CheckConstraint("sent_channel IN ('email','insurer_portal','estimating_system','in_person','other')", name="ck_packets_channel"),
        CheckConstraint(
            "status <> 'sent' OR (sent_on IS NOT NULL AND sent_channel IS NOT NULL AND sent_marked_by IS NOT NULL)",
            name="ck_packets_sent",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_packets_tenant_id"),
        UniqueConstraint("tenant_id", "ro_id", "id", name="uq_packets_ro_id"),
        UniqueConstraint("tenant_id", "ro_id", "version", name="uq_packets_version"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_packets_ro"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "supersedes_packet_id"],
            ["packets.tenant_id", "packets.ro_id", "packets.id"],
            name="fk_packets_supersedes",
        ),
        Index("uq_packets_one_live", "tenant_id", "ro_id", unique=True, postgresql_where=text("status IN ('frozen','sent')")),
        Index("ix_packets_sent", "tenant_id", "sent_on", postgresql_where=text("status = 'sent'")),
    )


class PacketLine(Base):
    __tablename__ = "packet_lines"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    packet_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    supplement_line_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    approved_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    approved_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    approved_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    carried_from_packet_line_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    response_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="no_response")
    approved_cents: Mapped[int | None] = mapped_column(BigInteger)
    denial_reason: Mapped[str | None] = mapped_column(Text)
    response_date: Mapped[date | None] = mapped_column(Date)
    response_document_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    override_reason: Mapped[str | None] = mapped_column(Text)
    response_recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    request_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="requested")
    response_recorded_at: Mapped[datetime | None] = mapped_column(TS)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint("request_state IN ('requested','withdrawn')", name="ck_packet_lines_request_state"),
        CheckConstraint(
            "request_state <> 'withdrawn' OR (response_status = 'withdrawn' AND approved_cents = 0)", name="ck_packet_lines_withdrawn"
        ),
        CheckConstraint(
            "response_status IN ('no_response','approved_full','approved_partial','denied','withdrawn','preapproved')",
            name="ck_packet_lines_response",
        ),
        CheckConstraint("response_status <> 'approved_full' OR approved_cents = requested_cents", name="ck_packet_lines_full"),
        CheckConstraint("response_status <> 'approved_partial' OR approved_cents > 0", name="ck_packet_lines_partial"),
        CheckConstraint(
            "approved_cents IS NULL OR approved_cents <= requested_cents OR override_reason IS NOT NULL", name="ck_packet_lines_cap"
        ),
        CheckConstraint("response_status NOT IN ('denied','withdrawn','preapproved') OR approved_cents = 0", name="ck_packet_lines_zero"),
        CheckConstraint("approved_cents IS NULL OR approved_cents >= 0", name="ck_packet_lines_nonneg"),
        UniqueConstraint("tenant_id", "id", name="uq_packet_lines_tenant_id"),
        UniqueConstraint("packet_id", "supplement_line_id", name="uq_packet_lines_line"),
        ForeignKeyConstraint(["tenant_id", "packet_id"], ["packets.tenant_id", "packets.id"], name="fk_packet_lines_packet"),
        ForeignKeyConstraint(
            ["tenant_id", "supplement_line_id"], ["supplement_lines.tenant_id", "supplement_lines.id"], name="fk_packet_lines_line"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "carried_from_packet_line_id"], ["packet_lines.tenant_id", "packet_lines.id"], name="fk_packet_lines_carried"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "response_document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_packet_lines_response_doc",
        ),
        Index("ix_packet_lines_packet", "tenant_id", "packet_id", "line_no"),
    )


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    packet_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    remittance_document_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    over_approved_reason: Mapped[str | None] = mapped_column(Text)
    payer: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    reverses_payment_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    recorded_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("kind IN ('supplement','supplement_repayment','original_estimate','deductible','other')", name="ck_payments_kind"),
        CheckConstraint("payer IN ('insurer','customer','other')", name="ck_payments_payer"),
        CheckConstraint("kind NOT IN ('supplement','supplement_repayment') OR packet_id IS NOT NULL", name="ck_payments_packet"),
        CheckConstraint(
            "amount_cents <> 0 AND (amount_cents > 0 OR reverses_payment_id IS NOT NULL OR kind = 'supplement_repayment')",
            name="ck_payments_amount",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_payments_tenant_id"),
        UniqueConstraint("reverses_payment_id", name="uq_payments_reverses"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_payments_ro"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "packet_id"], ["packets.tenant_id", "packets.ro_id", "packets.id"], name="fk_payments_packet"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "remittance_document_id"],
            ["documents.tenant_id", "documents.ro_id", "documents.id"],
            name="fk_payments_remittance",
        ),
        ForeignKeyConstraint(["tenant_id", "reverses_payment_id"], ["payments.tenant_id", "payments.id"], name="fk_payments_reverses"),
        Index("ix_payments_ro_kind", "tenant_id", "ro_id", "kind"),
    )


class BaselineRo(Base):
    __tablename__ = "baseline_ros"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    location_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    ro_label: Mapped[str] = mapped_column(Text, nullable=False)
    closed_month: Mapped[date] = mapped_column(Date, nullable=False)
    insurer_name: Mapped[str | None] = mapped_column(Text)
    requested_cents: Mapped[int | None] = mapped_column(BigInteger)
    approved_cents: Mapped[int | None] = mapped_column(BigInteger)
    collected_cents: Mapped[int | None] = mapped_column(BigInteger)
    first_request_on: Mapped[date | None] = mapped_column(Date)
    approved_on: Mapped[date | None] = mapped_column(Date)
    collected_on: Mapped[date | None] = mapped_column(Date)
    source_note: Mapped[str] = mapped_column(Text, nullable=False)
    entered_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("requested_cents >= 0", name="ck_baseline_requested"),
        CheckConstraint("approved_cents >= 0", name="ck_baseline_approved"),
        CheckConstraint("collected_cents >= 0", name="ck_baseline_collected"),
        UniqueConstraint("tenant_id", "location_id", "ro_label", name="uq_baseline_ros_label"),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"], name="fk_baseline_ros_location"),
    )


class Pilot(Base):
    __tablename__ = "pilots"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    location_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="14900")
    threshold_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="100000")
    min_packets: Mapped[int] = mapped_column(Integer, nullable=False, server_default="8")
    min_baseline: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    min_response_share: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, server_default="0.80")
    terms_version: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_from: Mapped[date | None] = mapped_column(Date)
    baseline_to: Mapped[date | None] = mapped_column(Date)
    baseline_insurer_ro_count: Mapped[int | None] = mapped_column(Integer)
    baseline_supplemented_ro_count: Mapped[int | None] = mapped_column(Integer)
    window_insurer_ro_count: Mapped[int | None] = mapped_column(Integer)
    counts_source_note: Mapped[str | None] = mapped_column(Text)
    baseline_counts_supplied_at: Mapped[datetime | None] = mapped_column(TS)
    vendor_late_drafts_recorded_at: Mapped[datetime | None] = mapped_column(TS)
    vendor_late_drafts_recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    paid_on: Mapped[date | None] = mapped_column(Date)
    refund_state: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(TS)
    decided_by: Mapped[uuid.UUID | None] = _user_fk()
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint("refund_state IN ('not_due','due','paid')", name="ck_pilots_refund"),
        UniqueConstraint("tenant_id", "id", name="uq_pilots_tenant_id"),
        UniqueConstraint("tenant_id", "location_id", "start_date", name="uq_pilots_start"),
        ForeignKeyConstraint(["tenant_id", "location_id"], ["locations.tenant_id", "locations.id"], name="fk_pilots_location"),
    )


class PilotCountEvent(Base):
    """Append-only history of every change to a pilot count (B1-003 fix round 2)."""

    __tablename__ = "pilot_count_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = _tenant()
    pilot_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    recorded_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    __table_args__ = (
        CheckConstraint(
            "field IN ('baseline_insurer_ro_count','baseline_supplemented_ro_count','window_insurer_ro_count')",
            name="ck_pilot_count_events_field",
        ),
        CheckConstraint("value IS NULL OR value >= 0", name="ck_pilot_count_events_value"),
        ForeignKeyConstraint(["tenant_id", "pilot_id"], ["pilots.tenant_id", "pilots.id"], name="fk_pilot_count_events_pilot"),
        Index("ix_pilot_count_events_pilot", "tenant_id", "pilot_id", "field", "recorded_at"),
    )


class VendorLateDraft(Base):
    """A draft the vendor returned later than 1 business day; auditable and visible to the shop."""

    __tablename__ = "vendor_late_drafts"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    pilot_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    ro_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)  # one late draft per repair order (B1-003 round 3)
    packet_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)  # the packet frozen from the draft, if any
    draft_reference: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(TS, nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(TS)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    recorded_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    __table_args__ = (
        CheckConstraint("length(draft_reference) BETWEEN 1 AND 100", name="ck_vendor_late_drafts_ref"),
        CheckConstraint("note IS NULL OR length(note) <= 300", name="ck_vendor_late_drafts_note"),
        CheckConstraint("returned_at IS NULL OR returned_at >= requested_at", name="ck_vendor_late_drafts_order"),
        UniqueConstraint("tenant_id", "pilot_id", "draft_reference", name="uq_vendor_late_drafts_ref"),
        ForeignKeyConstraint(["tenant_id", "pilot_id"], ["pilots.tenant_id", "pilots.id"], name="fk_vendor_late_drafts_pilot"),
        UniqueConstraint("tenant_id", "pilot_id", "ro_id", name="uq_vendor_late_drafts_ro"),
        ForeignKeyConstraint(["tenant_id", "ro_id"], ["repair_orders.tenant_id", "repair_orders.id"], name="fk_vendor_late_drafts_ro"),
        ForeignKeyConstraint(
            ["tenant_id", "ro_id", "packet_id"], ["packets.tenant_id", "packets.ro_id", "packets.id"], name="fk_vendor_late_drafts_packet"
        ),
    )


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    locked_until: Mapped[datetime | None] = mapped_column(TS)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    result: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("state IN ('queued','running','succeeded','failed','partial')", name="ck_jobs_state"),
        UniqueConstraint("tenant_id", "kind", "idempotency_key", name="uq_jobs_idempotency"),
        Index("ix_jobs_claim", "state", "locked_until", "created_at", postgresql_where=text("state IN ('queued','running')")),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = _tenant()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUIDT, nullable=False)
    before: Mapped[Any | None] = mapped_column(JSONB)
    after: Mapped[Any | None] = mapped_column(JSONB)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUIDT)
    at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("actor_kind IN ('user','operator','worker','system')", name="ck_audit_actor"),
        Index("ix_audit_events_entity", "tenant_id", "entity_type", "entity_id", "at"),
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    request_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_idempotency_key"),)


TENANT_TABLES = tuple(sorted(t.name for t in Base.metadata.sorted_tables if "tenant_id" in t.c and t.name != "sessions"))
