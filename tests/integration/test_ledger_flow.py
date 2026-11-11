"""Ledger through the API and database: UT-09, UT-10, UT-17, UT-18, IT-19, E2E-01 (API level), E2E-06."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from sp_files import MemoryObjectStore
from sp_worker.handlers import default_handlers
from sp_worker.runner import Worker
from tests.conftest import JPEG, SYNTHETIC_PDF, TODAY, Api, Shop, approve, approve_all, create_ro, explain, freeze, ro_with_diff


def _mark_sent(est: Api, packet: dict[str, Any], on: str = TODAY.isoformat()) -> Any:
    return est.post(
        f"/packets/{packet['id']}/mark-sent",
        json={
            "sent_on": on,
            "sent_channel": "email",
            "confirm": True,
            "requested_total_cents": packet["requested_total_cents"],
            "line_count": packet["line_count"],
        },
    )


def _manual_ro(est: Api, shop: Shop, amounts: dict[str, int]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    ro = create_ro(est, shop)
    lines = {}
    for name, cents in amounts.items():
        r = est.post(
            f"/ros/{ro['id']}/lines",
            json={
                "origin": "manual",
                "category": "missing_operation",
                "description": f"Operation {name}",
                "requested_cents": cents,
                "explanation": "Synthetic explanation of the needed operation.",
            },
        )
        assert r.status_code == 201, r.text
        lines[name] = r.json()
        assert approve(est, lines[name]).status_code == 200
    return ro, lines


def _response(est: Api, pl: dict[str, Any], **body: Any) -> Any:
    return est.put(f"/packet-lines/{pl['id']}/response", json=body, headers={"If-Match": str(pl["row_version"])})


def _remittance(owner: Api, packet_id: str) -> str:
    r = owner.post(
        f"/packets/{packet_id}/remittance-documents", files={"file": ("r.pdf", SYNTHETIC_PDF + uuid.uuid4().bytes, "application/pdf")}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["document"]["id"])


def test_ut09_response_refused_then_denied(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro, _ = _manual_ro(est, shop, {"A": 15000})
    packet = freeze(est, ro["id"]).json()
    pl = packet["lines"][0]
    r = _response(est, pl, response_status="approved_partial", approved_cents=16000)
    assert r.status_code == 422 and "override reason" in r.json()["detail"]
    r = _response(est, pl, response_status="denied", denial_reason="Not related to loss", response_date="2026-09-20")
    assert r.status_code == 200 and r.json()["approved_cents"] == 0
    assert (
        api["office"]
        .put(f"/packet-lines/{pl['id']}/response", json={"response_status": "no_response"}, headers={"If-Match": "2"})
        .status_code
        == 403
    )


def test_ut17_supersede_carries_response_and_reattributes_payment(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est, owner = api["estimator"], api["owner"]
    ro, lines = _manual_ro(est, shop, {"A": 15000, "B": 9000})
    p1 = freeze(est, ro["id"]).json()
    assert _mark_sent(est, p1["packet"]).status_code == 200
    by_desc = {pl["description"]: pl for pl in p1["lines"]}
    assert _response(est, by_desc["Operation A"], response_status="approved_full", response_date="2026-09-15").status_code == 200
    assert _response(est, by_desc["Operation B"], response_status="denied", denial_reason="Insufficient support").status_code == 200
    remit = _remittance(owner, p1["packet"]["id"])
    pay = owner.post(
        f"/ros/{ro['id']}/payments",
        json={
            "kind": "supplement",
            "packet_id": p1["packet"]["id"],
            "remittance_document_id": remit,
            "payer": "insurer",
            "amount_cents": 15000,
            "paid_on": "2026-09-25",
        },
    )
    assert pay.status_code == 201, pay.text

    # Amend B, re-approve, supersede.
    b = next(x for x in est.get(f"/ros/{ro['id']}/lines").json() if x["id"] == lines["B"]["id"])
    b = est.patch(f"/lines/{b['id']}", json={"requested_cents": 7000}, headers={"If-Match": str(b["row_version"])}).json()
    assert approve(est, b).status_code == 200
    p2 = freeze(est, ro["id"])
    assert p2.status_code == 201, p2.text
    p2 = p2.json()
    assert p2["packet"]["supersedes_packet_id"] == p1["packet"]["id"]
    carried = {pl["description"]: pl for pl in p2["lines"]}
    assert carried["Operation A"]["response_status"] == "approved_full" and carried["Operation A"]["carried_from_packet_line_id"]
    assert carried["Operation B"]["response_status"] == "no_response"
    ledger = est.get(f"/ros/{ro['id']}/ledger").json()
    assert ledger["insurer_approved_cents"] == 15000
    assert ledger["requested_cents"] == 22000
    assert ledger["collected_evidenced_cents"] == 15000
    assert ledger["live_packet_ids"] == [p2["packet"]["id"]]
    assert est.get(f"/packets/{p1['packet']['id']}").json()["packet"]["status"] == "superseded"
    with owner_engine.connect() as conn:
        packet_of_payment = conn.execute(text("SELECT packet_id FROM payments WHERE id = :i"), {"i": pay.json()["id"]}).scalar()
        reattr = conn.execute(
            text("SELECT before, after FROM audit_events WHERE action = 'payment.reattributed' AND entity_id = :i"), {"i": pay.json()["id"]}
        ).first()
    assert str(packet_of_payment) == p2["packet"]["id"]
    assert reattr[0]["packet_id"] == p1["packet"]["id"] and reattr[1]["packet_id"] == p2["packet"]["id"]
    # A response on the superseded packet is refused.
    old_b = by_desc["Operation B"]
    assert (
        _response(est, {**old_b, "row_version": old_b["row_version"] + 1}, response_status="denied", denial_reason="x").status_code == 409
    )


def test_ut18_payment_evidence_reason_and_packet_required(api: dict[str, Api], shop: Shop) -> None:
    est, office = api["estimator"], api["office"]
    ro, _ = _manual_ro(est, shop, {"A": 20000})
    packet = freeze(est, ro["id"]).json()
    _mark_sent(est, packet["packet"])
    assert _response(est, packet["lines"][0], response_status="approved_full").status_code == 200
    remit = _remittance(office, packet["packet"]["id"])
    first = office.post(
        f"/ros/{ro['id']}/payments",
        json={
            "kind": "supplement",
            "packet_id": packet["packet"]["id"],
            "remittance_document_id": remit,
            "payer": "insurer",
            "amount_cents": 20000,
            "paid_on": "2026-09-20",
        },
    )
    assert first.status_code == 201
    second = {"kind": "supplement", "packet_id": packet["packet"]["id"], "payer": "insurer", "amount_cents": 5000, "paid_on": "2026-09-21"}
    refused = office.post(f"/ros/{ro['id']}/payments", json=second)
    assert refused.status_code == 422 and "give a reason" in refused.json()["detail"]
    accepted = office.post(f"/ros/{ro['id']}/payments", json={**second, "over_approved_reason": "Storage paid with the supplement"})
    assert accepted.status_code == 201
    ledger = est.get(f"/ros/{ro['id']}/ledger").json()
    assert ledger["collected_evidenced_cents"] == 20000
    assert ledger["recorded_not_evidenced_cents"] == 5000
    no_packet = office.post(
        f"/ros/{ro['id']}/payments", json={"kind": "supplement", "payer": "insurer", "amount_cents": 100, "paid_on": "2026-09-22"}
    )
    assert no_packet.status_code == 422 and "name the packet" in no_packet.json()["detail"]
    assert est.post(f"/ros/{ro['id']}/payments", json=second).status_code == 403  # Estimator reads payments only


def test_ut10_reversal_and_superseded_requested(api: dict[str, Api], shop: Shop) -> None:
    est, owner = api["estimator"], api["owner"]
    ro, lines = _manual_ro(est, shop, {"A": 30000, "B": 10000})
    p1 = freeze(est, ro["id"]).json()
    b = next(x for x in est.get(f"/ros/{ro['id']}/lines").json() if x["id"] == lines["B"]["id"])
    est.post(f"/lines/{b['id']}/exclude", headers={"If-Match": str(b["row_version"])})
    p2 = freeze(est, ro["id"]).json()
    assert _response(est, p2["lines"][0], response_status="approved_full").status_code == 200
    remit = _remittance(owner, p2["packet"]["id"])
    pay = owner.post(
        f"/ros/{ro['id']}/payments",
        json={
            "kind": "supplement",
            "packet_id": p2["packet"]["id"],
            "remittance_document_id": remit,
            "payer": "insurer",
            "amount_cents": 40000,
            "paid_on": "2026-09-20",
            "over_approved_reason": "Paid with tax",
        },
    ).json()
    rev = owner.post(f"/payments/{pay['id']}/reverse", json={"reason": "Bank returned part", "amount_cents": 5000, "paid_on": "2026-09-21"})
    assert rev.status_code == 201 and rev.json()["amount_cents"] == -5000
    assert owner.post(f"/payments/{pay['id']}/reverse", json={"reason": "again"}).status_code == 409
    ledger = est.get(f"/ros/{ro['id']}/ledger").json()
    assert ledger["requested_cents"] == 30000  # live packet only; p1 (40000 requested) is superseded
    assert ledger["collected_evidenced_cents"] == 35000
    assert p1["packet"]["requested_total_cents"] == 40000
    assert {"requested_cents", "insurer_approved_cents", "collected_evidenced_cents"} <= set(ledger)


def test_payments_cannot_be_edited_or_deleted(api: dict[str, Api], shop: Shop) -> None:
    from tests.integration.test_approval_integrity import _as_app

    owner = api["owner"]
    ro = create_ro(owner, shop)
    pay = owner.post(
        f"/ros/{ro['id']}/payments", json={"kind": "deductible", "payer": "customer", "amount_cents": 50000, "paid_on": "2026-09-02"}
    ).json()
    for stmt in ("UPDATE payments SET amount_cents = 1 WHERE id = :i", "DELETE FROM payments WHERE id = :i"):
        assert _as_app(shop.tenant_id, "owner", shop.users["owner"], stmt, {"i": pay["id"]}) is not None


def test_it19_takedown_purges_files_keeps_amounts(
    settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore, owner_engine: Any
) -> None:
    est, owner = api["estimator"], api["owner"]
    ro, lines = ro_with_diff(est, shop)
    target = lines[0]
    est.post(
        f"/lines/{target['id']}/photos",
        files=[("files", ("s.jpg", JPEG + b"procedure-screenshot", "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    approve_all(est, ro["id"])
    packet = freeze(est, ro["id"]).json()
    worker = Worker(settings, store, default_handlers())
    while worker.run_one() is not None:
        pass
    view = est.get(f"/packets/{packet['packet']['id']}").json()
    pdf_sha = view["packet"]["pdf_sha256"]
    assert pdf_sha
    _mark_sent(est, view["packet"])
    assert _response(est, view["lines"][0], response_status="approved_full").status_code == 200
    ledger_before = est.get(f"/ros/{ro['id']}/ledger").json()
    keys_before = [k for k in store.objects if f"/ro/{ro['id']}/" in k and ("/packet/" in k or "/photo/" in k)]
    assert len(keys_before) == 2
    assert est.post(f"/packets/{packet['packet']['id']}/takedown", json={"reason": "photo is a procedure screenshot"}).status_code == 403
    r = owner.post(f"/packets/{packet['packet']['id']}/takedown", json={"reason": "photo is a procedure screenshot"})
    assert r.status_code == 200, r.text
    assert "cannot be recalled" in r.json()["notice"]
    while worker.run_one() is not None:
        pass
    assert not any(k in store.objects for k in keys_before)
    after = est.get(f"/packets/{packet['packet']['id']}").json()
    assert after["packet"]["pdf_sha256"] == pdf_sha and after["packet"]["purged_at"]
    assert after["packet"]["email_draft"] == "[redacted]"
    assert all(pl["description"] == "[redacted]" and pl["evidence_snapshot"] == {"redacted": True} for pl in after["lines"])
    assert [pl["requested_cents"] for pl in after["lines"]] == [pl["requested_cents"] for pl in view["lines"]]
    ledger_after = est.get(f"/ros/{ro['id']}/ledger").json()
    assert ledger_after == ledger_before
    with owner_engine.connect() as conn:
        actions = list(
            conn.execute(text("SELECT action FROM audit_events WHERE entity_id = :i ORDER BY id"), {"i": packet["packet"]["id"]}).scalars()
        )
    assert actions[:2] == ["packet.frozen", "packet.marked_sent"] and "packet.takedown" in actions


def test_e2e01_core_path_three_totals(settings: Any, api: dict[str, Api], shop: Shop, store: MemoryObjectStore) -> None:
    """API-level E2E-01 (the browser screens are out of B1 scope)."""
    est, office = api["estimator"], api["office"]
    ro, lines = ro_with_diff(est, shop)
    checklist_line = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "missing_operation", "description": "Pre-repair scan", "requested_cents": 15000},
    ).json()
    est.post(
        f"/lines/{checklist_line['id']}/photos",
        files=[("files", ("scan.jpg", JPEG + b"scan", "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    excluded = next(x for x in lines if x["category"] == "part_type_difference")
    est.post(f"/lines/{excluded['id']}/exclude", headers={"If-Match": str(excluded["row_version"])})
    for line in est.get(f"/ros/{ro['id']}/lines").json():
        if line["status"] == "draft":
            if line["id"] != checklist_line["id"]:
                line = explain(est, line)
            assert approve(est, line).status_code == 200
    packet = freeze(est, ro["id"]).json()
    assert {pl["supplement_line_id"] for pl in packet["lines"]} == {
        x["id"] for x in est.get(f"/ros/{ro['id']}/lines").json() if x["status"] == "approved"
    }
    assert excluded["id"] not in {pl["supplement_line_id"] for pl in packet["lines"]}
    worker = Worker(settings, store, default_handlers())
    while worker.run_one() is not None:
        pass
    view = est.get(f"/packets/{packet['packet']['id']}").json()
    pdf = store.objects[next(k for k in store.objects if k.endswith(view["packet"]["pdf_sha256"] + ".pdf"))]
    assert b"Pre-repair scan" in pdf and excluded["description"].encode() not in pdf
    assert _mark_sent(est, view["packet"]).status_code == 200
    for pl in view["lines"]:
        assert _response(est, pl, response_status="approved_full", response_date="2026-09-20").status_code == 200
    remit = _remittance(office, packet["packet"]["id"])
    total = packet["packet"]["requested_total_cents"]
    assert (
        office.post(
            f"/ros/{ro['id']}/payments",
            json={
                "kind": "supplement",
                "packet_id": packet["packet"]["id"],
                "remittance_document_id": remit,
                "payer": "insurer",
                "amount_cents": total - 1000,
                "paid_on": "2026-09-28",
            },
        ).status_code
        == 201
    )
    ledger = est.get(f"/ros/{ro['id']}/ledger").json()
    assert ledger["requested_cents"] == total == 6480 + 3000 + 15000
    assert ledger["insurer_approved_cents"] == total
    assert ledger["collected_evidenced_cents"] == total - 1000
