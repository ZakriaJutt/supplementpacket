#!/usr/bin/env bash
# Drop every object in the public schema of ONE of this product's databases and re-run
# the migrations as the owner role. Refuses any database that is not ours.
set -euo pipefail
db="${1:?usage: reset_db.sh supplementpacket_dev|supplementpacket_test}"
case "$db" in supplementpacket_dev|supplementpacket_test) ;; *) echo "refusing to reset $db" >&2; exit 2;; esac
here="$(cd "$(dirname "$0")/.." && pwd)"
psql -X -q -v ON_ERROR_STOP=1 -h localhost -d "$db" -f "$here/scripts/db_bootstrap.sql"
PGOPTIONS="-c client_min_messages=warning" psql -X -q -v ON_ERROR_STOP=1 -h localhost -d "$db" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; REVOKE ALL ON SCHEMA public FROM PUBLIC;"
MIGRATION_DATABASE_URL="postgresql+psycopg://$(whoami)@localhost:5432/$db" \
  "$here/.venv/bin/alembic" -c "$here/packages/db/alembic.ini" upgrade head
echo "reset $db: migrated to head"
