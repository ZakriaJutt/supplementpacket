"""Tenant isolation and permissions: IT-01, IT-02, IT-12, IT-15, IT-16, plus the zero-rows check."""

from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from sp_db.models import TENANT_TABLES
from sp_files import MemoryObjectStore
from sp_worker.handlers import default_handlers
from sp_worker.runner import Worker
from tests.conftest import APP_URL, JPEG, SYNTHETIC_PDF, Api, Shop, approve_all, freeze, ro_with_diff


def _build_b(api_b: Api, shop_b: Shop, owner_engine: Any) -> dict[str, str]:
    ro, lines = ro_with_diff(api_b, shop_b)
    line = lines[0]
    photo = api_b.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("p.jpg", JPEG + b"b-shop", "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    ).json()["results"][0]
    ref = api_b.post(
        f"/lines/{line['id']}/references",
        json={"material_type": "industry_body", "publisher": "Synthetic body", "title": "Guidance", "accessed_on": "2026-11-01"},
    ).json()
    approve_all(api_b, ro["id"])
    packet = freeze(api_b, ro["id"]).json()
    owner_b = Api(api_b.client, shop_b.tokens["owner"])
    pay = owner_b.post(
        f"/ros/{ro['id']}/payments", json={"kind": "original_estimate", "payer": "insurer", "amount_cents": 1000, "paid_on": "2026-11-02"}
    )
    with owner_engine.connect() as conn:
        doc_id = conn.execute(text("SELECT id FROM documents WHERE ro_id = :r LIMIT 1"), {"r": ro["id"]}).scalar()
        est_line = conn.execute(
            text(
                "SELECT e.id FROM estimate_lines e JOIN parse_runs p ON p.id = e.parse_run_id JOIN documents d ON d.id = p.document_id "
                "WHERE d.ro_id = :r LIMIT 1"
            ),
            {"r": ro["id"]},
        ).scalar()
        job_id = conn.execute(text("SELECT id FROM jobs WHERE tenant_id = :t LIMIT 1"), {"t": str(shop_b.tenant_id)}).scalar()
    return {
        "ro_id": ro["id"],
        "document_id": str(doc_id),
        "estimate_line_id": str(est_line),
        "line_id": line["id"],
        "job_id": str(job_id),
        "photo_id": photo["photo_id"],
        "evidence_id": photo["evidence_id"],
        "reference_id": ref["reference"]["id"],
        "packet_id": packet["packet"]["id"],
        "packet_line_id": packet["lines"][0]["id"],
        "payment_id": pay.json()["id"],
        "pilot_id": str(shop_b.pilot_id),
    }


def _call(user: Api, method: str, path: str) -> Any:
    kwargs: dict[str, Any] = {}
    if path.endswith("/documents") and method == "POST":
        kwargs = {
            "data": {"purpose": "insurer_estimate"},
            "files": {"file": ("x.pdf", SYNTHETIC_PDF + uuid.uuid4().bytes, "application/pdf")},
        }
    elif path.endswith(("-documents",)):
        kwargs = {"files": {"file": ("x.pdf", SYNTHETIC_PDF + uuid.uuid4().bytes, "application/pdf")}}
    elif path.endswith("/photos") and method == "POST":
        kwargs = {"files": [("files", ("x.jpg", JPEG, "image/jpeg"))], "data": {"attested": "true", "taken_by_shop": "true"}}
    elif method in ("POST", "PATCH", "PUT"):
        kwargs = {"json": {}, "headers": {"If-Match": "1"}}
    elif path.endswith("/download"):
        path += "?expires=9999999999&sig=x"
    return getattr(user, method.lower())(path, **kwargs)


def test_it01_every_endpoint_returns_404_for_another_tenants_ids(
    client: TestClient, api: dict[str, Api], shop: Shop, other_shop: Shop, owner_engine: Any
) -> None:
    api_b = Api(client, other_shop.tokens["estimator"])
    b = _build_b(api_b, other_shop, owner_engine)
    a_owner = api["owner"]
    routes = [r for r in client.app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]  # type: ignore[attr-defined]
    checked = 0
    for route in routes:
        params = re.findall(r"{(\w+)}", route.path)
        if not params:
            continue
        path = route.path.removeprefix("/api/v1")
        for name in params:
            key = "estimate_line_id" if (name == "line_id" and path.startswith("/estimate-lines")) else name
            path = path.replace("{" + name + "}", b[key])
        for method in sorted(route.methods):
            response = _call(a_owner, method, path)
            assert response.status_code == 404, f"{method} {route.path} -> {response.status_code} {response.text}"
            checked += 1
    assert checked >= 35
    # Body references to another tenant's rows are 404 too.
    r = a_owner.post("/ros", json={"location_id": str(other_shop.location_id), "ro_number": "X"})
    assert r.status_code == 404
    r = a_owner.post(
        "/baseline-ros",
        json={"location_id": str(other_shop.location_id), "ro_label": "X", "closed_month": "2026-08-01", "source_note": "synthetic"},
    )
    assert r.status_code == 404
    assert all(ro["tenant_id"] == str(shop.tenant_id) for ro in a_owner.get("/ros").json())
    # Nothing of B's changed.
    assert api_b.get(f"/packets/{b['packet_id']}").json()["packet"]["status"] == "frozen"


def test_it01_worker_refuses_job_naming_another_tenants_file(
    settings: Any, client: TestClient, api: dict[str, Api], shop: Shop, other_shop: Shop, owner_engine: Any, store: MemoryObjectStore
) -> None:
    api_b = Api(client, other_shop.tokens["estimator"])
    b = _build_b(api_b, other_shop, owner_engine)
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET state = 'succeeded' WHERE state = 'queued'"))  # isolate this test's job
        job_id = conn.execute(
            text(
                "INSERT INTO jobs (tenant_id, kind, subject_id, idempotency_key, correlation_id) "
                "VALUES (:t, 'parse_document', :s, :k, gen_random_uuid()) RETURNING id"
            ),
            {"t": str(shop.tenant_id), "s": b["document_id"], "k": uuid.uuid4().hex},
        ).scalar()
    worker = Worker(settings, store, default_handlers())
    claimed = worker.run_one()
    assert claimed is not None and str(claimed.job_id) == str(job_id)
    with owner_engine.connect() as conn:
        state, code = conn.execute(text("SELECT state, error_code FROM jobs WHERE id = :i"), {"i": job_id}).first()
        runs = conn.execute(text("SELECT count(*) FROM parse_runs WHERE tenant_id = :t"), {"t": str(shop.tenant_id)}).scalar()
    assert (state, code) == ("failed", "not_found")
    assert runs == 0


def test_rls_without_tenant_context_reads_zero_rows(api: dict[str, Api], shop: Shop) -> None:
    ro_with_diff(api["estimator"], shop)
    engine = create_engine(APP_URL)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar() is False
        for table in (*TENANT_TABLES, "tenants"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table
        conn.execute(text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(shop.tenant_id)})
        assert conn.execute(text("SELECT count(*) FROM supplement_lines")).scalar() > 0
    engine.dispose()


def test_rls_refuses_writes_into_another_tenant(shop: Shop, other_shop: Shop) -> None:
    engine = create_engine(APP_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(shop.tenant_id)})
            conn.execute(text("INSERT INTO insurers (tenant_id, name) VALUES (:t, 'x')"), {"t": str(other_shop.tenant_id)})
    except Exception as exc:
        assert "row-level security" in str(exc)
    else:
        raise AssertionError("cross-tenant insert accepted")
    finally:
        engine.dispose()


