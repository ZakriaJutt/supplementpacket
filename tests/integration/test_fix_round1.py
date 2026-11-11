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
    late_ro = create_ro(api["estimator"], shop)
    draft = {
        "ro_id": late_ro["id"],
        "draft_reference": "HAND-RUN-07",
        "requested_at": "2026-11-02T09:00:00-08:00",
        "returned_at": "2026-11-05T16:00:00-08:00",
    }
    assert office.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=draft).status_code == 403
    assert (
        op.post(
            f"/pilots/{shop.pilot_id}/vendor-late-drafts",
            json={**draft, "draft_reference": "ON-TIME", "returned_at": "2026-11-02T15:00:00-08:00"},
        ).status_code
        == 422
    )
    r = op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=draft)
    assert r.status_code == 201, r.text
    assert r.json()["recorded_by"] == str(shop.users["operator"]) and r.json()["recorded_at"]
    # Still undetermined until the vendor confirms the record is complete.
    assert _report(owner, shop)["conditions"][1]["met"] == "undetermined"
    pilot_row = owner.get(f"/pilots/{shop.pilot_id}/report").json()
    assert pilot_row["vendor_late_drafts"][0]["draft_reference"] == "HAND-RUN-07"  # the shop can see it
    assert [d["draft_reference"] for d in owner.get(f"/pilots/{shop.pilot_id}/vendor-late-drafts").json()] == ["HAND-RUN-07"]
    r = op.patch(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json={"complete": True}, headers={"If-Match": "2"})
    assert r.status_code == 200, r.text
    report = _report(owner, shop)
    assert report["conditions"][1]["met"] is False
    assert "vendor-late-draft:HAND-RUN-07" in report["counted_packet_ids"]  # UT-11 late-draft variant via the API
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
    client = TestClient(create_app(settings, store), raise_server_exceptions=False, base_url="https://testserver")
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
                headers={**est._headers(None, "POST"), "Idempotency-Key": f"{tag}-{key}-{ro_id}"},
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


def test_b1_003_round2_counts_raised_after_day7_api(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    """Reviewer n4 through the API: S = 12 supplied by day 7, raised to 30 after day 7."""
    owner, office = api["owner"], api["office"]
    for i in range(10):
        office.post(
            "/baseline-ros",
            json={
                "location_id": str(shop.location_id),
                "ro_label": f"B{i}",
                "closed_month": "2026-07-01",
                "requested_cents": 2000,
                "approved_cents": 1000,
                "collected_cents": 1000,
                "source_note": "synthetic",
            },
        )
    r = office.patch(
        f"/pilots/{shop.pilot_id}/counts",
        json={"baseline_insurer_ro_count": 100, "baseline_supplemented_ro_count": 12, "window_insurer_ro_count": 40},
        headers={"If-Match": "1"},
    )
    assert r.status_code == 200
    # Move the pilot start back 8 days and the first supply into day 3, so the next change lands after day 7.
    _backdate(owner_engine, "UPDATE pilots SET start_date = :d WHERE id = :p", {"d": TODAY - timedelta(days=8), "p": str(shop.pilot_id)})
    _backdate(
        owner_engine,
        "UPDATE pilot_count_events SET recorded_at = :t WHERE pilot_id = :p",
        {"t": f"{TODAY - timedelta(days=6)} 12:00-08:00", "p": str(shop.pilot_id)},
    )
    _backdate(
        owner_engine,
        "UPDATE baseline_ros SET created_at = :t WHERE tenant_id = :x",
        {"t": f"{TODAY - timedelta(days=6)} 12:00-08:00", "x": str(shop.tenant_id)},
    )
    r = office.patch(f"/pilots/{shop.pilot_id}/counts", json={"baseline_supplemented_ro_count": 30}, headers={"If-Match": "2"})
    assert r.status_code == 200 and [e["value"] for e in r.json()["count_history"]] == [100, 12, 40, 30]
    report = _report(owner, shop)
    assert report["conditions"][0]["met"] is True
    assert report["expected_cents"] == 4800  # S = 12 in force at day 7: 12000 / 100 x 40, not S = 30
    assert any("values in force at the end of day 7" in f for f in report["flags"])
    r = office.patch(f"/pilots/{shop.pilot_id}/counts", json={"baseline_supplemented_ro_count": None}, headers={"If-Match": "3"})
    assert _report(owner, shop)["expected_cents"] == 4800  # clearing after day 7 does not change the day-7 value


# Fix after round-3 retest (B1-003 residue) -----------------------------------------------------------
def _late(ro_id: str, ref: str, packet_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ro_id": ro_id,
        "draft_reference": ref,
        "requested_at": f"{TODAY - timedelta(days=6)}T09:00:00-08:00",
        "returned_at": f"{TODAY - timedelta(days=1)}T16:00:00-08:00",
    }
    if packet_id:
        body["packet_id"] = packet_id
    return body


def test_b1_003_round3_late_draft_counts_once_per_repair_order(
    client: TestClient, api: dict[str, Api], shop: Shop, other_shop: Shop, owner_engine: Any
) -> None:
    """Reviewer r3 and r5 through the API: 8 sent with 7 documents, then late rows for one repair order."""
    est, owner, op = api["estimator"], api["owner"], api["operator"]
    _backdate(owner_engine, "UPDATE pilots SET start_date = :d WHERE id = :p", {"d": TODAY - timedelta(days=2), "p": str(shop.pilot_id)})
    sent = []
    for i in range(8):
        ro, _, packet = _sent_ro(est, shop, 10000)
        if i < 7:
            doc = _response_doc(est, packet["packet"]["id"])
            r = _response(
                est, packet["lines"][0], response_status="approved_full", response_date=TODAY.isoformat(), response_document_id=doc
            )
            assert r.status_code == 200, r.text
        sent.append((ro, packet))
    assert op.patch(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json={"complete": True}, headers={"If-Match": "1"}).status_code == 200
    c = _report(owner, shop)["conditions"][2]
    assert c["met"] is True and c["detail"].startswith("7 of 8")
    # A late draft for a repair order whose packet was sent: accepted, but that RO already counts.
    ro0, p0 = sent[0]
    assert (
        op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=_late(ro0["id"], "RO-0 draft", p0["packet"]["id"])).status_code == 201
    )
    assert op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=_late(ro0["id"], "ro-0 draft (again)")).status_code == 409
    report = _report(owner, shop)
    assert report["conditions"][2]["met"] is True and report["conditions"][2]["detail"].startswith("7 of 8")
    assert len(report["counted_packet_ids"]) == 8 and any("not counted again" in f for f in report["flags"])
    # A repair order with no sent packet: one late draft joins (c)'s denominator once; a reworded repeat is refused.
    unsent = create_ro(est, shop)
    assert op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=_late(unsent["id"], "LATE-9")).status_code == 201
    assert op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=_late(unsent["id"], "late-9")).status_code == 409
    report = _report(owner, shop)
    assert report["conditions"][2]["detail"].startswith("7 of 9") and report["conditions"][2]["met"] is False  # UT-11 rule
    assert len(report["counted_packet_ids"]) == 9
    rows = owner.get(f"/pilots/{shop.pilot_id}/vendor-late-drafts").json()
    assert sorted((d["ro_id"], d["packet_id"]) for d in rows) == sorted([(ro0["id"], p0["packet"]["id"]), (unsent["id"], None)])
    # Another tenant's repair order is not found; a packet from another repair order is refused.
    other_ro = create_ro(Api(client, other_shop.tokens["estimator"]), other_shop)
    assert op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=_late(other_ro["id"], "X")).status_code == 404
    ro1, _ = sent[1]
    assert op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json=_late(ro1["id"], "Y", p0["packet"]["id"])).status_code == 422
    assert op.post(f"/pilots/{shop.pilot_id}/vendor-late-drafts", json={**_late(ro1["id"], "Z"), "ro_id": None}).status_code == 422


