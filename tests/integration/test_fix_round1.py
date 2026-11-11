"""Permanent regression tests for the B1 round-1 review findings (B1-001 .. B1-011)."""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from sp_api.main import create_app
from sp_files import MemoryObjectStore
from sp_worker.handlers import default_handlers
from sp_worker.runner import Worker
from tests.conftest import SYNTHETIC_PDF, TODAY, Api, Shop, approve, create_ro, freeze


def _line(est: Api, ro_id: str, name: str, cents: int, origin: str = "manual") -> dict[str, Any]:
    r = est.post(
        f"/ros/{ro_id}/lines",
        json={
            "origin": origin,
            "category": "missing_operation",
            "description": f"Operation {name}",
            "requested_cents": cents,
            "explanation": "Synthetic explanation of the needed operation.",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _current(est: Api, ro_id: str, line_id: str) -> dict[str, Any]:
    return next(x for x in est.get(f"/ros/{ro_id}/lines").json() if x["id"] == line_id)


def _mark_sent(est: Api, packet: dict[str, Any], on: str | None = None) -> Any:
    return est.post(
        f"/packets/{packet['id']}/mark-sent",
        json={
            "sent_on": on or TODAY.isoformat(),
            "sent_channel": "email",
            "confirm": True,
            "requested_total_cents": packet["requested_total_cents"],
            "line_count": packet["line_count"],
        },
    )


def _response(est: Api, pl: dict[str, Any], **body: Any) -> Any:
    return est.put(f"/packet-lines/{pl['id']}/response", json=body, headers={"If-Match": str(pl["row_version"])})


def _response_doc(est: Api, packet_id: str) -> str:
    r = est.post(
        f"/packets/{packet_id}/response-documents", files={"file": ("r.pdf", SYNTHETIC_PDF + uuid.uuid4().bytes, "application/pdf")}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["document"]["id"])


def _sent_ro(est: Api, shop: Shop, cents: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ro = create_ro(est, shop)
    line = _line(est, ro["id"], "A", cents)
    assert approve(est, line).status_code == 200
    packet = freeze(est, ro["id"]).json()
    assert _mark_sent(est, packet["packet"]).status_code == 200
    return ro, line, packet


def _report(owner: Api, shop: Shop) -> dict[str, Any]:
    r = owner.get(f"/pilots/{shop.pilot_id}/report")
    assert r.status_code == 200, r.text
    return r.json()["refund_test"]


def _backdate(owner_engine: Any, sql: str, params: dict[str, Any]) -> None:
    """Test-only: move recorded dates into the past (bypasses the immutability triggers as the owner)."""
    with owner_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text(sql), params)


# B1-001 ---------------------------------------------------------------------------------------------
def test_b1_001_sent_packet_stays_in_pilot_after_supersede(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est, owner = api["estimator"], api["owner"]
    ro, _, p1 = _sent_ro(est, shop, 20000)
    doc = _response_doc(est, p1["packet"]["id"])
    assert (
        _response(
            est, p1["lines"][0], response_status="approved_full", response_date=TODAY.isoformat(), response_document_id=doc
        ).status_code
        == 200
    )
    before = _report(owner, shop)
    assert before["pilot_insurer_approved_cents"] == 20000 and before["counted_packet_ids"] == [p1["packet"]["id"]]
    # Correction v2 frozen, not sent: the chain still qualifies once with A carried forward.
    b = _line(est, ro["id"], "B", 3000)
    assert approve(est, b).status_code == 200
    p2 = freeze(est, ro["id"]).json()
    after = _report(owner, shop)
    assert after["pilot_insurer_approved_cents"] == 20000 and after["counted_packet_ids"] == [p1["packet"]["id"]]
    # v2 sent after day 30: still one unit, still counted once. Move v1 into an earlier pilot window.
    _backdate(
        owner_engine,
        "UPDATE packets SET frozen_at = frozen_at - interval '20 days', sent_on = :d WHERE id = :p",
        {"d": TODAY - timedelta(days=20), "p": p1["packet"]["id"]},
    )
    _backdate(owner_engine, "UPDATE pilots SET start_date = :d WHERE id = :p", {"d": TODAY - timedelta(days=40), "p": str(shop.pilot_id)})
    _backdate(
        owner_engine,
        "UPDATE packet_lines SET response_date = :d WHERE packet_id IN (:a, :b)",
        {"d": TODAY - timedelta(days=15), "a": p1["packet"]["id"], "b": p2["packet"]["id"]},
    )
    assert _mark_sent(est, p2["packet"]).status_code == 200  # day 41, outside the window
    late = _report(owner, shop)
    assert late["counted_packet_ids"] == [p1["packet"]["id"]]
    assert late["pilot_insurer_approved_cents"] == 20000  # line B was first sent after day 30: not counted


# B1-002 ---------------------------------------------------------------------------------------------
def test_b1_002_undated_or_undocumented_approval_excluded_and_listed(api: dict[str, Api], shop: Shop) -> None:
    est, owner = api["estimator"], api["owner"]
    _, _, documented = _sent_ro(est, shop, 30000)
    _, _, undated = _sent_ro(est, shop, 40000)
    _, _, undocumented = _sent_ro(est, shop, 50000)
    doc = _response_doc(est, documented["packet"]["id"])
    assert (
        _response(
            est, documented["lines"][0], response_status="approved_full", response_date=TODAY.isoformat(), response_document_id=doc
        ).status_code
        == 200
    )
    assert _response(est, undated["lines"][0], response_status="approved_full").status_code == 200
    assert _response(est, undocumented["lines"][0], response_status="approved_full", response_date=TODAY.isoformat()).status_code == 200
    report = _report(owner, shop)
    assert report["pilot_insurer_approved_cents"] == 30000
    reasons = {e["packet_line_id"]: e["reason"] for e in report["excluded_approvals"]}
    assert reasons == {undated["lines"][0]["id"]: "no response date", undocumented["lines"][0]["id"]: "no response document"}
    future = _response(
        est,
        {**undated["lines"][0], "row_version": 2},
        response_status="approved_full",
        response_date=(TODAY + timedelta(days=2)).isoformat(),
    )
    assert future.status_code == 422


# B1-003 ---------------------------------------------------------------------------------------------
def test_b1_003_refund_undetermined_until_inputs_recorded(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    owner, office, op = api["owner"], api["office"], api["operator"]
    _backdate(owner_engine, "UPDATE pilots SET start_date = :d WHERE id = :p", {"d": TODAY - timedelta(days=2), "p": str(shop.pilot_id)})
    for i in range(10):
        office.post(
            "/baseline-ros",
            json={
                "location_id": str(shop.location_id),
                "ro_label": f"B{i}",
                "closed_month": "2026-07-01",
                "requested_cents": 20000,
                "approved_cents": 15000,
                "collected_cents": 15000,
                "source_note": "synthetic",
            },
        )
    report = _report(owner, shop)
    assert report["conditions"][0]["met"] is False  # counts missing
    r = office.patch(
        f"/pilots/{shop.pilot_id}/counts",
        json={"baseline_insurer_ro_count": 100, "baseline_supplemented_ro_count": 10, "window_insurer_ro_count": 1},
        headers={"If-Match": "1"},
    )
    assert r.status_code == 200 and r.json()["baseline_counts_supplied_at"]
    report = _report(owner, shop)
    assert report["conditions"][0]["met"] is True
    assert report["conditions"][1]["met"] == "undetermined"  # vendor-late drafts not recorded, fewer than 8 packets
    assert report["refund_result"] in ("undetermined", "not_due")
    assert (
        office.patch(
            f"/pilots/{shop.pilot_id}/vendor-late-drafts", json={"vendor_late_draft_count": 1}, headers={"If-Match": "2"}
        ).status_code
        == 403
    )
    r = op.patch(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json={"vendor_late_draft_count": 1}, headers={"If-Match": "2"})
    assert r.status_code == 200, r.text
    report = _report(owner, shop)
    assert report["conditions"][1]["met"] is False
    assert any(pid.startswith("vendor-late-draft") for pid in report["counted_packet_ids"])  # UT-11 late-draft variant via the API
    assert report["refund_result"] == "not_due"


def test_b1_003_pdf_shows_approver_name(settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    approve(est, _line(est, ro["id"], "A", 1000))
    packet = freeze(est, ro["id"]).json()["packet"]
    worker = Worker(settings, store, default_handlers())
    while worker.run_one() is not None:
        pass
    sha = est.get(f"/packets/{packet['id']}").json()["packet"]["pdf_sha256"]
    pdf = next(v for k, v in store.objects.items() if k.endswith(f"{sha}.pdf"))
    assert b"Synthetic Estimator A" in pdf


# B1-005 (E2E-06 rewritten) ----------------------------------------------------------------------------
def test_e2e06_b1_005_withdrawal_through_superseding_packet(
    settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore
) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    a = _line(est, ro["id"], "A", 10000)
    b = _line(est, ro["id"], "B", 5000)
    approve(est, a)
    approve(est, b)
    p1 = freeze(est, ro["id"]).json()
    assert _mark_sent(est, p1["packet"]).status_code == 200
    b_now = _current(est, ro["id"], b["id"])
    assert est.post(f"/lines/{b['id']}/exclude", headers={"If-Match": str(b_now["row_version"])}).status_code == 200
    review = est.get(f"/ros/{ro['id']}/packet-review").json()
    assert [w["supplement_line_id"] for w in review["withdrawn_lines"]] == [b["id"]]
    p2 = freeze(est, ro["id"])
    assert p2.status_code == 201, p2.text
    p2 = p2.json()
    assert p2["packet"]["requested_total_cents"] == 10000 and p2["packet"]["line_count"] == 1
    assert "withdraws 1 line" in p2["packet"]["email_draft"] and "USD 150.00" not in p2["packet"]["email_draft"]
    wl = next(pl for pl in p2["lines"] if pl["supplement_line_id"] == b["id"])
    assert wl["request_state"] == "withdrawn" and wl["response_status"] == "withdrawn" and wl["requested_cents"] == 5000
    ledger = est.get(f"/ros/{ro['id']}/ledger").json()
    assert ledger["requested_cents"] == 10000 and ledger["withdrawn_cents"] == 5000
    assert _response(est, wl, response_status="approved_full").status_code == 409
    assert est.get(f"/packets/{p1['packet']['id']}").json()["packet"]["status"] == "superseded"  # the old version stays readable
    worker = Worker(settings, store, default_handlers())
    while worker.run_one() is not None:
        pass
    sha = est.get(f"/packets/{p2['packet']['id']}").json()["packet"]["pdf_sha256"]
    pdf = next(v for k, v in store.objects.items() if k.endswith(f"{sha}.pdf"))
    requested_part, withdrawn_part = pdf.split(b"withdrawn", 1)
    assert b"Operation B" not in requested_part and b"Operation B" in withdrawn_part


# B1-006 ---------------------------------------------------------------------------------------------
def test_b1_006_demoted_or_removed_approver_resets_approval(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est, owner = api["estimator"], api["owner"]
    ro = create_ro(est, shop)
    line = _line(est, ro["id"], "A", 12000)
    assert approve(est, line).status_code == 200
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE memberships SET role = 'office' WHERE user_id = :u"), {"u": shop.users["estimator"]})
    assert _current(owner, ro["id"], line["id"])["status"] == "draft"
    assert freeze(owner, ro["id"]).status_code == 409
    # Deactivated approver: the freeze refuses and returns the line to draft.
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE memberships SET role = 'estimator' WHERE user_id = :u"), {"u": shop.users["estimator"]})
    assert approve(est, _current(est, ro["id"], line["id"])).status_code == 200
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'disabled' WHERE id = :u"), {"u": shop.users["estimator"]})
    r = freeze(owner, ro["id"])
    assert r.status_code == 409 and r.json()["problems"][0]["reason"] == "approver no longer permitted"
    assert _current(owner, ro["id"], line["id"])["status"] == "draft"
    # Removed member.
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'active' WHERE id = :u"), {"u": shop.users["estimator"]})
    assert approve(est, _current(est, ro["id"], line["id"])).status_code == 200
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM memberships WHERE user_id = :u"), {"u": shop.users["estimator"]})
    assert _current(owner, ro["id"], line["id"])["status"] == "draft"


# B1-009, B1-010, B1-011 ----------------------------------------------------------------------------------
def test_b1_009_money_and_input_types(api: dict[str, Api], shop: Shop) -> None:
    est, owner = api["estimator"], api["owner"]
    ro = create_ro(est, shop)
    base = {"origin": "manual", "category": "other", "description": "Seam sealer"}
    for bad in (129.99, "12.5", True, None, "1e3"):
        r = est.post(f"/ros/{ro['id']}/lines", json={**base, "requested_cents": bad})
        assert r.status_code == 422, (bad, r.text)
    assert est.post(f"/ros/{ro['id']}/lines", json={**base, "requested_cents": "12500"}).json()["requested_cents"] == 12500
    for bad_hours in ("NaN", "Infinity", 1.2, "1.234"):
        assert est.post(f"/ros/{ro['id']}/lines", json={**base, "requested_cents": 100, "hours_delta": bad_hours}).status_code == 422
    assert est.post("/ros", json={"ro_number": "X"}).status_code == 422
    assert (
        owner.post(
            f"/ros/{ro['id']}/payments",
            json={"kind": "deductible", "payer": "customer", "amount_cents": 500.5, "paid_on": TODAY.isoformat()},
        ).status_code
        == 422
    )


def test_b1_010_sent_date_not_future_not_before_freeze(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    approve(est, _line(est, ro["id"], "A", 1000))
    packet = freeze(est, ro["id"]).json()["packet"]
    assert _mark_sent(est, packet, (TODAY + timedelta(days=1)).isoformat()).status_code == 422
    assert _mark_sent(est, packet, (TODAY - timedelta(days=3)).isoformat()).status_code == 422
    assert _mark_sent(est, packet).status_code == 200


def test_b1_011_free_text_capped_and_notice_returned(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    long_text = "Step 1. Remove the bumper cover per OEM procedure. " * 300
    r = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "other", "description": "Op", "requested_cents": 100, "explanation": long_text},
    )
    assert r.status_code == 422 and "procedure" in r.json()["detail"]
    ok = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "other", "description": "Op", "requested_cents": 100, "explanation": "Short shop note."},
    )
    assert ok.status_code == 201 and "Do not paste procedure" in ok.json()["free_text_notice"]
    assert "free_text_notice" in est.get(f"/ros/{ro['id']}/packet-review").json()


# IT-03 concurrent variant (review note) ---------------------------------------------------------------
def test_it03_concurrent_uploads_return_one_document(settings: Any, store: MemoryObjectStore, shop: Shop, owner_engine: Any) -> None:
    client = TestClient(create_app(settings, store), raise_server_exceptions=False)
    est = Api(client, shop.tokens["estimator"])
    for label, keys in (("same", ["k"] * 4), ("new", ["a", "b", "c", "d"])):
        ro = create_ro(est, shop)["id"]
        data = SYNTHETIC_PDF + uuid.uuid4().bytes
        out: list[tuple[int, str]] = []

        def go(key: str, ro_id: str = ro, payload: bytes = data, sink: list[tuple[int, str]] = out, tag: str = label) -> None:
            r = client.post(
                f"/api/v1/ros/{ro_id}/documents",
                data={"purpose": "shop_estimate"},
                files={"file": ("e.pdf", payload, "application/pdf")},
                headers={"Authorization": f"Bearer {shop.tokens['estimator']}", "Idempotency-Key": f"{tag}-{key}-{ro_id}"},
            )
            sink.append((r.status_code, r.json().get("document", {}).get("id", r.text)))

        threads = [threading.Thread(target=go, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert {s for s, _ in out} == {202}, out
        assert len({d for _, d in out}) == 1
        with owner_engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM documents WHERE ro_id = :r"), {"r": ro}).scalar() == 1
