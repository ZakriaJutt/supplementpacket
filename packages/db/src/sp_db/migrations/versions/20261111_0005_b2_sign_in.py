"""B2: sign-in with password and TOTP, server sessions, invitations, password reset, throttling.

Revision ID: 20261111_0005
Revises: 20261111_0004
Create Date: 2026-11-11

T-2.2.2 and the invitation part of T-2.2.3. `sessions.auth_level` separates a session that
has passed the password step only ('password', minutes long, accepted by nothing but the TOTP
step) from a signed-in one ('full'). Invites are tenant data under row-level security; two
SECURITY DEFINER functions answer the only two questions asked before a tenant is known:
which tenants a verified user may enter, and which tenant an invitation token belongs to.
"""

from __future__ import annotations

from alembic import op

revision = "20261111_0005"
down_revision = "20261111_0004"
branch_labels = None
depends_on = None

APP_ROLE = "supplementpacket_app"

UP = rf"""
ALTER TABLE sessions ADD COLUMN auth_level text NOT NULL DEFAULT 'full'
    CONSTRAINT ck_sessions_auth_level CHECK (auth_level IN ('password','full'));
CREATE INDEX ix_sessions_user ON sessions (user_id);

ALTER TABLE users ADD COLUMN totp_last_step bigint;
ALTER TABLE users ADD COLUMN password_changed_at timestamptz;
ALTER TABLE users ADD CONSTRAINT ck_users_status CHECK (status IN ('active','disabled'));

CREATE TABLE invites (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    email citext NOT NULL,
    role text NOT NULL CONSTRAINT ck_invites_role CHECK (role IN ('owner','estimator','office')),
    token_hash bytea NOT NULL CONSTRAINT uq_invites_token UNIQUE,
    totp_pending_enc bytea,
    created_by uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    accepted_user_id uuid REFERENCES users(id),
    CONSTRAINT ck_invites_72h CHECK (expires_at <= created_at + interval '72 hours')
);
CREATE INDEX ix_invites_tenant ON invites (tenant_id, created_at DESC);
ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON invites USING (tenant_id = sp_current_tenant()) WITH CHECK (tenant_id = sp_current_tenant());

CREATE TABLE password_resets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    token_hash bytea NOT NULL CONSTRAINT uq_password_resets_token UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    CONSTRAINT ck_password_resets_30m CHECK (expires_at <= created_at + interval '30 minutes')
);
CREATE INDEX ix_password_resets_user ON password_resets (user_id);

CREATE TABLE auth_throttle (
    id bigserial PRIMARY KEY,
    bucket text NOT NULL,
    key_hash bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_auth_throttle_lookup ON auth_throttle (bucket, key_hash, created_at);

CREATE FUNCTION sp_login_tenants(p_user uuid) RETURNS TABLE (tenant_id uuid, tenant_name text, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT t.id, t.name, m.role
      FROM memberships m JOIN tenants t ON t.id = m.tenant_id
     WHERE m.user_id = p_user AND t.status <> 'deleting'
    UNION ALL
    SELECT t.id, t.name, 'operator'
      FROM operator_grants g JOIN tenants t ON t.id = g.tenant_id JOIN users u ON u.id = g.operator_user_id
     WHERE g.operator_user_id = p_user AND u.is_operator AND g.revoked_at IS NULL AND g.expires_at > now()
       AND t.status <> 'deleting'
       AND NOT EXISTS (SELECT 1 FROM memberships m2 WHERE m2.user_id = p_user AND m2.tenant_id = g.tenant_id)
$$;

CREATE FUNCTION sp_invite_lookup(p_hash bytea) RETURNS TABLE (invite_id uuid, tenant_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT id, tenant_id FROM invites WHERE token_hash = p_hash
$$;

REVOKE ALL ON FUNCTION sp_login_tenants(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION sp_invite_lookup(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sp_login_tenants(uuid) TO {APP_ROLE};
GRANT EXECUTE ON FUNCTION sp_invite_lookup(bytea) TO {APP_ROLE};
GRANT SELECT, INSERT, UPDATE ON invites, password_resets TO {APP_ROLE};
-- Accepting an invitation creates the account; the application can never set is_operator or status.
GRANT INSERT (id, email, password_hash, totp_secret_enc, totp_enabled_at, totp_last_step, display_name, password_changed_at)
    ON users TO {APP_ROLE};
GRANT UPDATE (password_hash, totp_secret_enc, totp_enabled_at, totp_last_step, display_name, password_changed_at)
    ON users TO {APP_ROLE};
GRANT SELECT, INSERT, DELETE ON auth_throttle TO {APP_ROLE};
GRANT USAGE, SELECT ON SEQUENCE auth_throttle_id_seq TO {APP_ROLE};
"""

DOWN = f"""
REVOKE INSERT, UPDATE ON users FROM {APP_ROLE};
DROP FUNCTION IF EXISTS sp_invite_lookup(bytea);
DROP FUNCTION IF EXISTS sp_login_tenants(uuid);
DROP TABLE IF EXISTS auth_throttle;
DROP TABLE IF EXISTS password_resets;
DROP TABLE IF EXISTS invites;
ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_status;
ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at;
ALTER TABLE users DROP COLUMN IF EXISTS totp_last_step;
DROP INDEX IF EXISTS ix_sessions_user;
ALTER TABLE sessions DROP COLUMN IF EXISTS auth_level;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