def test_b1_003_round3_pm1_uses_counts_in_force_at_day90_api(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    """Reviewer r4 through the API: counts changed after day 90 do not move PM-1."""
    owner, office = api["owner"], api["office"]
    for i in range(10):
        office.post(
            "/baseline-ros",
            json={
                "location_id": str(shop.location_id),
                "ro_label": f"B{i}",
                "closed_month": "2026-07-01",
                "requested_cents": 2000,
                "approved_cents": 1000,
                "collected_cents": 1000,
                "source_note": "synthetic",
            },
        )
    r = office.patch(
        f"/pilots/{shop.pilot_id}/counts",
        json={"baseline_insurer_ro_count": 100, "baseline_supplemented_ro_count": 12, "window_insurer_ro_count": 40},
        headers={"If-Match": "1"},
    )
    assert r.status_code == 200
    _backdate(owner_engine, "UPDATE pilots SET start_date = :d WHERE id = :p", {"d": TODAY - timedelta(days=95), "p": str(shop.pilot_id)})
    _backdate(
        owner_engine,
        "UPDATE pilot_count_events SET recorded_at = :t WHERE pilot_id = :p",
        {"t": f"{TODAY - timedelta(days=60)} 12:00-08:00", "p": str(shop.pilot_id)},
    )
    full = owner.get(f"/pilots/{shop.pilot_id}/report").json()
    assert full["pm1_incremental_collected_cents"] == -4800  # 12000 / 100 x 40
    assert not any("day 90" in f for f in full["pm1_flags"])
    for version, value in ((2, 30), (3, 5), (4, None)):
        r = office.patch(
            f"/pilots/{shop.pilot_id}/counts", json={"baseline_supplemented_ro_count": value}, headers={"If-Match": str(version)}
        )
        assert r.status_code == 200, r.text
        full = owner.get(f"/pilots/{shop.pilot_id}/report").json()
        assert full["pm1_incremental_collected_cents"] == -4800, value  # the day-90 value, not the current one
        assert any("in force at the end of day 90" in f for f in full["pm1_flags"])
