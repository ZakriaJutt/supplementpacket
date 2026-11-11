"""Fix after round-3 retest: a vendor-late draft names its repair order (B1-003 residue).

Revision ID: 20261111_0004
Revises: 20261111_0003
Create Date: 2026-11-11

Each vendor-late draft row references the repair order it was for and, optionally, the
packet frozen from it (same repair order, enforced by a composite foreign key). One late
draft per repair order per pilot, so a repair order counts once in conditions (b) and (c).
The table was never released; it must be empty when this runs (NOT NULL without default).
"""

from __future__ import annotations

from alembic import op

revision = "20261111_0004"
down_revision = "20261111_0003"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE vendor_late_drafts ADD COLUMN ro_id uuid NOT NULL;
ALTER TABLE vendor_late_drafts ADD COLUMN packet_id uuid;
ALTER TABLE vendor_late_drafts ADD CONSTRAINT uq_vendor_late_drafts_ro UNIQUE (tenant_id, pilot_id, ro_id);
ALTER TABLE vendor_late_drafts ADD CONSTRAINT fk_vendor_late_drafts_ro
    FOREIGN KEY (tenant_id, ro_id) REFERENCES repair_orders (tenant_id, id);
ALTER TABLE vendor_late_drafts ADD CONSTRAINT fk_vendor_late_drafts_packet
    FOREIGN KEY (tenant_id, ro_id, packet_id) REFERENCES packets (tenant_id, ro_id, id);
"""

DOWN = """
ALTER TABLE vendor_late_drafts DROP CONSTRAINT IF EXISTS fk_vendor_late_drafts_packet;
ALTER TABLE vendor_late_drafts DROP CONSTRAINT IF EXISTS fk_vendor_late_drafts_ro;
ALTER TABLE vendor_late_drafts DROP CONSTRAINT IF EXISTS uq_vendor_late_drafts_ro;
ALTER TABLE vendor_late_drafts DROP COLUMN IF EXISTS packet_id;
ALTER TABLE vendor_late_drafts DROP COLUMN IF EXISTS ro_id;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
