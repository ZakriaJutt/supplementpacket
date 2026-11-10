"""ORM parity check (T-2.1.3, R-08, IT-07).

Compares a database migrated to head with the ORM metadata (tables, columns, types,
nullability, indexes, unique constraints, foreign keys) using Alembic's comparator, and
checks the catalog for row-level security, FORCE, the tenant policy on every
tenant-owned table, and the integrity triggers. Exits non-zero on any difference.

The schema guide proposes two scratch databases; this machine allows only the product's
own two databases, so the migrated test database is compared with the metadata instead.
"""

from __future__ import annotations

import os
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, create_engine, text

from sp_db.models import TENANT_TABLES, Base

REQUIRED_TRIGGERS = {
    ("audit_events", "trg_audit_append_only"),
    ("supplement_lines", "trg_supplement_lines_guard"),
    ("supplement_lines", "trg_supplement_lines_insert_guard"),
    ("line_evidence", "trg_line_evidence_reset"),
    ("photos", "trg_photos_reset"),
    ("reference_citations", "trg_references_reset"),
    ("estimate_lines", "trg_estimate_lines_reset"),
    ("packets", "trg_packets_guard"),
    ("packet_lines", "trg_packet_lines_guard"),
    ("payments", "trg_payments_guard"),
}


def run(url: str, metadata: MetaData | None = None) -> list[str]:
    problems: list[str] = []
    engine = create_engine(url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": False})
        for diff in compare_metadata(ctx, metadata if metadata is not None else Base.metadata):
            problems.append(f"schema difference: {diff}")
        rows = conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )
        ).all()
        catalog = {r[0]: (r[1], r[2], r[3]) for r in rows}
        for table in (*TENANT_TABLES, "tenants"):
            enabled, forced, policies = catalog.get(table, (False, False, 0))
            if not (enabled and forced and policies == 1):
                problems.append(f"row-level security incomplete on {table}: enabled={enabled} forced={forced} policies={policies}")
        triggers = {
            (r[0], r[1])
            for r in conn.execute(
                text("SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid WHERE NOT t.tgisinternal")
            )
        }
        for missing in sorted(REQUIRED_TRIGGERS - triggers):
            problems.append(f"missing trigger {missing[1]} on {missing[0]}")
    engine.dispose()
    return problems


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        print("MIGRATION_DATABASE_URL is required", file=sys.stderr)
        return 2
    problems = run(url)
    for problem in problems:
        print(problem)
    print(f"orm parity: {len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