def test_it02_office_and_operator_cannot_approve_exclude_freeze_or_mark_sent(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est = api["estimator"]
    ro, _lines = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    packet = freeze(est, ro["id"]).json()["packet"]
    draft_line = est.post(
        f"/ros/{ro['id']}/lines",
        json={
            "origin": "manual",
            "category": "other",
            "description": "Corrosion protection",
            "requested_cents": 2500,
            "explanation": "Required after welding per shop practice.",
        },
    ).json()
    for role in ("office", "operator"):
        user = api[role]
        attempts = [
            user.post(f"/lines/{draft_line['id']}/approve", headers={"If-Match": str(draft_line["row_version"])}),
            user.post(f"/lines/{draft_line['id']}/exclude", headers={"If-Match": str(draft_line["row_version"])}),
            user.post(f"/ros/{ro['id']}/packets", json={"review_fingerprint": "x", "review_components": {}}),
            user.post(
                f"/packets/{packet['id']}/mark-sent",
                json={
                    "sent_on": "2026-11-10",
                    "sent_channel": "email",
                    "confirm": True,
                    "requested_total_cents": packet["requested_total_cents"],
                    "line_count": packet["line_count"],
                },
            ),
            user.post(f"/packets/{packet['id']}/unmark-sent", json={"reason": "x"}),
        ]
        assert [a.status_code for a in attempts] == [403] * 5, (role, [a.text for a in attempts])
    assert est.get(f"/ros/{ro['id']}/lines").json()[-1]["status"] == "draft"
    assert est.get(f"/packets/{packet['id']}").json()["packet"]["status"] == "frozen"
    with owner_engine.connect() as conn:
        denials = conn.execute(
            text("SELECT actor_kind, count(*) FROM audit_events WHERE tenant_id = :t AND action = 'permission.denied' GROUP BY actor_kind"),
            {"t": str(shop.tenant_id)},
        ).all()
    assert dict(denials) == {"user": 5, "operator": 5}


def test_operator_without_grant_sees_nothing(api: dict[str, Api], shop: Shop) -> None:
    ro, _ = ro_with_diff(api["estimator"], shop)
    assert api["operator_nogrant"].get(f"/ros/{ro['id']}").status_code == 404
    assert api["operator_nogrant"].get("/ros").status_code == 404


def test_it16_audit_events_are_append_only(api: dict[str, Api], shop: Shop) -> None:
    ro_with_diff(api["estimator"], shop)
    engine = create_engine(APP_URL)
    for stmt in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"):
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(shop.tenant_id)})
                conn.execute(text(stmt))
        except Exception as exc:
            assert "permission denied" in str(exc) or "append-only" in str(exc)
        else:
            raise AssertionError(f"audit row changed: {stmt}")
    engine.dispose()


