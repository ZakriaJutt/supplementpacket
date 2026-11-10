"""B1 core schema: tenancy, ROs, documents, lines, evidence, packets, ledger, pilot, jobs, audit.

Revision ID: 20261111_0001
Revises:
Create Date: 2026-11-11

T-2.2.1, T-2.2.4. Row-level security on every tenant-owned table, FORCE ROW LEVEL
SECURITY, composite foreign keys repeating tenant_id, append-only audit events, the
approval reset rule as triggers, packet and payment immutability as triggers.
"""

from __future__ import annotations

from alembic import op

revision = "20261111_0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "supplementpacket_app"

TENANT_TABLES = (
    "locations",
    "memberships",
    "operator_grants",
    "insurers",
    "repair_orders",
    "documents",
    "parse_runs",
    "estimate_lines",
    "diff_runs",
    "supplement_lines",
    "photos",
    "reference_citations",
    "line_evidence",
    "packets",
    "packet_lines",
    "payments",
    "baseline_ros",
    "pilots",
    "jobs",
    "audit_events",
    "idempotency_records",
)

DDL = r"""
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE FUNCTION sp_current_tenant() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;
CREATE FUNCTION sp_current_user() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;
CREATE FUNCTION sp_actor_role() RETURNS text LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.actor_role', true), '') $$;
CREATE FUNCTION sp_correlation_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.correlation_id', true), '')::uuid $$;

-- Identity and tenancy -------------------------------------------------------
CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CONSTRAINT ck_tenants_status CHECK (status IN ('active','read_only','deleting')),
    timezone text NOT NULL DEFAULT 'America/Los_Angeles',
    retention_days integer NOT NULL DEFAULT 90 CONSTRAINT ck_tenants_retention CHECK (retention_days BETWEEN 30 AND 730),
    ai_consent_at timestamptz,
    ai_consent_by uuid,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email citext NOT NULL CONSTRAINT uq_users_email UNIQUE,
    password_hash text NOT NULL,
    totp_secret_enc bytea,
    totp_enabled_at timestamptz,
    is_operator boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE locations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    city text,
    state char(2) NOT NULL DEFAULT 'WA',
    CONSTRAINT uq_locations_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_locations_name UNIQUE (tenant_id, name)
);

CREATE TABLE memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id uuid NOT NULL REFERENCES users(id),
    role text NOT NULL CONSTRAINT ck_memberships_role CHECK (role IN ('owner','estimator','office')),
    CONSTRAINT uq_memberships_user UNIQUE (tenant_id, user_id)
);

CREATE TABLE operator_grants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    operator_user_id uuid NOT NULL REFERENCES users(id),
    granted_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CONSTRAINT ck_operator_grants_30d CHECK (expires_at <= created_at + interval '30 days')
);

CREATE TABLE sessions (
    id bytea PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    tenant_id uuid REFERENCES tenants(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

-- Repair orders and source documents -----------------------------------------
CREATE TABLE insurers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    CONSTRAINT uq_insurers_tenant_id UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX uq_insurers_name ON insurers (tenant_id, lower(name));

CREATE TABLE repair_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    location_id uuid NOT NULL,
    ro_number text NOT NULL,
    insurer_id uuid,
    claim_number text,
    adjuster_name text,
    adjuster_email citext,
    vin text CONSTRAINT ck_repair_orders_vin CHECK (vin IS NULL OR length(vin) = 17),
    vehicle_desc text,
    email_free_paragraph text,
    status text NOT NULL DEFAULT 'open' CONSTRAINT ck_repair_orders_status CHECK (status IN ('open','closed')),
    closed_at timestamptz,
    row_version integer NOT NULL DEFAULT 1,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_repair_orders_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_repair_orders_number UNIQUE (tenant_id, location_id, ro_number),
    CONSTRAINT fk_repair_orders_location FOREIGN KEY (tenant_id, location_id) REFERENCES locations (tenant_id, id),
    CONSTRAINT fk_repair_orders_insurer FOREIGN KEY (tenant_id, insurer_id) REFERENCES insurers (tenant_id, id)
);
CREATE INDEX ix_repair_orders_list ON repair_orders (tenant_id, status, created_at DESC);
CREATE INDEX ix_repair_orders_insurer ON repair_orders (tenant_id, insurer_id);

CREATE TABLE documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    packet_id uuid,
    purpose text NOT NULL CONSTRAINT ck_documents_purpose CHECK (purpose IN ('insurer_estimate','shop_estimate','response','remittance')),
    version integer NOT NULL,
    source_system text NOT NULL DEFAULT 'unknown' CONSTRAINT ck_documents_source CHECK (source_system IN ('ccc_one','mitchell','audatex','unknown')),
    content_type text NOT NULL,
    storage_key text,
    sha256 bytea NOT NULL,
    size_bytes integer NOT NULL CONSTRAINT ck_documents_size CHECK (size_bytes > 0 AND size_bytes <= 26214400),
    page_count integer,
    uploaded_by uuid NOT NULL REFERENCES users(id),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    purged_at timestamptz,
    CONSTRAINT ck_documents_packet CHECK (purpose NOT IN ('response','remittance') OR packet_id IS NOT NULL),
    CONSTRAINT uq_documents_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_documents_ro_id UNIQUE (tenant_id, ro_id, id),
    CONSTRAINT uq_documents_packet_id UNIQUE (tenant_id, packet_id, id),
    CONSTRAINT uq_documents_version UNIQUE (tenant_id, ro_id, purpose, version),
    CONSTRAINT uq_documents_sha UNIQUE (tenant_id, ro_id, purpose, sha256),
    CONSTRAINT fk_documents_ro FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id)
);
CREATE INDEX ix_documents_latest ON documents (tenant_id, ro_id, purpose, version DESC);
CREATE INDEX ix_documents_retention ON documents (purged_at, uploaded_at) WHERE storage_key IS NOT NULL;

CREATE TABLE parse_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    document_id uuid NOT NULL,
    parser_name text NOT NULL,
    parser_version text NOT NULL,
    status text NOT NULL CONSTRAINT ck_parse_runs_status CHECK (status IN ('reconciled','unreconciled','failed','manual')),
    printed_total_cents bigint,
    parsed_total_cents bigint,
    confirm_reason text,
    confirmed_by uuid REFERENCES users(id),
    is_current boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_parse_runs_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_parse_runs_document FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id)
);
CREATE UNIQUE INDEX uq_parse_runs_current ON parse_runs (document_id) WHERE is_current;

CREATE TABLE estimate_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    parse_run_id uuid NOT NULL,
    line_no integer NOT NULL,
    page integer,
    section text,
    operation text NOT NULL CONSTRAINT ck_estimate_lines_operation CHECK (operation IN ('replace','repair','remove_install','refinish','blend','sublet','scan','calibrate','materials','other')),
    description text NOT NULL,
    part_number text,
    part_type text CONSTRAINT ck_estimate_lines_part_type CHECK (part_type IN ('oem','aftermarket','recycled','remanufactured')),
    part_price_cents bigint,
    labor_hours numeric(6,2),
    labor_type text,
    labor_rate_cents bigint,
    line_total_cents bigint NOT NULL,
    source text NOT NULL DEFAULT 'parser' CONSTRAINT ck_estimate_lines_source CHECK (source IN ('parser','manual','ai_suggested')),
    edited_by uuid REFERENCES users(id),
    row_version integer NOT NULL DEFAULT 1,
    CONSTRAINT uq_estimate_lines_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_estimate_lines_line_no UNIQUE (parse_run_id, line_no),
    CONSTRAINT fk_estimate_lines_run FOREIGN KEY (tenant_id, parse_run_id) REFERENCES parse_runs (tenant_id, id)
);
CREATE INDEX ix_estimate_lines_review ON estimate_lines (tenant_id, parse_run_id, line_no);

-- Lines, evidence and checklist -------------------------------------------------
CREATE TABLE diff_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    insurer_document_id uuid NOT NULL,
    shop_document_id uuid NOT NULL,
    engine_version text NOT NULL,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_diff_runs_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_diff_runs_ro_id UNIQUE (tenant_id, ro_id, id),
    CONSTRAINT uq_diff_runs_inputs UNIQUE (tenant_id, insurer_document_id, shop_document_id, engine_version),
    CONSTRAINT fk_diff_runs_ro FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id),
    CONSTRAINT fk_diff_runs_insurer_doc FOREIGN KEY (tenant_id, ro_id, insurer_document_id) REFERENCES documents (tenant_id, ro_id, id),
    CONSTRAINT fk_diff_runs_shop_doc FOREIGN KEY (tenant_id, ro_id, shop_document_id) REFERENCES documents (tenant_id, ro_id, id)
);

CREATE TABLE checklist_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version integer NOT NULL CONSTRAINT uq_checklist_versions_version UNIQUE,
    published_at timestamptz NOT NULL DEFAULT now(),
    author text NOT NULL
);

CREATE TABLE checklist_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    checklist_version_id uuid NOT NULL REFERENCES checklist_versions(id),
    repair_type text NOT NULL,
    operation_name text NOT NULL,
    prompt text NOT NULL
);

CREATE TABLE supplement_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    diff_run_id uuid,
    diff_key text,
    origin text NOT NULL CONSTRAINT ck_supplement_lines_origin CHECK (origin IN ('diff','checklist','manual','ai_suggested')),
    category text NOT NULL CONSTRAINT ck_supplement_lines_category CHECK (category IN ('missing_operation','labor_hours_gap','refinish_hours_gap','part_price_gap','part_type_difference','rate_difference','materials_gap','other')),
    shop_line_id uuid,
    insurer_line_id uuid,
    checklist_item_id uuid REFERENCES checklist_items(id),
    match_state text NOT NULL DEFAULT 'matched' CONSTRAINT ck_supplement_lines_match CHECK (match_state IN ('matched','needs_review','not_applicable')),
    description text NOT NULL,
    requested_cents bigint NOT NULL CONSTRAINT ck_supplement_lines_requested CHECK (requested_cents >= 0),
    hours_delta numeric(6,2),
    explanation text,
    status text NOT NULL DEFAULT 'draft' CONSTRAINT ck_supplement_lines_status CHECK (status IN ('draft','approved','excluded')),
    approved_by uuid REFERENCES users(id),
    approved_at timestamptz,
    approved_row_version integer,
    approved_fingerprint bytea,
    row_version integer NOT NULL DEFAULT 1,
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_supplement_lines_approved CHECK (
        status <> 'approved' OR (
            approved_by IS NOT NULL AND approved_at IS NOT NULL AND approved_fingerprint IS NOT NULL
            AND approved_row_version = row_version AND match_state <> 'needs_review'
        )
    ),
    CONSTRAINT ck_supplement_lines_checklist CHECK (origin <> 'checklist' OR checklist_item_id IS NOT NULL),
    CONSTRAINT ck_supplement_lines_diff CHECK (origin <> 'diff' OR diff_run_id IS NOT NULL),
    CONSTRAINT uq_supplement_lines_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_supplement_lines_ro_id UNIQUE (tenant_id, ro_id, id),
    CONSTRAINT fk_supplement_lines_ro FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id),
    CONSTRAINT fk_supplement_lines_diff FOREIGN KEY (tenant_id, ro_id, diff_run_id) REFERENCES diff_runs (tenant_id, ro_id, id),
    CONSTRAINT fk_supplement_lines_shop_line FOREIGN KEY (tenant_id, shop_line_id) REFERENCES estimate_lines (tenant_id, id),
    CONSTRAINT fk_supplement_lines_insurer_line FOREIGN KEY (tenant_id, insurer_line_id) REFERENCES estimate_lines (tenant_id, id)
);
CREATE INDEX ix_supplement_lines_status ON supplement_lines (tenant_id, ro_id, status);
CREATE INDEX ix_supplement_lines_needs_review ON supplement_lines (tenant_id, ro_id) WHERE match_state = 'needs_review';
CREATE UNIQUE INDEX uq_supplement_lines_diff_key ON supplement_lines (tenant_id, ro_id, diff_key) WHERE diff_key IS NOT NULL;

CREATE TABLE photos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    storage_key text,
    sha256 bytea NOT NULL,
    content_type text NOT NULL,
    width integer,
    height integer,
    taken_by_shop boolean NOT NULL,
    not_licensed_copy_attested boolean NOT NULL CONSTRAINT ck_photos_attested CHECK (not_licensed_copy_attested),
    attested_by uuid NOT NULL REFERENCES users(id),
    attested_at timestamptz NOT NULL,
    attestation_note text,
    uploaded_by uuid NOT NULL REFERENCES users(id),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    purged_at timestamptz,
    row_version integer NOT NULL DEFAULT 1,
    CONSTRAINT ck_photos_note CHECK (taken_by_shop OR attestation_note IS NOT NULL),
    CONSTRAINT uq_photos_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_photos_ro_id UNIQUE (tenant_id, ro_id, id),
    CONSTRAINT uq_photos_sha UNIQUE (tenant_id, ro_id, sha256),
    CONSTRAINT fk_photos_ro FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id)
);

CREATE TABLE reference_citations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    material_type text NOT NULL CONSTRAINT ck_reference_citations_type CHECK (material_type IN ('oem_procedure_subscription','oem_position_statement','estimating_guide','industry_body','other')),
    publisher text NOT NULL,
    title text NOT NULL,
    identifier text,
    url text,
    accessed_on date NOT NULL,
    note text CONSTRAINT ck_reference_citations_note CHECK (note IS NULL OR length(note) <= 300),
    row_version integer NOT NULL DEFAULT 1,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_reference_citations_url CHECK (
        url IS NULL OR (url LIKE 'https://%' AND material_type NOT IN ('oem_procedure_subscription','estimating_guide'))
    ),
    CONSTRAINT uq_reference_citations_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE line_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    supplement_line_id uuid NOT NULL,
    photo_id uuid,
    reference_id uuid,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_line_evidence_one CHECK (num_nonnulls(photo_id, reference_id) = 1),
    CONSTRAINT uq_line_evidence_photo UNIQUE (supplement_line_id, photo_id),
    CONSTRAINT uq_line_evidence_reference UNIQUE (supplement_line_id, reference_id),
    CONSTRAINT fk_line_evidence_line FOREIGN KEY (tenant_id, ro_id, supplement_line_id) REFERENCES supplement_lines (tenant_id, ro_id, id),
    CONSTRAINT fk_line_evidence_photo FOREIGN KEY (tenant_id, ro_id, photo_id) REFERENCES photos (tenant_id, ro_id, id),
    CONSTRAINT fk_line_evidence_reference FOREIGN KEY (tenant_id, reference_id) REFERENCES reference_citations (tenant_id, id)
);

-- Packets and ledger -------------------------------------------------------------
CREATE TABLE packets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    version integer NOT NULL,
    status text NOT NULL DEFAULT 'frozen' CONSTRAINT ck_packets_status CHECK (status IN ('frozen','sent','superseded')),
    review_fingerprint bytea NOT NULL,
    supersedes_packet_id uuid,
    requested_total_cents bigint NOT NULL,
    line_count integer NOT NULL CONSTRAINT ck_packets_line_count CHECK (line_count > 0),
    email_draft text NOT NULL,
    frozen_by uuid NOT NULL REFERENCES users(id),
    frozen_at timestamptz NOT NULL DEFAULT now(),
    pdf_storage_key text,
    pdf_sha256 bytea,
    sent_on date,
    sent_channel text CONSTRAINT ck_packets_channel CHECK (sent_channel IN ('email','insurer_portal','estimating_system','in_person','other')),
    sent_marked_by uuid REFERENCES users(id),
    sent_marked_at timestamptz,
    correction_note text,
    purged_at timestamptz,
    purge_reason text,
    purged_by uuid REFERENCES users(id),
    row_version integer NOT NULL DEFAULT 1,
    CONSTRAINT ck_packets_sent CHECK (status <> 'sent' OR (sent_on IS NOT NULL AND sent_channel IS NOT NULL AND sent_marked_by IS NOT NULL)),
    CONSTRAINT uq_packets_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_packets_ro_id UNIQUE (tenant_id, ro_id, id),
    CONSTRAINT uq_packets_version UNIQUE (tenant_id, ro_id, version),
    CONSTRAINT fk_packets_ro FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id),
    CONSTRAINT fk_packets_supersedes FOREIGN KEY (tenant_id, ro_id, supersedes_packet_id) REFERENCES packets (tenant_id, ro_id, id)
);
CREATE UNIQUE INDEX uq_packets_one_live ON packets (tenant_id, ro_id) WHERE status IN ('frozen','sent');
CREATE INDEX ix_packets_sent ON packets (tenant_id, sent_on) WHERE status = 'sent';

ALTER TABLE documents ADD CONSTRAINT fk_documents_packet FOREIGN KEY (tenant_id, ro_id, packet_id) REFERENCES packets (tenant_id, ro_id, id);

CREATE TABLE packet_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    packet_id uuid NOT NULL,
    supplement_line_id uuid NOT NULL,
    line_no integer NOT NULL,
    origin text NOT NULL,
    category text NOT NULL,
    description text NOT NULL,
    requested_cents bigint NOT NULL,
    evidence_snapshot jsonb NOT NULL,
    approved_by uuid NOT NULL REFERENCES users(id),
    approved_at timestamptz NOT NULL,
    approved_fingerprint bytea NOT NULL,
    carried_from_packet_line_id uuid,
    response_status text NOT NULL DEFAULT 'no_response' CONSTRAINT ck_packet_lines_response CHECK (response_status IN ('no_response','approved_full','approved_partial','denied','withdrawn','preapproved')),
    approved_cents bigint,
    denial_reason text,
    response_date date,
    response_document_id uuid,
    override_reason text,
    response_recorded_by uuid REFERENCES users(id),
    row_version integer NOT NULL DEFAULT 1,
    CONSTRAINT ck_packet_lines_full CHECK (response_status <> 'approved_full' OR approved_cents = requested_cents),
    CONSTRAINT ck_packet_lines_partial CHECK (response_status <> 'approved_partial' OR approved_cents > 0),
    CONSTRAINT ck_packet_lines_cap CHECK (approved_cents IS NULL OR approved_cents <= requested_cents OR override_reason IS NOT NULL),
    CONSTRAINT ck_packet_lines_zero CHECK (response_status NOT IN ('denied','withdrawn','preapproved') OR approved_cents = 0),
    CONSTRAINT ck_packet_lines_nonneg CHECK (approved_cents IS NULL OR approved_cents >= 0),
    CONSTRAINT uq_packet_lines_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_packet_lines_line UNIQUE (packet_id, supplement_line_id),
    CONSTRAINT fk_packet_lines_packet FOREIGN KEY (tenant_id, packet_id) REFERENCES packets (tenant_id, id),
    CONSTRAINT fk_packet_lines_line FOREIGN KEY (tenant_id, supplement_line_id) REFERENCES supplement_lines (tenant_id, id),
    CONSTRAINT fk_packet_lines_carried FOREIGN KEY (tenant_id, carried_from_packet_line_id) REFERENCES packet_lines (tenant_id, id),
    CONSTRAINT fk_packet_lines_response_doc FOREIGN KEY (tenant_id, response_document_id) REFERENCES documents (tenant_id, id)
);
CREATE INDEX ix_packet_lines_packet ON packet_lines (tenant_id, packet_id, line_no);

CREATE TABLE payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    ro_id uuid NOT NULL,
    packet_id uuid,
    kind text NOT NULL CONSTRAINT ck_payments_kind CHECK (kind IN ('supplement','supplement_repayment','original_estimate','deductible','other')),
    remittance_document_id uuid,
    over_approved_reason text,
    payer text NOT NULL CONSTRAINT ck_payments_payer CHECK (payer IN ('insurer','customer','other')),
    amount_cents bigint NOT NULL,
    paid_on date NOT NULL,
    reference text,
    reverses_payment_id uuid,
    recorded_by uuid NOT NULL REFERENCES users(id),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_payments_packet CHECK (kind NOT IN ('supplement','supplement_repayment') OR packet_id IS NOT NULL),
    CONSTRAINT ck_payments_amount CHECK (amount_cents <> 0 AND (amount_cents > 0 OR reverses_payment_id IS NOT NULL OR kind = 'supplement_repayment')),
    CONSTRAINT uq_payments_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_payments_reverses UNIQUE (reverses_payment_id),
    CONSTRAINT fk_payments_ro FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id),
    CONSTRAINT fk_payments_packet FOREIGN KEY (tenant_id, ro_id, packet_id) REFERENCES packets (tenant_id, ro_id, id),
    CONSTRAINT fk_payments_remittance FOREIGN KEY (tenant_id, ro_id, remittance_document_id) REFERENCES documents (tenant_id, ro_id, id),
    CONSTRAINT fk_payments_reverses FOREIGN KEY (tenant_id, reverses_payment_id) REFERENCES payments (tenant_id, id)
);
CREATE INDEX ix_payments_ro_kind ON payments (tenant_id, ro_id, kind);

CREATE TABLE baseline_ros (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    location_id uuid NOT NULL,
    ro_label text NOT NULL,
    closed_month date NOT NULL,
    insurer_name text,
    requested_cents bigint CONSTRAINT ck_baseline_requested CHECK (requested_cents >= 0),
    approved_cents bigint CONSTRAINT ck_baseline_approved CHECK (approved_cents >= 0),
    collected_cents bigint CONSTRAINT ck_baseline_collected CHECK (collected_cents >= 0),
    first_request_on date,
    approved_on date,
    collected_on date,
    source_note text NOT NULL,
    entered_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_baseline_ros_label UNIQUE (tenant_id, location_id, ro_label),
    CONSTRAINT fk_baseline_ros_location FOREIGN KEY (tenant_id, location_id) REFERENCES locations (tenant_id, id)
);

CREATE TABLE pilots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    location_id uuid NOT NULL,
    start_date date NOT NULL,
    price_cents bigint NOT NULL DEFAULT 14900,
    threshold_cents bigint NOT NULL DEFAULT 100000,
    min_packets integer NOT NULL DEFAULT 8,
    min_baseline integer NOT NULL DEFAULT 10,
    min_response_share numeric(3,2) NOT NULL DEFAULT 0.80,
    terms_version text NOT NULL,
    baseline_from date,
    baseline_to date,
    baseline_insurer_ro_count integer,
    baseline_supplemented_ro_count integer,
    window_insurer_ro_count integer,
    counts_source_note text,
    created_by uuid NOT NULL REFERENCES users(id),
    paid_on date,
    refund_state text CONSTRAINT ck_pilots_refund CHECK (refund_state IN ('not_due','due','paid')),
    decided_at timestamptz,
    decided_by uuid REFERENCES users(id),
    row_version integer NOT NULL DEFAULT 1,
    CONSTRAINT uq_pilots_start UNIQUE (tenant_id, location_id, start_date),
    CONSTRAINT fk_pilots_location FOREIGN KEY (tenant_id, location_id) REFERENCES locations (tenant_id, id)
);

-- Operations ------------------------------------------------------------------------
CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    kind text NOT NULL,
    subject_id uuid NOT NULL,
    state text NOT NULL DEFAULT 'queued' CONSTRAINT ck_jobs_state CHECK (state IN ('queued','running','succeeded','failed','partial')),
    state_version integer NOT NULL DEFAULT 0,
    attempt integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 3,
    locked_until timestamptz,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    error_code text,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_jobs_idempotency UNIQUE (tenant_id, kind, idempotency_key)
);
CREATE INDEX ix_jobs_claim ON jobs (state, locked_until, created_at) WHERE state IN ('queued','running');

CREATE TABLE audit_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    actor_user_id uuid,
    actor_kind text NOT NULL CONSTRAINT ck_audit_actor CHECK (actor_kind IN ('user','operator','worker','system')),
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    before jsonb,
    after jsonb,
    correlation_id uuid,
    at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_events_entity ON audit_events (tenant_id, entity_type, entity_id, at);

CREATE TABLE idempotency_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    key text NOT NULL,
    method text NOT NULL,
    path text NOT NULL,
    request_sha256 bytea NOT NULL,
    status_code integer NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_idempotency_key UNIQUE (tenant_id, key)
);
"""

