"""Jobs, uploads, bulk photos and logging: IT-03, IT-04, IT-05, IT-11, IT-13, UT-13 (database)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from sp_files import MemoryObjectStore
from sp_obs import configure_logging
from sp_parsers import ParsedEstimate, ParsedLine, ParserError, clear_registry, register
from sp_worker.handlers import default_handlers
from sp_worker.runner import Worker, apply_event
from tests.conftest import APP_URL, SYNTHETIC_PDF, Api, Shop, create_ro, jpeg

REPO = Path(__file__).resolve().parents[2]


class FakeParser:
    name = "fake-ccc"
    version = "1.0.0"
    fail_first = 0

    def parse(self, data: bytes) -> ParsedEstimate:
        if FakeParser.fail_first > 0:
            FakeParser.fail_first -= 1
            raise RuntimeError("transient read failure")
        if b"unreadable" in data:
            raise ParserError("no text layer")
        lines = tuple(
            ParsedLine(
                line_no=i,
                page=1,
                operation="repair",
                description=f"Panel {i}",
                line_total_cents=10000,
                labor_hours=Decimal("2.0"),
                labor_rate_cents=5000,
            )
            for i in range(1, 4)
        )
        return ParsedEstimate(self.name, self.version, lines, printed_total_cents=30000, page_count=1)


@pytest.fixture()
def fake_parser() -> Iterator[None]:
    register("ccc_one", FakeParser)
    FakeParser.fail_first = 0
    yield
    clear_registry()


@pytest.fixture()
def drained(owner_engine: Any) -> None:
    """Earlier tests leave unrelated queued jobs; park them so this test's worker sees only its own."""
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET state = 'failed', error_code = 'parked_by_test' WHERE state IN ('queued','running')"))


def _upload(user: Api, ro_id: str, data: bytes, key: str | None = None) -> Any:
    headers = {"Idempotency-Key": key} if key else None
    return user.post(
        f"/ros/{ro_id}/documents",
        data={"purpose": "shop_estimate", "source_system": "ccc_one"},
        files={"file": ("e.pdf", data, "application/pdf")},
        headers=headers,
    )


def test_it03_repeated_upload_returns_original_document_and_job(
    settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore, fake_parser: None, drained: None, owner_engine: Any
) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    data = SYNTHETIC_PDF + uuid.uuid4().bytes
    first = _upload(est, ro["id"], data, key="upload-1")
    again = _upload(est, ro["id"], data, key="upload-1")  # the client gave up and retried with the same key
    other_key = _upload(est, ro["id"], data, key="upload-2")  # same file, new key
    assert first.status_code == again.status_code == other_key.status_code == 202
    assert first.json() == again.json()
    assert other_key.json()["document"]["id"] == first.json()["document"]["id"] and other_key.json()["created"] is False
    assert other_key.json()["job"]["id"] == first.json()["job"]["id"]
    with owner_engine.connect() as conn:
        docs = conn.execute(text("SELECT count(*) FROM documents WHERE ro_id = :r"), {"r": ro["id"]}).scalar()
        jobs = conn.execute(text("SELECT count(*) FROM jobs WHERE subject_id = :d"), {"d": first.json()["document"]["id"]}).scalar()
    assert (docs, jobs) == (1, 1)
    Worker(settings, store, default_handlers()).run_one()
    job = est.get(f"/jobs/{first.json()['job']['id']}").json()
    assert job["state"] == "succeeded" and job["result"]["status"] == "reconciled"


def test_it04_late_and_duplicate_events_are_discarded(
    settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore, fake_parser: None, drained: None, owner_engine: Any
) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    doc = _upload(est, ro["id"], SYNTHETIC_PDF + uuid.uuid4().bytes).json()
    job_id = uuid.UUID(doc["job"]["id"])
    worker = Worker(settings, store, default_handlers())
    worker.run_one()  # queued(0) -> running(1) -> succeeded(2)
    assert not apply_event(APP_URL, shop.tenant_id, job_id, "running", 0)  # late "running"
    assert not apply_event(APP_URL, shop.tenant_id, job_id, "succeeded", 1)  # duplicate "succeeded"
    with owner_engine.connect() as conn:
        state, version = conn.execute(text("SELECT state, state_version FROM jobs WHERE id = :i"), {"i": job_id}).first()
        sets = conn.execute(text("SELECT count(*) FROM parse_runs WHERE document_id = :d"), {"d": doc["document"]["id"]}).scalar()
        lines = conn.execute(
            text("SELECT count(*) FROM estimate_lines e JOIN parse_runs p ON p.id = e.parse_run_id WHERE p.document_id = :d"),
            {"d": doc["document"]["id"]},
        ).scalar()
    assert (state, version, sets, lines) == ("succeeded", 2, 1, 3)


