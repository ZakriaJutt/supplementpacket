"""B2 security fixes (B2-S07): a session state for choosing a shop after every factor.

Revision ID: 20261111_0006
Revises: 20261111_0005
Create Date: 2026-11-11

`choose_tenant` is a 5-minute session for a person with several shops who has passed every
factor but not picked a shop; it reaches only `POST /auth/tenant`. No shop is named before
the second factor.
"""

from __future__ import annotations

from alembic import op

revision = "20261111_0006"
down_revision = "20261111_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sessions DROP CONSTRAINT ck_sessions_auth_level, "
        "ADD CONSTRAINT ck_sessions_auth_level CHECK (auth_level IN ('password','choose_tenant','full'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM sessions WHERE auth_level = 'choose_tenant'")
    op.execute(
        "ALTER TABLE sessions DROP CONSTRAINT ck_sessions_auth_level, "
        "ADD CONSTRAINT ck_sessions_auth_level CHECK (auth_level IN ('password','full'))"
    )