FUNCTIONS = r"""
CREATE FUNCTION sp_actor_kind() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT CASE sp_actor_role() WHEN 'operator' THEN 'operator' WHEN 'worker' THEN 'worker'
         WHEN 'owner' THEN 'user' WHEN 'estimator' THEN 'user' WHEN 'office' THEN 'user' ELSE 'system' END
$$;

CREATE FUNCTION sp_audit(p_tenant uuid, p_action text, p_entity_type text, p_entity_id uuid, p_before jsonb, p_after jsonb)
RETURNS void LANGUAGE sql AS $$
  INSERT INTO audit_events (tenant_id, actor_user_id, actor_kind, action, entity_type, entity_id, before, after, correlation_id)
  VALUES (p_tenant, sp_current_user(), sp_actor_kind(), p_action, p_entity_type, p_entity_id, p_before, p_after, sp_correlation_id())
$$;

-- Audit events are insert-only (IT-16).
CREATE FUNCTION sp_audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only' USING ERRCODE = 'insufficient_privilege';
END $$;
CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION sp_audit_append_only();
CREATE TRIGGER trg_audit_no_truncate BEFORE TRUNCATE ON audit_events
  FOR EACH STATEMENT EXECUTE FUNCTION sp_audit_append_only();

-- Approval reset rule (schema 3, MH-06, UT-07). One function; triggers call it.
CREATE FUNCTION sp_reset_line(p_line uuid, p_reason text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  PERFORM set_config('sp.reset_reason', p_reason, true);
  UPDATE supplement_lines SET row_version = row_version + 1 WHERE id = p_line;
  PERFORM set_config('sp.reset_reason', '', true);
END $$;

CREATE FUNCTION sp_supplement_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  content_changed boolean;
BEGIN
  IF NEW.tenant_id <> OLD.tenant_id OR NEW.ro_id <> OLD.ro_id OR NEW.origin <> OLD.origin THEN
    RAISE EXCEPTION 'supplement line identity cannot change';
  END IF;
  content_changed := (NEW.category, NEW.description, NEW.requested_cents, NEW.hours_delta, NEW.explanation,
                      NEW.match_state, NEW.shop_line_id, NEW.insurer_line_id, NEW.checklist_item_id, NEW.diff_run_id)
                     IS DISTINCT FROM
                     (OLD.category, OLD.description, OLD.requested_cents, OLD.hours_delta, OLD.explanation,
                      OLD.match_state, OLD.shop_line_id, OLD.insurer_line_id, OLD.checklist_item_id, OLD.diff_run_id);
  IF content_changed AND NEW.row_version = OLD.row_version THEN
    NEW.row_version := OLD.row_version + 1;
  END IF;
  IF NEW.row_version <> OLD.row_version THEN
    -- Any change returns the line to draft; approval and exclusion are cleared.
    NEW.status := 'draft';
    NEW.approved_by := NULL;
    NEW.approved_at := NULL;
    NEW.approved_row_version := NULL;
    NEW.approved_fingerprint := NULL;
    IF OLD.status = 'approved' THEN
      PERFORM sp_audit(NEW.tenant_id, 'line.approval_reset', 'supplement_line', NEW.id,
        jsonb_build_object('status', OLD.status, 'row_version', OLD.row_version),
        jsonb_build_object('status', NEW.status, 'row_version', NEW.row_version,
          'reason', coalesce(nullif(current_setting('sp.reset_reason', true), ''), 'line changed')));
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.status = 'approved' AND OLD.status <> 'approved' THEN
    IF sp_actor_role() IS NULL OR sp_actor_role() NOT IN ('owner','estimator') THEN
      RAISE EXCEPTION 'only an Owner or Estimator can approve a line' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.approved_by IS DISTINCT FROM sp_current_user() THEN
      RAISE EXCEPTION 'approved_by must be the acting user' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  IF NEW.status = 'excluded' AND OLD.status <> 'excluded'
     AND (sp_actor_role() IS NULL OR sp_actor_role() NOT IN ('owner','estimator')) THEN
    RAISE EXCEPTION 'only an Owner or Estimator can exclude a line' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.status = 'approved' AND OLD.status = 'approved'
     AND (NEW.approved_by, NEW.approved_at, NEW.approved_fingerprint, NEW.approved_row_version)
         IS DISTINCT FROM (OLD.approved_by, OLD.approved_at, OLD.approved_fingerprint, OLD.approved_row_version) THEN
    RAISE EXCEPTION 'an approval cannot be rewritten; reset the line first';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_supplement_lines_guard BEFORE UPDATE ON supplement_lines
  FOR EACH ROW EXECUTE FUNCTION sp_supplement_lines_guard();

CREATE FUNCTION sp_supplement_lines_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status <> 'draft' THEN
    RAISE EXCEPTION 'a new line starts as draft; nothing is auto-approved';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_supplement_lines_insert_guard BEFORE INSERT ON supplement_lines
  FOR EACH ROW EXECUTE FUNCTION sp_supplement_lines_insert_guard();

CREATE FUNCTION sp_line_evidence_reset() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    PERFORM sp_reset_line(NEW.supplement_line_id, 'evidence added');
    RETURN NEW;
  ELSIF TG_OP = 'DELETE' THEN
    PERFORM sp_reset_line(OLD.supplement_line_id, 'evidence removed');
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'line evidence is replaced by delete and insert, never updated';
END $$;
CREATE TRIGGER trg_line_evidence_reset AFTER INSERT OR DELETE ON line_evidence
  FOR EACH ROW EXECUTE FUNCTION sp_line_evidence_reset();
CREATE TRIGGER trg_line_evidence_no_update BEFORE UPDATE ON line_evidence
  FOR EACH ROW EXECUTE FUNCTION sp_line_evidence_reset();

CREATE FUNCTION sp_photos_reset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  IF (NEW.sha256, NEW.storage_key, NEW.taken_by_shop, NEW.not_licensed_copy_attested, NEW.attestation_note, NEW.ro_id)
     IS DISTINCT FROM (OLD.sha256, OLD.storage_key, OLD.taken_by_shop, OLD.not_licensed_copy_attested, OLD.attestation_note, OLD.ro_id) THEN
    FOR r IN SELECT DISTINCT supplement_line_id FROM line_evidence WHERE photo_id = NEW.id LOOP
      PERFORM sp_reset_line(r.supplement_line_id, 'photo or attestation changed');
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_photos_reset AFTER UPDATE ON photos FOR EACH ROW EXECUTE FUNCTION sp_photos_reset();

CREATE FUNCTION sp_references_reset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  IF (NEW.material_type, NEW.publisher, NEW.title, NEW.identifier, NEW.url, NEW.accessed_on, NEW.note)
     IS DISTINCT FROM (OLD.material_type, OLD.publisher, OLD.title, OLD.identifier, OLD.url, OLD.accessed_on, OLD.note) THEN
    FOR r IN SELECT DISTINCT supplement_line_id FROM line_evidence WHERE reference_id = NEW.id LOOP
      PERFORM sp_reset_line(r.supplement_line_id, 'reference changed');
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_references_reset AFTER UPDATE ON reference_citations FOR EACH ROW EXECUTE FUNCTION sp_references_reset();

CREATE FUNCTION sp_estimate_lines_reset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  IF (NEW.operation, NEW.description, NEW.part_number, NEW.part_type, NEW.part_price_cents, NEW.labor_hours,
      NEW.labor_type, NEW.labor_rate_cents, NEW.line_total_cents)
     IS DISTINCT FROM (OLD.operation, OLD.description, OLD.part_number, OLD.part_type, OLD.part_price_cents, OLD.labor_hours,
      OLD.labor_type, OLD.labor_rate_cents, OLD.line_total_cents) THEN
    FOR r IN SELECT id FROM supplement_lines WHERE shop_line_id = NEW.id OR insurer_line_id = NEW.id LOOP
      PERFORM sp_reset_line(r.id, 'linked source estimate line corrected');
    END LOOP;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_estimate_lines_reset AFTER UPDATE ON estimate_lines FOR EACH ROW EXECUTE FUNCTION sp_estimate_lines_reset();

-- Frozen packets never change except by a licensed-content takedown (MH-06, MH-11).
CREATE FUNCTION sp_packets_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'packets are never deleted';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF sp_actor_role() IS NULL OR sp_actor_role() NOT IN ('owner','estimator') OR NEW.frozen_by IS DISTINCT FROM sp_current_user() THEN
      RAISE EXCEPTION 'only an Owner or Estimator can freeze a packet' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status <> 'frozen' THEN
      RAISE EXCEPTION 'a packet is created frozen';
    END IF;
    RETURN NEW;
  END IF;
  IF (NEW.tenant_id, NEW.ro_id, NEW.version, NEW.review_fingerprint, NEW.supersedes_packet_id, NEW.requested_total_cents,
      NEW.line_count, NEW.frozen_by, NEW.frozen_at)
     IS DISTINCT FROM (OLD.tenant_id, OLD.ro_id, OLD.version, OLD.review_fingerprint, OLD.supersedes_packet_id,
      OLD.requested_total_cents, OLD.line_count, OLD.frozen_by, OLD.frozen_at) THEN
    RAISE EXCEPTION 'a frozen packet cannot change';
  END IF;
  IF NEW.email_draft IS DISTINCT FROM OLD.email_draft AND NOT (NEW.email_draft = '[redacted]' AND NEW.purged_at IS NOT NULL) THEN
    RAISE EXCEPTION 'a frozen packet email draft cannot change except by takedown';
  END IF;
  IF OLD.pdf_sha256 IS NOT NULL AND NEW.pdf_sha256 IS DISTINCT FROM OLD.pdf_sha256 THEN
    RAISE EXCEPTION 'the packet PDF hash is stored at first success and never replaced';
  END IF;
  IF OLD.status = 'superseded' AND NEW.status <> 'superseded' THEN
    RAISE EXCEPTION 'a superseded packet stays superseded';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status AND NEW.status IN ('sent','frozen') AND OLD.status IN ('sent','frozen')
     AND (sp_actor_role() IS NULL OR sp_actor_role() NOT IN ('owner','estimator')) THEN
    RAISE EXCEPTION 'only an Owner or Estimator can mark or unmark sent' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_packets_guard BEFORE INSERT OR UPDATE OR DELETE ON packets FOR EACH ROW EXECUTE FUNCTION sp_packets_guard();

CREATE FUNCTION sp_packet_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE purged timestamptz;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'packet lines are never deleted';
  END IF;
  IF (NEW.tenant_id, NEW.packet_id, NEW.supplement_line_id, NEW.line_no, NEW.origin, NEW.category, NEW.requested_cents,
      NEW.approved_by, NEW.approved_at, NEW.approved_fingerprint, NEW.carried_from_packet_line_id)
     IS DISTINCT FROM (OLD.tenant_id, OLD.packet_id, OLD.supplement_line_id, OLD.line_no, OLD.origin, OLD.category,
      OLD.requested_cents, OLD.approved_by, OLD.approved_at, OLD.approved_fingerprint, OLD.carried_from_packet_line_id) THEN
    RAISE EXCEPTION 'packet line snapshot is immutable';
  END IF;
  IF (NEW.description, NEW.evidence_snapshot) IS DISTINCT FROM (OLD.description, OLD.evidence_snapshot) THEN
    SELECT purged_at INTO purged FROM packets WHERE id = NEW.packet_id;
    IF purged IS NULL OR NEW.description <> '[redacted]' OR NEW.evidence_snapshot <> '{"redacted": true}'::jsonb THEN
      RAISE EXCEPTION 'packet line snapshot changes only by takedown redaction';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_packet_lines_guard BEFORE UPDATE OR DELETE ON packet_lines FOR EACH ROW EXECUTE FUNCTION sp_packet_lines_guard();

-- Payments are never edited; the one system change is re-attribution on supersede (MH-08).
CREATE FUNCTION sp_payments_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE successor_of uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'payments are never deleted; reverse a mistake';
  END IF;
  IF (NEW.tenant_id, NEW.ro_id, NEW.kind, NEW.remittance_document_id, NEW.over_approved_reason, NEW.payer, NEW.amount_cents,
      NEW.paid_on, NEW.reference, NEW.reverses_payment_id, NEW.recorded_by, NEW.recorded_at)
     IS DISTINCT FROM (OLD.tenant_id, OLD.ro_id, OLD.kind, OLD.remittance_document_id, OLD.over_approved_reason, OLD.payer,
      OLD.amount_cents, OLD.paid_on, OLD.reference, OLD.reverses_payment_id, OLD.recorded_by, OLD.recorded_at) THEN
    RAISE EXCEPTION 'payments are never edited; reverse a mistake';
  END IF;
  IF NEW.packet_id IS DISTINCT FROM OLD.packet_id THEN
    SELECT supersedes_packet_id INTO successor_of FROM packets WHERE id = NEW.packet_id;
    IF successor_of IS DISTINCT FROM OLD.packet_id THEN
      RAISE EXCEPTION 'a payment is re-attributed only to the packet that supersedes its packet';
    END IF;
    PERFORM sp_audit(NEW.tenant_id, 'payment.reattributed', 'payment', NEW.id,
      jsonb_build_object('packet_id', OLD.packet_id), jsonb_build_object('packet_id', NEW.packet_id));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_payments_guard BEFORE UPDATE OR DELETE ON payments FOR EACH ROW EXECUTE FUNCTION sp_payments_guard();

-- Worker claim and sweeper. They run before the tenant is known, so they are the only
-- SECURITY DEFINER functions; they return the tenant so the worker sets it (TRD 8.3).
CREATE FUNCTION sp_claim_job(p_kinds text[], p_lock_seconds integer)
RETURNS TABLE (job_id uuid, tenant_id uuid, kind text, subject_id uuid, state_version integer, attempt integer, correlation_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
  RETURN QUERY
  WITH next AS (
    SELECT j.id FROM jobs j
    WHERE j.state = 'queued' AND j.kind = ANY (p_kinds)
    ORDER BY j.created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE jobs j SET state = 'running', state_version = j.state_version + 1, attempt = j.attempt + 1,
         locked_until = now() + make_interval(secs => p_lock_seconds), updated_at = now()
  FROM next WHERE j.id = next.id
  RETURNING j.id, j.tenant_id, j.kind, j.subject_id, j.state_version, j.attempt, j.correlation_id;
END $$;

CREATE FUNCTION sp_sweep_jobs() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE n integer;
BEGIN
  UPDATE jobs SET state = CASE WHEN attempt >= max_attempts THEN 'failed' ELSE 'queued' END,
         error_code = CASE WHEN attempt >= max_attempts THEN 'lock_expired' ELSE error_code END,
         state_version = state_version + 1, locked_until = NULL, updated_at = now()
  WHERE state = 'running' AND locked_until < now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
"""