def test_ut13_stale_completion_in_database(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    with owner_engine.begin() as conn:
        job_id = conn.execute(
            text(
                "INSERT INTO jobs (tenant_id, kind, subject_id, idempotency_key, correlation_id, state, state_version) "
                "VALUES (:t, 'parse_document', gen_random_uuid(), :k, gen_random_uuid(), 'running', 3) RETURNING id"
            ),
            {"t": str(shop.tenant_id), "k": uuid.uuid4().hex},
        ).scalar()
    assert not apply_event(APP_URL, shop.tenant_id, job_id, "succeeded", 2)
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT state, state_version FROM jobs WHERE id = :i"), {"i": job_id}).first() == ("running", 3)


def test_sweeper_requeues_expired_lock(settings: Any, shop: Shop, owner_engine: Any, store: MemoryObjectStore) -> None:
    with owner_engine.begin() as conn:
        job_id = conn.execute(
            text(
                "INSERT INTO jobs (tenant_id, kind, subject_id, idempotency_key, correlation_id, state, state_version, attempt, locked_until) "
                "VALUES (:t, 'parse_document', gen_random_uuid(), :k, gen_random_uuid(), 'running', 1, 1, now() - interval '1 minute') RETURNING id"
            ),
            {"t": str(shop.tenant_id), "k": uuid.uuid4().hex},
        ).scalar()
    assert Worker(settings, store, default_handlers()).sweep() >= 1
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT state, state_version FROM jobs WHERE id = :i"), {"i": job_id}).first() == ("queued", 2)


def test_unreadable_file_fails_cleanly_and_manual_entry_completes(
    settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore, fake_parser: None, drained: None
) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    doc = _upload(est, ro["id"], SYNTHETIC_PDF + b"unreadable" + uuid.uuid4().bytes).json()
    Worker(settings, store, default_handlers()).run_one()
    job = est.get(f"/jobs/{doc['job']['id']}").json()
    assert job["state"] == "failed" and job["error_code"] == "unreadable_manual_entry_offered"
    r = est.post(
        f"/documents/{doc['document']['id']}/manual-lines",
        json={"printed_total_cents": 5000, "lines": [{"operation": "repair", "description": "Door", "line_total_cents": 5000}]},
    )
    assert r.status_code == 201 and r.json()["parse_run"]["status"] == "manual"


def test_it05_bulk_photos_report_per_file_and_retry_adds_none_twice(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    line = est.post(
        f"/ros/{ro['id']}/lines", json={"origin": "manual", "category": "other", "description": "Seam sealer", "requested_cents": 4000}
    ).json()
    files = [("files", (f"p{i}.jpg", jpeg(f"photo-{i}".encode()), "image/jpeg")) for i in range(7)]
    files += [("files", ("bad1.jpg", b"not an image", "image/jpeg")), ("files", ("bad2.jpg", SYNTHETIC_PDF, "image/jpeg"))]
    first = est.post(f"/lines/{line['id']}/photos", files=files, data={"attested": "true", "taken_by_shop": "true"}).json()
    assert (first["attached"], first["rejected"], first["already_attached"]) == (7, 2, 0)
    assert [r["index"] for r in first["results"] if r["status"] == "rejected"] == [7, 8]
    retry = est.post(f"/lines/{line['id']}/photos", files=files, data={"attested": "true", "taken_by_shop": "true"}).json()
    assert (retry["attached"], retry["rejected"], retry["already_attached"]) == (0, 2, 7)


def test_it11_one_correlation_id_and_no_sensitive_values_in_logs(
    settings: Any, client: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore, fake_parser: None, drained: None
) -> None:
    buffer = io.StringIO()
    configure_logging("INFO", stream=buffer)
    cid = str(uuid.uuid4())
    est = api["estimator"]
    vin, claim = "1HGCM82633A004352", "SYN-CLM-778899"
    ro = est.post(
        "/ros",
        json={
            "location_id": str(shop.location_id),
            "ro_number": "RO-LOG-1",
            "vin": vin,
            "claim_number": claim,
            "adjuster_name": "Pat Example",
        },
        headers={"X-Correlation-ID": cid},
    ).json()
    doc = est.post(
        f"/ros/{ro['id']}/documents",
        data={"purpose": "shop_estimate", "source_system": "ccc_one"},
        files={"file": ("Owner Name estimate.pdf", SYNTHETIC_PDF + uuid.uuid4().bytes, "application/pdf")},
        headers={"X-Correlation-ID": cid},
    ).json()
    FakeParser.fail_first = 1
    worker = Worker(settings, store, default_handlers())
    worker.run_one()  # crashes, retried
    worker.run_one()  # succeeds
    assert est.get(f"/jobs/{doc['job']['id']}").json()["state"] == "succeeded"
    records = [json.loads(line) for line in buffer.getvalue().splitlines() if line.startswith("{")]
    job_records = [r for r in records if r.get("job_id") == doc["job"]["id"]]
    assert {r["event"] for r in job_records} >= {"job started", "job crashed", "job finished"}
    assert {r["correlation_id"] for r in job_records} == {cid}
    assert any(r["correlation_id"] == cid and r["event"] == "request" for r in records)
    text_out = buffer.getvalue()
    for secret in (vin, claim, "Pat Example", "Owner Name", "30000", "300.00"):
        assert secret not in text_out, secret
    configure_logging("INFO")


def test_it13_worker_starts_without_web_framework(settings: Any) -> None:
    env = {
        **os.environ,
        "PUBLIC_BASE_URL": settings.public_base_url,
        "DATABASE_URL": APP_URL,
        "STORAGE_BUCKET": settings.storage_bucket,
        "SESSION_KEY": "test-session-key-not-secret",
        "WORKER_HEARTBEAT_PATH": str(Path(settings.storage_bucket) / "it13.hb"),
    }
    code = (
        "import sys, sp_worker.__main__ as m\n"
        "bad = [n for n in ('fastapi', 'starlette', 'uvicorn', 'sp_api') if n in sys.modules]\n"
        "assert not bad, bad\n"
        "sys.exit(m.main(['--once']))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    events = [json.loads(line)["event"] for line in proc.stdout.splitlines() if line.startswith("{")]
    assert "worker starting" in events
    assert (Path(settings.storage_bucket) / "it13.hb").exists()
