"""Approval state machine and freeze integrity: UT-07, UT-08, IT-06, IT-18, UT-19 (API), E2E-04.

Highest-consequence error: an unapproved or unsupported line reaches an insurer.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from sqlalchemy import create_engine, text

from tests.conftest import (
    APP_URL,
    INSURER_LINES,
    JPEG,
    SHOP_LINES,
    Api,
    Shop,
    approve,
    approve_all,
    enter_lines,
    explain,
    freeze,
    ro_with_diff,
    upload_estimate,
)


def _lines(user: Api, ro_id: str) -> dict[str, dict[str, Any]]:
    return {x["id"]: x for x in user.get(f"/ros/{ro_id}/lines").json()}


def _audit_actions(owner_engine: Any, entity_id: str) -> list[str]:
    with owner_engine.connect() as conn:
        return list(conn.execute(text("SELECT action FROM audit_events WHERE entity_id = :e ORDER BY id"), {"e": entity_id}).scalars())


def _approved_line_with_evidence(est: Api, ro_id: str, line: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    photo = est.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("a.jpg", JPEG + uuid.uuid4().bytes, "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    assert photo.status_code == 200, photo.text
    photo_id = photo.json()["results"][0]["photo_id"]
    ref = est.post(
        f"/lines/{line['id']}/references",
        json={
            "material_type": "oem_position_statement",
            "publisher": "Synthetic OEM",
            "title": "Position statement on scans",
            "identifier": "PS-01",
            "url": "https://oem.example.test/ps-01",
            "accessed_on": "2026-11-01",
        },
    )
    assert ref.status_code == 201, ref.text
    current = _lines(est, ro_id)[line["id"]]
    r = approve(est, current)
    assert r.status_code == 200, r.text
    return r.json(), photo_id, ref.json()["reference"]["id"]


def _assert_reset(est: Api, ro_id: str, line_id: str, before_version: int, owner_engine: Any) -> dict[str, Any]:
    after = _lines(est, ro_id)[line_id]
    assert after["status"] == "draft"
    assert after["approved_by"] is None and after["approved_fingerprint"] is None
    assert after["row_version"] > before_version
    assert _audit_actions(owner_engine, line_id)[-1] in (
        "line.approval_reset",
        "line.edited",
        "evidence.removed",
        "evidence.photo_attached",
        "reference.edited",
    )
    assert "line.approval_reset" in _audit_actions(owner_engine, line_id)
    return after


def test_ut07_every_change_resets_approval(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est = api["estimator"]
    ro, lines = ro_with_diff(est, shop)
    target = next(x for x in lines if x["category"] == "labor_hours_gap")
    other = next(x for x in lines if x["category"] == "missing_operation")
    other_approved = approve(est, explain(est, other)).json()

    def reapprove() -> dict[str, Any]:
        current = _lines(est, ro["id"])[target["id"]]
        r = approve(est, current)
        assert r.status_code == 200, r.text
        return r.json()

    approved, photo_id, ref_id = _approved_line_with_evidence(est, ro["id"], target)

    # 1. change amount
    r = est.patch(f"/lines/{target['id']}", json={"requested_cents": 3100}, headers={"If-Match": str(approved["row_version"])})
    assert r.status_code == 200
    _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)
    approved = reapprove()

    # 2. add a photo
    r = est.post(
        f"/lines/{target['id']}/photos",
        files=[("files", ("b.jpg", JPEG + b"second", "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    assert r.status_code == 200 and r.json()["attached"] == 1
    _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)
    approved = reapprove()

    # 3. delete the photo
    second_ev = r.json()["results"][0]["evidence_id"]
    assert est.delete(f"/evidence/{second_ev}").status_code == 200
    _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)
    approved = reapprove()

    # 4. edit the reference
    with owner_engine.connect() as conn:
        ref_version = conn.execute(text("SELECT row_version FROM reference_citations WHERE id = :i"), {"i": ref_id}).scalar()
    r = est.patch(f"/references/{ref_id}", json={"title": "Position statement on pre-repair scans"}, headers={"If-Match": str(ref_version)})
    assert r.status_code == 200, r.text
    _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)
    approved = reapprove()

    # 5. change the attestation
    with owner_engine.connect() as conn:
        photo_version = conn.execute(text("SELECT row_version FROM photos WHERE id = :i"), {"i": photo_id}).scalar()
    r = est.patch(
        f"/photos/{photo_id}",
        json={"attested": True, "taken_by_shop": False, "attestation_note": "Taken by the vehicle owner"},
        headers={"If-Match": str(photo_version)},
    )
    assert r.status_code == 200, r.text
    _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)
    approved = reapprove()

    # 6. correct the linked shop estimate line
    with owner_engine.connect() as conn:
        shop_line_id, ev = conn.execute(
            text("SELECT e.id, e.row_version FROM estimate_lines e JOIN supplement_lines s ON s.shop_line_id = e.id WHERE s.id = :i"),
            {"i": target["id"]},
        ).first()
    r = est.patch(f"/estimate-lines/{shop_line_id}", json={"labor_hours": "2.6", "line_total_cents": 15600}, headers={"If-Match": str(ev)})
    assert r.status_code == 200, r.text
    _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)

    # 7. re-run the comparison with a changed source: requested amount changes, line returns to draft
    r = est.post(f"/documents/{r.json()['parse_run']['document_id']}/reconcile", json={"reason": "printed total corrected by hand"})
    assert r.status_code == 200, r.text
    approved = reapprove()
    rerun = est.post(f"/ros/{ro['id']}/diff")
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["lines_changed"] >= 1
    after = _assert_reset(est, ro["id"], target["id"], approved["row_version"], owner_engine)
    assert after["requested_cents"] == 3600  # 0.6 h x 6000

    # The unrelated approved line is untouched throughout.
    untouched = _lines(est, ro["id"])[other["id"]]
    assert untouched["status"] == "approved" and untouched["row_version"] == other_approved["row_version"]


def test_ut07_unchanged_rerun_keeps_approval(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    before = _lines(est, ro["id"])
    rerun = est.post(f"/ros/{ro['id']}/diff").json()
    assert rerun["lines_changed"] == 0 and rerun["lines_created"] == 0
    assert _lines(est, ro["id"]) == before


def test_ut08_freeze_refused_listing_draft_and_needs_review(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    from tests.conftest import create_ro

    ro = create_ro(est, shop)
    ins = upload_estimate(est, ro["id"], "insurer_estimate")
    sh = upload_estimate(est, ro["id"], "shop_estimate")
    enter_lines(est, ins["id"], INSURER_LINES)
    enter_lines(
        est, sh["id"], [*SHOP_LINES[:1], {"operation": "other", "description": "Additional labour as discussed", "line_total_cents": 9000}]
    )
    assert est.post(f"/ros/{ro['id']}/diff").status_code == 200
    lines = est.get(f"/ros/{ro['id']}/lines").json()
    assert {x["match_state"] for x in lines} == {"matched", "needs_review"}
    r = freeze(est, ro["id"])
    assert r.status_code == 409
    items = {p["item"] for p in r.json()["problems"]}
    assert items == {f"line:{x['id']}" for x in lines}
    # needs_review cannot be approved, but it does not block the other line once excluded
    review_line = next(x for x in lines if x["match_state"] == "needs_review")
    assert approve(est, review_line).status_code == 422
    assert est.post(f"/lines/{review_line['id']}/exclude", headers={"If-Match": str(review_line["row_version"])}).status_code == 200
    approve_all(est, ro["id"])
    assert freeze(est, ro["id"]).status_code == 201


def test_it06_operator_edit_during_freeze_is_refused(api: dict[str, Api], shop: Shop) -> None:
    est, op = api["estimator"], api["operator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    review = est.get(f"/ros/{ro['id']}/packet-review").json()
    line = next(x for x in review["lines"] if x["category"] == "labor_hours_gap")
    r = op.patch(f"/lines/{line['id']}", json={"requested_cents": 99999}, headers={"If-Match": str(line["row_version"])})
    assert r.status_code == 200  # the Operator may edit, never approve
    r = est.post(
        f"/ros/{ro['id']}/packets",
        json={"review_fingerprint": review["review_fingerprint"], "review_components": review["review_components"]},
    )
    assert r.status_code == 409
    assert {"item": f"line:{line['id']}", "reason": "not approved"} in r.json()["problems"]
    assert est.get(f"/ros/{ro['id']}/ledger").json()["live_packet_ids"] == []


def test_it06_concurrent_edit_waits_for_lock_then_freeze_refuses(api: dict[str, Api], shop: Shop) -> None:
    """The edit holds the row lock; freeze's SELECT FOR UPDATE waits and then sees the change."""
    est = api["estimator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    review = est.get(f"/ros/{ro['id']}/packet-review").json()
    line_id = next(x["id"] for x in review["lines"] if x["category"] == "labor_hours_gap")
    engine = create_engine(APP_URL)
    conn = engine.connect()
    tx = conn.begin()
    conn.execute(
        text("SELECT set_config('app.tenant_id', :t, true), set_config('app.actor_role', 'operator', true)"), {"t": str(shop.tenant_id)}
    )
    conn.execute(text("UPDATE supplement_lines SET requested_cents = requested_cents + 1 WHERE id = :i"), {"i": line_id})
    result: dict[str, Any] = {}

    def do_freeze() -> None:
        result["r"] = est.post(
            f"/ros/{ro['id']}/packets",
            json={"review_fingerprint": review["review_fingerprint"], "review_components": review["review_components"]},
        )

    worker = threading.Thread(target=do_freeze)
    worker.start()
    time.sleep(0.5)
    assert worker.is_alive(), "freeze must wait for the line lock"
    tx.commit()
    worker.join(10)
    conn.close()
    engine.dispose()
    assert result["r"].status_code == 409
    assert any(p["item"] == f"line:{line_id}" for p in result["r"].json()["problems"])


def test_it18_photo_swap_or_email_edit_after_review_refused(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est, op = api["estimator"], api["operator"]
    ro, lines = ro_with_diff(est, shop)
    target = next(x for x in lines if x["category"] == "missing_operation")
    _, photo_id, _ = _approved_line_with_evidence(est, ro["id"], target)
    approve_all(est, ro["id"])
    review = est.get(f"/ros/{ro['id']}/packet-review").json()

    # Operator replaces the line's photo.
    with owner_engine.connect() as conn:
        ev_id = conn.execute(text("SELECT id FROM line_evidence WHERE photo_id = :p"), {"p": photo_id}).scalar()
    assert op.delete(f"/evidence/{ev_id}").status_code == 200
    r = op.post(
        f"/lines/{target['id']}/photos",
        files=[("files", ("c.jpg", JPEG + b"replacement", "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    assert r.status_code == 200
    r = est.post(
        f"/ros/{ro['id']}/packets",
        json={"review_fingerprint": review["review_fingerprint"], "review_components": review["review_components"]},
    )
    assert r.status_code == 409
    assert f"line:{target['id']}" in r.json()["changed"]
    assert _lines(est, ro["id"])[target["id"]]["status"] == "draft"

    # Re-approve, fresh review, then the Operator edits the email paragraph.
    approve_all(est, ro["id"])
    review = est.get(f"/ros/{ro['id']}/packet-review").json()
    ro_now = est.get(f"/ros/{ro['id']}").json()
    assert (
        op.patch(
            f"/ros/{ro['id']}", json={"email_free_paragraph": "Please call the shop."}, headers={"If-Match": str(ro_now["row_version"])}
        ).status_code
        == 200
    )
    r = est.post(
        f"/ros/{ro['id']}/packets",
        json={"review_fingerprint": review["review_fingerprint"], "review_components": review["review_components"]},
    )
    assert r.status_code == 409 and r.json()["changed"] == ["email_draft"]

    # After a fresh review the freeze succeeds.
    r = freeze(est, ro["id"])
    assert r.status_code == 201, r.text
    packet = r.json()
    assert packet["packet"]["line_count"] == 3
    assert "Please call the shop." in packet["packet"]["email_draft"]


def test_ut19_email_draft_with_other_amount_refused(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    ro_now = est.get(f"/ros/{ro['id']}").json()
    est.patch(
        f"/ros/{ro['id']}",
        json={"email_free_paragraph": "We also ask for USD 1,500 storage."},
        headers={"If-Match": str(ro_now["row_version"])},
    )
    r = freeze(est, ro["id"])
    assert r.status_code == 422 and "USD 1,500" in r.json()["detail"]
    ro_now = est.get(f"/ros/{ro['id']}").json()
    est.patch(
        f"/ros/{ro['id']}",
        json={"email_free_paragraph": "Photos are attached for each line."},
        headers={"If-Match": str(ro_now["row_version"])},
    )
    assert freeze(est, ro["id"]).status_code == 201


def test_e2e04_double_submit_creates_one_packet(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    review = est.get(f"/ros/{ro['id']}/packet-review").json()
    body = {"review_fingerprint": review["review_fingerprint"], "review_components": review["review_components"]}
    headers = {"Idempotency-Key": "freeze-click-1"}
    first = est.post(f"/ros/{ro['id']}/packets", json=body, headers=headers)
    second = est.post(f"/ros/{ro['id']}/packets", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["packet"]["id"] == second.json()["packet"]["id"]
    third = est.post(f"/ros/{ro['id']}/packets", json=body)  # new key, nothing changed
    assert third.status_code == 409


def _as_app(tenant_id: uuid.UUID, role: str, user_id: uuid.UUID | None, stmt: str, params: dict[str, Any]) -> Exception | None:
    """Run one statement as the application role in its own transaction; return the refusal."""
    engine = create_engine(APP_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "SELECT set_config('app.tenant_id', :t, true), set_config('app.actor_role', :r, true), set_config('app.user_id', :u, true)"
                ),
                {"t": str(tenant_id), "r": role, "u": str(user_id) if user_id else ""},
            )
            conn.execute(text(stmt), params)
    except Exception as exc:
        return exc
    finally:
        engine.dispose()
    return None


def test_frozen_packet_rows_are_immutable(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    packet_id = freeze(est, ro["id"]).json()["packet"]["id"]
    for stmt in (
        "UPDATE packets SET requested_total_cents = 1 WHERE id = :i",
        "UPDATE packets SET email_draft = 'changed' WHERE id = :i",
        "UPDATE packet_lines SET requested_cents = 1 WHERE packet_id = :i",
        "UPDATE packet_lines SET description = 'changed' WHERE packet_id = :i",
        "DELETE FROM packets WHERE id = :i",
        "DELETE FROM packet_lines WHERE packet_id = :i",
    ):
        refusal = _as_app(shop.tenant_id, "owner", shop.users["owner"], stmt, {"i": packet_id})
        assert refusal is not None, f"frozen packet changed: {stmt}"
        assert (
            "permission denied" in str(refusal)
            or "cannot change" in str(refusal)
            or "immutable" in str(refusal)
            or "takedown" in str(refusal)
        )


def test_worker_and_operator_cannot_approve_or_freeze_in_the_database(shop: Shop, api: dict[str, Api]) -> None:
    est = api["estimator"]
    ro, lines = ro_with_diff(est, shop)
    line = explain(est, lines[0])
    approve_sql = (
        "UPDATE supplement_lines SET status='approved', approved_by=:u, approved_at=now(), approved_row_version=row_version, "
        "approved_fingerprint='\\x00' WHERE id = :i"
    )
    for role, user in (("worker", None), ("operator", shop.users["operator"]), ("office", shop.users["office"])):
        refusal = _as_app(shop.tenant_id, role, user, approve_sql, {"i": line["id"], "u": str(user or shop.users["estimator"])})
        assert refusal is not None and "only an Owner or Estimator" in str(refusal), role
    freeze_sql = (
        "INSERT INTO packets (tenant_id, ro_id, version, review_fingerprint, requested_total_cents, line_count, email_draft, frozen_by) "
        "VALUES (:t, :r, 99, '\\x00', 1, 1, 'x', :u)"
    )
    for role, user in (("worker", shop.users["estimator"]), ("operator", shop.users["operator"])):
        refusal = _as_app(shop.tenant_id, role, user, freeze_sql, {"t": str(shop.tenant_id), "r": ro["id"], "u": str(user)})
        assert refusal is not None and "only an Owner or Estimator" in str(refusal), role
    # a new line can never be inserted already approved
    refusal = _as_app(
        shop.tenant_id,
        "estimator",
        shop.users["estimator"],
        "INSERT INTO supplement_lines (tenant_id, ro_id, origin, category, description, requested_cents, status) "
        "VALUES (:t, :r, 'manual', 'other', 'x', 1, 'approved')",
        {"t": str(shop.tenant_id), "r": ro["id"]},
    )
    assert refusal is not None and "nothing is auto-approved" in str(refusal)