def test_it15_licensed_material_controls(client: TestClient, api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro, lines = ro_with_diff(est, shop)
    line = lines[0]
    base = {"publisher": "Synthetic OEM", "title": "Bumper repair procedure", "identifier": "PROC-77", "accessed_on": "2026-11-01"}
    refused = est.post(
        f"/lines/{line['id']}/references",
        json={**base, "material_type": "oem_procedure_subscription", "url": "https://portal.example.test/proc-77"},
    )
    assert refused.status_code == 422 and "URL is not accepted" in refused.json()["detail"]
    guide = est.post(f"/lines/{line['id']}/references", json={**base, "material_type": "estimating_guide", "url": "https://g.example.test"})
    assert guide.status_code == 422
    accepted = est.post(f"/lines/{line['id']}/references", json={**base, "material_type": "oem_procedure_subscription"})
    assert accepted.status_code == 201
    no_tick = est.post(
        f"/lines/{line['id']}/photos", files=[("files", ("x.jpg", JPEG + b"1", "image/jpeg"))], data={"taken_by_shop": "true"}
    )
    assert no_tick.status_code == 422
    pdf_as_photo = est.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("x.jpg", SYNTHETIC_PDF, "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    assert pdf_as_photo.json()["rejected"] == 1
    paths = {r.path for r in client.app.routes if isinstance(r, APIRoute)}  # type: ignore[attr-defined]
    assert not any(re.search(r"procedure|send|transmit|deliver|insurer-portal|email", p) for p in paths), paths
    bad_purpose = est.post(
        f"/ros/{ro['id']}/documents", data={"purpose": "procedure"}, files={"file": ("p.pdf", SYNTHETIC_PDF + b"p", "application/pdf")}
    )
    assert bad_purpose.status_code == 422


def test_it12_signed_link_uses_public_base_url(
    settings: Any, client: TestClient, api: dict[str, Api], shop: Shop, store: MemoryObjectStore
) -> None:
    est = api["estimator"]
    ro, _ = ro_with_diff(est, shop)
    approve_all(est, ro["id"])
    packet = freeze(est, ro["id"]).json()
    worker = Worker(settings, store, default_handlers())
    while worker.run_one() is not None:
        pass
    r = est.get(f"/packets/{packet['packet']['id']}/pdf", headers={"Host": "api.internal:8103", "X-Forwarded-Host": "10.0.0.5"})
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["url"])
    assert f"{url.scheme}://{url.netloc}" == settings.public_base_url
    download = est.get(f"{url.path.removeprefix('/api/v1')}?{url.query}")
    assert download.status_code == 200 and download.content.startswith(b"%PDF-")