def _rls_sql() -> str:
    parts = ["ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;", "ALTER TABLE tenants FORCE ROW LEVEL SECURITY;"]
    parts.append("CREATE POLICY tenant_isolation ON tenants USING (id = sp_current_tenant()) WITH CHECK (id = sp_current_tenant());")
    for table in TENANT_TABLES:
        parts.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        parts.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        parts.append(
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = sp_current_tenant()) "
            f"WITH CHECK (tenant_id = sp_current_tenant());"
        )
    return "\n".join(parts)


def _grants_sql() -> str:
    r = APP_ROLE
    return f"""
GRANT USAGE ON SCHEMA public TO {r};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {r};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {r};
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM {r};
REVOKE DELETE, TRUNCATE ON packets, packet_lines, payments FROM {r};
REVOKE UPDATE ON line_evidence FROM {r};
REVOKE INSERT, UPDATE, DELETE ON users, checklist_versions, checklist_items, tenants FROM {r};
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON alembic_version FROM {r};
REVOKE ALL ON FUNCTION sp_claim_job(text[], integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION sp_sweep_jobs() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sp_claim_job(text[], integer) TO {r};
GRANT EXECUTE ON FUNCTION sp_sweep_jobs() TO {r};
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(FUNCTIONS)
    op.execute(_rls_sql())
    op.execute(_grants_sql())


def downgrade() -> None:
    tables = [
        "idempotency_records",
        "audit_events",
        "jobs",
        "pilots",
        "baseline_ros",
        "payments",
        "packet_lines",
        "packets",
        "line_evidence",
        "reference_citations",
        "photos",
        "supplement_lines",
        "checklist_items",
        "checklist_versions",
        "diff_runs",
        "estimate_lines",
        "parse_runs",
        "documents",
        "repair_orders",
        "insurers",
        "sessions",
        "operator_grants",
        "memberships",
        "locations",
        "users",
        "tenants",
    ]
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS fk_documents_packet;")
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
    for fn in (
        "sp_claim_job(text[], integer)",
        "sp_sweep_jobs()",
        "sp_payments_guard()",
        "sp_packet_lines_guard()",
        "sp_packets_guard()",
        "sp_estimate_lines_reset()",
        "sp_references_reset()",
        "sp_photos_reset()",
        "sp_line_evidence_reset()",
        "sp_supplement_lines_insert_guard()",
        "sp_supplement_lines_guard()",
        "sp_reset_line(uuid, text)",
        "sp_audit_append_only()",
        "sp_audit(uuid, text, text, uuid, jsonb, jsonb)",
        "sp_actor_kind()",
        "sp_correlation_id()",
        "sp_actor_role()",
        "sp_current_user()",
        "sp_current_tenant()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn};")
