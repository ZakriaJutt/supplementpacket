"""Fix round 2: pilot count history and auditable vendor-late drafts (B1-003 residue).

Revision ID: 20261111_0003
Revises: 20261111_0002
Create Date: 2026-11-11

Every change to a pilot count is an append-only event, so condition (a) can use the
value in force at the end of day 7. Vendor-late drafts are rows with the draft
reference, request and return times and the recorder, readable by the shop. The bare
`pilots.vendor_late_draft_count` is removed (it was never released).
"""

from __future__ import annotations

from alembic import op

revision = "20261111_0003"
down_revision = "20261111_0002"
branch_labels = None
depends_on = None

APP_ROLE = "supplementpacket_app"

UP = rf"""
ALTER TABLE pilots ADD CONSTRAINT uq_pilots_tenant_id UNIQUE (tenant_id, id);

CREATE TABLE pilot_count_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    pilot_id uuid NOT NULL,
    field text NOT NULL CONSTRAINT ck_pilot_count_events_field
        CHECK (field IN ('baseline_insurer_ro_count','baseline_supplemented_ro_count','window_insurer_ro_count')),
    value integer CONSTRAINT ck_pilot_count_events_value CHECK (value IS NULL OR value >= 0),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL REFERENCES users(id),
    CONSTRAINT fk_pilot_count_events_pilot FOREIGN KEY (tenant_id, pilot_id) REFERENCES pilots (tenant_id, id)
);
CREATE INDEX ix_pilot_count_events_pilot ON pilot_count_events (tenant_id, pilot_id, field, recorded_at);

CREATE TABLE vendor_late_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    pilot_id uuid NOT NULL,
    draft_reference text NOT NULL CONSTRAINT ck_vendor_late_drafts_ref CHECK (length(draft_reference) BETWEEN 1 AND 100),
    requested_at timestamptz NOT NULL,
    returned_at timestamptz,
    note text CONSTRAINT ck_vendor_late_drafts_note CHECK (note IS NULL OR length(note) <= 300),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL REFERENCES users(id),
    CONSTRAINT ck_vendor_late_drafts_order CHECK (returned_at IS NULL OR returned_at >= requested_at),
    CONSTRAINT uq_vendor_late_drafts_ref UNIQUE (tenant_id, pilot_id, draft_reference),
    CONSTRAINT fk_vendor_late_drafts_pilot FOREIGN KEY (tenant_id, pilot_id) REFERENCES pilots (tenant_id, id)
);

ALTER TABLE pilots DROP CONSTRAINT IF EXISTS ck_pilots_late_drafts;
ALTER TABLE pilots DROP COLUMN vendor_late_draft_count;

CREATE FUNCTION sp_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION USING MESSAGE = TG_TABLE_NAME || ' is append-only', ERRCODE = 'insufficient_privilege';
END $$;
CREATE TRIGGER trg_pilot_count_events_append_only BEFORE UPDATE OR DELETE ON pilot_count_events
  FOR EACH ROW EXECUTE FUNCTION sp_append_only();
CREATE TRIGGER trg_vendor_late_drafts_append_only BEFORE UPDATE OR DELETE ON vendor_late_drafts
  FOR EACH ROW EXECUTE FUNCTION sp_append_only();

ALTER TABLE pilot_count_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_count_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON pilot_count_events USING (tenant_id = sp_current_tenant()) WITH CHECK (tenant_id = sp_current_tenant());
ALTER TABLE vendor_late_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_late_drafts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON vendor_late_drafts USING (tenant_id = sp_current_tenant()) WITH CHECK (tenant_id = sp_current_tenant());

GRANT SELECT, INSERT ON pilot_count_events, vendor_late_drafts TO {APP_ROLE};
GRANT USAGE, SELECT ON SEQUENCE pilot_count_events_id_seq TO {APP_ROLE};
"""

DOWN = """
DROP TABLE IF EXISTS vendor_late_drafts;
DROP TABLE IF EXISTS pilot_count_events;
DROP FUNCTION IF EXISTS sp_append_only();
ALTER TABLE pilots DROP CONSTRAINT IF EXISTS uq_pilots_tenant_id;
ALTER TABLE pilots ADD COLUMN vendor_late_draft_count integer;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
