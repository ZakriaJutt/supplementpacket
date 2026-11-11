"""Migration discipline and repository checks: IT-07, the boundary script (R-03, R-04), pilot report via the API."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import Index, MetaData

from sp_db.models import Base
from tests.conftest import OWNER_URL, Api, Shop

REPO = Path(__file__).resolve().parents[2]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it07_parity_passes_and_a_missing_index_fails() -> None:
    parity = _script("orm_parity")
    assert parity.run(OWNER_URL) == []
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    Index("ix_only_in_model", metadata.tables["payments"].c.paid_on)
    problems = parity.run(OWNER_URL, metadata)
    assert any("ix_only_in_model" in p for p in problems)


def test_it07_second_migration_head_fails(tmp_path: Path) -> None:
    heads = _script("check_migration_heads")
    versions = REPO / "packages" / "db" / "src" / "sp_db" / "migrations"
    copy = tmp_path / "migrations"
    shutil.copytree(versions, copy, ignore=shutil.ignore_patterns("__pycache__"))
    current = heads.heads(str(copy))
    assert len(current) == 1
    (copy / "versions" / "20261111_0092_branch_a.py").write_text(
        'revision = "branch_a"\ndown_revision = "' + current[0] + '"\nbranch_labels = None\ndepends_on = None\n'
        "def upgrade():\n    pass\ndef downgrade():\n    pass\n"
    )
    (copy / "versions" / "20261111_0093_branch_b.py").write_text(
        'revision = "branch_b"\ndown_revision = "' + current[0] + '"\nbranch_labels = None\ndepends_on = None\n'
        "def upgrade():\n    pass\ndef downgrade():\n    pass\n"
    )
    assert len(heads.heads(str(copy))) == 2
    assert heads.main(["x", str(copy)]) == 1


def test_boundary_script_fails_on_seeded_violations(tmp_path: Path) -> None:
    boundaries = _script("check_boundaries")
    assert boundaries.check(REPO) == []
    copy = tmp_path / "repo"
    for part in ("apps", "packages"):
        shutil.copytree(REPO / part, copy / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (copy / "apps/worker/src/sp_worker/bad.py").write_text("from sp_api.services import packets\nimport fastapi\n")
    (copy / "apps/api/src/sp_api/dup.py").write_text("def parse_cents(text):\n    return 0\n")
    problems = boundaries.check(copy)
    assert any("app imports another app" in p for p in problems)
    assert any("web framework" in p for p in problems)
    assert any("helper parse_cents" in p for p in problems)


def test_idempotency_key_reuse_with_other_body_is_refused(api: dict[str, Api], shop: Shop) -> None:
    owner = api["owner"]
    body = {"location_id": str(shop.location_id), "ro_number": "RO-IDEM-1"}
    first = owner.post("/ros", json=body, headers={"Idempotency-Key": "k-1"})
    again = owner.post("/ros", json=body, headers={"Idempotency-Key": "k-1"})
    other = owner.post("/ros", json={**body, "ro_number": "RO-IDEM-2"}, headers={"Idempotency-Key": "k-1"})
    assert first.status_code == again.status_code == 201 and first.json()["id"] == again.json()["id"]
    assert other.status_code == 422
    headers = {k: v for k, v in owner._headers(None, "POST").items() if k != "Idempotency-Key"}
    missing = owner.client.post("/api/v1/ros", json=body, headers=headers)
    assert missing.status_code == 428


def test_pilot_report_not_computable_then_counts(api: dict[str, Api], shop: Shop) -> None:
    owner, office = api["owner"], api["office"]
    report = owner.get(f"/pilots/{shop.pilot_id}/report").json()
    assert report["refund_test"]["computable"] is False
    assert report["refund_test"]["incremental_approved_cents"] == "not computable"
    assert any("baseline insurer-paid RO count" in m for m in report["refund_test"]["missing"])
    for i in range(10):
        r = office.post(
            "/baseline-ros",
            json={
                "location_id": str(shop.location_id),
                "ro_label": f"BASE-{i}",
                "closed_month": "2026-07-01",
                "requested_cents": 20000,
                "approved_cents": 15000,
                "collected_cents": 15000,
                "source_note": "synthetic baseline row",
            },
        )
        assert r.status_code == 201, r.text
    incomplete = office.post(
        "/baseline-ros",
        json={
            "location_id": str(shop.location_id),
            "ro_label": "BASE-X",
            "closed_month": "2026-07-01",
            "approved_cents": 15000,
            "source_note": "synthetic, collected unknown",
        },
    )
    assert incomplete.json()["collected_cents"] is None  # never a placeholder
    pilot_row: Any = office.patch(
        f"/pilots/{shop.pilot_id}/counts",
        json={"baseline_insurer_ro_count": 100, "baseline_supplemented_ro_count": 11, "window_insurer_ro_count": 40},
        headers={"If-Match": "1"},
    )
    assert pilot_row.status_code == 200, pilot_row.text
    report = owner.get(f"/pilots/{shop.pilot_id}/report").json()["refund_test"]
    assert report["computable"] is True
    # 10 of 11 complete (91%): 11 x 15000 = 165000 over 100 ROs = 1650 per RO; expected 66000; nothing approved yet.
    assert report["baseline_rate_cents"] == 1650 and report["expected_cents"] == 66000
    assert report["incremental_approved_cents"] == -66000
    assert report["refund_due"] is False  # conditions (b) and (c) are not met with no packets
    assert api["estimator"].post("/baseline-ros", json={}).status_code == 403
