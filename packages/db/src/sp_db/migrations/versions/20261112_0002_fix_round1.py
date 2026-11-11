"""Fix round 1: withdrawn packet lines, response recording time, pilot inputs, approver name, approver demotion.

Revision ID: 20261112_0002
Revises: 20261111_0001
Create Date: 2026-11-12

B1-001/B1-002 (response_recorded_at), B1-003 (pilot counts timestamp, vendor-late drafts,
users.display_name), B1-005 (packet_lines.request_state), B1-006 (membership demotion
resets that user's approvals). Additive only (expand step).
"""

from __future__ import annotations

from alembic import op

revision = "20261112_0002"
down_revision = "20261111_0001"
branch_labels = None
depends_on = None

UP = r"""
ALTER TABLE users ADD COLUMN display_name text;

ALTER TABLE packet_lines ADD COLUMN request_state text NOT NULL DEFAULT 'requested';
ALTER TABLE packet_lines ADD CONSTRAINT ck_packet_lines_request_state CHECK (request_state IN ('requested','withdrawn'));
ALTER TABLE packet_lines ADD CONSTRAINT ck_packet_lines_withdrawn
  CHECK (request_state <> 'withdrawn' OR (response_status = 'withdrawn' AND approved_cents = 0));
ALTER TABLE packet_lines ADD COLUMN response_recorded_at timestamptz;

ALTER TABLE pilots ADD COLUMN baseline_counts_supplied_at timestamptz;
ALTER TABLE pilots ADD COLUMN vendor_late_draft_count integer;
ALTER TABLE pilots ADD CONSTRAINT ck_pilots_late_drafts CHECK (vendor_late_draft_count IS NULL OR vendor_late_draft_count >= 0);
ALTER TABLE pilots ADD COLUMN vendor_late_drafts_recorded_at timestamptz;
ALTER TABLE pilots ADD COLUMN vendor_late_drafts_recorded_by uuid REFERENCES users(id);

CREATE OR REPLACE FUNCTION sp_packet_lines_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE purged timestamptz;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'packet lines are never deleted';
  END IF;
  IF (NEW.tenant_id, NEW.packet_id, NEW.supplement_line_id, NEW.line_no, NEW.origin, NEW.category, NEW.requested_cents,
      NEW.approved_by, NEW.approved_at, NEW.approved_fingerprint, NEW.carried_from_packet_line_id, NEW.request_state)
     IS DISTINCT FROM (OLD.tenant_id, OLD.packet_id, OLD.supplement_line_id, OLD.line_no, OLD.origin, OLD.category,
      OLD.requested_cents, OLD.approved_by, OLD.approved_at, OLD.approved_fingerprint, OLD.carried_from_packet_line_id,
      OLD.request_state) THEN
    RAISE EXCEPTION 'packet line snapshot is immutable';
  END IF;
  IF OLD.request_state = 'withdrawn' AND (NEW.response_status, NEW.approved_cents) IS DISTINCT FROM (OLD.response_status, OLD.approved_cents) THEN
    RAISE EXCEPTION 'a line withdrawn by a superseding packet has no insurer response';
  END IF;
  IF (NEW.description, NEW.evidence_snapshot) IS DISTINCT FROM (OLD.description, OLD.evidence_snapshot) THEN
    SELECT purged_at INTO purged FROM packets WHERE id = NEW.packet_id;
    IF purged IS NULL OR NEW.description <> '[redacted]' OR NEW.evidence_snapshot <> '{"redacted": true}'::jsonb THEN
      RAISE EXCEPTION 'packet line snapshot changes only by takedown redaction';
    END IF;
  END IF;
  RETURN NEW;
END $$;

-- B1-006: an approval is valid only while its approver holds the Owner or Estimator role.
CREATE FUNCTION sp_memberships_reset_approvals() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
  IF OLD.role IN ('owner','estimator') AND (TG_OP = 'DELETE' OR NEW.role NOT IN ('owner','estimator')) THEN
    FOR r IN SELECT id FROM supplement_lines
             WHERE tenant_id = OLD.tenant_id AND status = 'approved' AND approved_by = OLD.user_id LOOP
      PERFORM sp_reset_line(r.id, 'approver no longer holds the estimator role');
    END LOOP;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER trg_memberships_reset_approvals AFTER UPDATE OR DELETE ON memberships
  FOR EACH ROW EXECUTE FUNCTION sp_memberships_reset_approvals();
"""

DOWN = r"""
DROP TRIGGER IF EXISTS trg_memberships_reset_approvals ON memberships;
DROP FUNCTION IF EXISTS sp_memberships_reset_approvals();
ALTER TABLE pilots DROP COLUMN IF EXISTS vendor_late_drafts_recorded_by, DROP COLUMN IF EXISTS vendor_late_drafts_recorded_at,
  DROP COLUMN IF EXISTS vendor_late_draft_count, DROP COLUMN IF EXISTS baseline_counts_supplied_at;
ALTER TABLE packet_lines DROP COLUMN IF EXISTS response_recorded_at;
ALTER TABLE packet_lines DROP CONSTRAINT IF EXISTS ck_packet_lines_withdrawn;
ALTER TABLE packet_lines DROP COLUMN IF EXISTS request_state;
ALTER TABLE users DROP COLUMN IF EXISTS display_name;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
