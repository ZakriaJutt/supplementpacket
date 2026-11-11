"""B2 sign-in against the real path: invitation and reset email through Mailpit, password, TOTP,
server sessions, anti-forgery, logout, expiry, revocation, rate limits (T-2.2.2, TRD 8.2).

Needs the local Mailpit (SMTP 127.0.0.1:1025, API http://127.0.0.1:8025). Every address is
unique per test, and only the messages these tests read are deleted afterwards.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sp_api.main import create_app
from sp_core.auth import TOTP_STEP_SECONDS, totp_code
from sp_files import MemoryObjectStore
from tests.conftest import Api, Shop

MAILPIT = "http://127.0.0.1:8025/api/v1"


@pytest.fixture()
def mailbox() -> Iterator[list[str]]:
    """Message IDs read by the test; deleted at the end (other projects share this Mailpit)."""
    try:
        httpx.get(f"{MAILPIT}/messages", params={"limit": 1}, timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Mailpit is not running on 127.0.0.1:8025")
    seen: list[str] = []
    yield seen
    if seen:
        httpx.request("DELETE", f"{MAILPIT}/messages", json={"IDs": seen}, timeout=5)


def _read_link(mailbox: list[str], to: str, path: str) -> str:
    """Wait for the message to ``to`` and return the token from its ``/{path}#token=<token>`` link."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        found = httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{to}"'}, timeout=5).json()["messages"]
        if found:
            mid = found[0]["ID"]
            mailbox.append(mid)
            body = httpx.get(f"{MAILPIT}/message/{mid}", timeout=5).json()["Text"]
            # The token is in the URL fragment (never sent to a server); no token in any path (B2-S03).
            match = re.search(rf"https://app\.example\.test/{path}#token=([A-Za-z0-9_\-]+)", body)
            assert match, body
            return match.group(1)
        time.sleep(0.2)
    raise AssertionError(f"no email to {to}")


def _browser(settings: Any, store: MemoryObjectStore) -> TestClient:
    return TestClient(create_app(settings, store), raise_server_exceptions=True, base_url="https://testserver")


def _code(secret: str, offset: int = 0) -> str:
    return totp_code(secret, int(time.time() // TOTP_STEP_SECONDS) + offset)


def _invite_and_accept(
    owner: Api, mailbox: list[str], role: str, *, with_totp: bool = True, password: str = "correct horse battery 42"
) -> tuple[str, str | None, str]:
    """Owner invites; the invitee reads the email, sets up TOTP and accepts. Returns email, secret, token."""
    email = f"{role}.{uuid.uuid4().hex[:10]}@example.test"
    r = owner.post("/users", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    token = _read_link(mailbox, email, "invite")
    anon = owner.client
    view = anon.post("/api/v1/invites/lookup", json={"token": token})
    assert view.status_code == 200 and view.json()["role"] == role
    secret = None
    body: dict[str, Any] = {"password": password, "display_name": f"Synthetic {role}"}
    if with_totp:
        setup = anon.post("/api/v1/invites/totp-setup", json={"token": token})
        assert setup.status_code == 200 and setup.json()["otpauth_uri"].startswith("otpauth://totp/")
        secret = setup.json()["secret"]
        body["totp_code"] = _code(secret)
    r = anon.post("/api/v1/invites/accept", json={"token": token, **body})
    assert r.status_code == 201, r.text
    assert "set-cookie" not in r.headers  # accepting does not sign in (S-02 -> S-01)
    return email, secret, token


def _sign_in(browser: TestClient, email: str, password: str, secret: str | None, offset: int = 1) -> dict[str, Any]:
    r = browser.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    if body["next"] == "totp":
        assert secret is not None
        r = browser.post("/api/v1/auth/totp", json={"code": _code(secret, offset)}, headers={"X-CSRF-Token": body["csrf_token"]})
        assert r.status_code == 200, r.text
        body = r.json()
    assert body["next"] == "done"
    return body


def test_b2_invite_sign_in_logout_end_to_end(
    settings: Any, store: MemoryObjectStore, api: dict[str, Api], shop: Shop, mailbox: list[str]
) -> None:
    owner = api["owner"]
    assert api["estimator"].post("/users", json={"email": "x.y@example.test", "role": "office"}).status_code == 403  # Owner only
    email, secret, _ = _invite_and_accept(owner, mailbox, "estimator")
    assert secret is not None
    browser = _browser(settings, store)
    r = browser.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery 42"})
    assert r.status_code == 200 and r.json()["next"] == "totp"
    cookie = r.headers["set-cookie"]
    for attribute in ("__Host-sp_session=", "Secure", "HttpOnly", "SameSite=lax", "Path=/"):
        assert attribute in cookie, cookie
    assert "Domain" not in cookie
    pending_csrf = r.json()["csrf_token"]
    assert browser.get("/api/v1/auth/session").status_code == 401  # the password step alone reaches nothing
    assert browser.get("/api/v1/ros").status_code == 401
    assert browser.post("/api/v1/auth/totp", json={"code": _code(secret, 1)}).status_code == 403  # no anti-forgery header
    r = browser.post("/api/v1/auth/totp", json={"code": _code(secret, 1)}, headers={"X-CSRF-Token": pending_csrf})
    assert r.status_code == 200, r.text
    full_csrf = r.json()["csrf_token"]
    assert full_csrf != pending_csrf  # a new session token on authentication
    me = browser.get("/api/v1/auth/session").json()
    assert me["role"] == "estimator" and me["tenant_id"] == str(shop.tenant_id) and me["csrf_token"] == full_csrf
    body = {"location_id": str(shop.location_id), "ro_number": f"RO-{uuid.uuid4().hex[:6]}"}
    assert browser.post("/api/v1/ros", json=body, headers={"Idempotency-Key": "b2-1"}).status_code == 403  # no CSRF header
    bad = {"Idempotency-Key": "b2-1", "X-CSRF-Token": full_csrf, "Origin": "https://evil.example"}
    assert browser.post("/api/v1/ros", json=body, headers=bad).status_code == 403  # foreign origin
    ok = browser.post("/api/v1/ros", json=body, headers={"Idempotency-Key": "b2-1", "X-CSRF-Token": full_csrf})
    assert ok.status_code == 201, ok.text
    stolen = browser.cookies.get("__Host-sp_session")
    r = browser.post("/api/v1/auth/logout", headers={"X-CSRF-Token": full_csrf})
    assert r.status_code == 200 and "Clear-Site-Data" in r.headers
    assert browser.get("/api/v1/auth/session").status_code == 401
    replay = _browser(settings, store)
    assert replay.get("/api/v1/ros", headers={"Cookie": f"__Host-sp_session={stolen}"}).status_code == 401  # ended server-side


def test_b2_expired_and_reused_invite_and_code_refused(
    settings: Any, store: MemoryObjectStore, api: dict[str, Api], shop: Shop, mailbox: list[str], owner_engine: Any
) -> None:
    owner = api["owner"]
    email, secret, token = _invite_and_accept(owner, mailbox, "owner")
    assert secret is not None
    again = owner.client.post(
        "/api/v1/invites/accept", json={"token": token, "password": "correct horse battery 42", "totp_code": _code(secret)}
    )
    assert again.status_code == 410 and "expired" in again.json()["detail"]  # used once
    # An expired invitation shows the S-02 message and accepts nothing.
    late = f"late.{uuid.uuid4().hex[:8]}@example.test"
    assert owner.post("/users", json={"email": late, "role": "office"}).status_code == 201
    late_token = _read_link(mailbox, late, "invite")
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE invites SET created_at = now() - interval '73 hours', expires_at = now() - interval '1 hour' WHERE email = :e"),
            {"e": late},
        )
    assert owner.client.post("/api/v1/invites/lookup", json={"token": late_token}).status_code == 410
    assert (
        owner.client.post("/api/v1/invites/accept", json={"token": late_token, "password": "correct horse battery 42"}).status_code == 410
    )
    assert owner.client.post("/api/v1/invites/lookup", json={"token": uuid.uuid4().hex}).status_code == 404
    # A TOTP code works once: the step used at acceptance is refused, the next one works once.
    browser = _browser(settings, store)
    first = browser.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery 42"}).json()
    with owner_engine.connect() as conn:  # the step consumed at acceptance (robust to a 30 s boundary)
        step = int(conn.execute(text("SELECT totp_last_step FROM users WHERE email = :e"), {"e": email}).scalar())
    used = totp_code(secret, step)
    assert browser.post("/api/v1/auth/totp", json={"code": used}, headers={"X-CSRF-Token": first["csrf_token"]}).status_code == 401
    assert browser.post("/api/v1/auth/totp", json={"code": "000000"}, headers={"X-CSRF-Token": first["csrf_token"]}).status_code in (401,)
    nxt = totp_code(secret, step + 1)
    assert browser.post("/api/v1/auth/totp", json={"code": nxt}, headers={"X-CSRF-Token": first["csrf_token"]}).status_code == 200
    other = _browser(settings, store)
    second = other.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery 42"}).json()
    assert other.post("/api/v1/auth/totp", json={"code": nxt}, headers={"X-CSRF-Token": second["csrf_token"]}).status_code == 401


def test_b2_office_without_totp_and_weak_password_refused(
    settings: Any, store: MemoryObjectStore, api: dict[str, Api], mailbox: list[str]
) -> None:
    owner = api["owner"]
    email = f"office.{uuid.uuid4().hex[:10]}@example.test"
    assert owner.post("/users", json={"email": email, "role": "office"}).status_code == 201
    token = _read_link(mailbox, email, "invite")
    weak = owner.client.post("/api/v1/invites/accept", json={"token": token, "password": "password1234"})
    assert weak.status_code == 422
    short = owner.client.post("/api/v1/invites/accept", json={"token": token, "password": "short"})
    assert short.status_code == 422
    assert owner.client.post("/api/v1/invites/accept", json={"token": token, "password": "office ledger synthetic 7"}).status_code == 201
    browser = _browser(settings, store)
    r = browser.post("/api/v1/auth/login", json={"email": email, "password": "office ledger synthetic 7"})
    assert r.status_code == 200 and r.json()["next"] == "done"  # TOTP optional for Office during the pilot (TRD 8.2)
    assert browser.get("/api/v1/auth/session").json()["role"] == "office"
    # An estimator invitation without the authenticator is refused.
    est = f"est.{uuid.uuid4().hex[:10]}@example.test"
    assert owner.post("/users", json={"email": est, "role": "estimator"}).status_code == 201
    est_token = _read_link(mailbox, est, "invite")
    r = owner.client.post("/api/v1/invites/accept", json={"token": est_token, "password": "estimator synthetic pass 9"})
    assert r.status_code == 422 and r.json()["title"] == "Authenticator required"


def test_b2_password_reset_needs_totp_ends_sessions_and_link_works_once(
    settings: Any, store: MemoryObjectStore, api: dict[str, Api], mailbox: list[str], owner_engine: Any
) -> None:
    email, secret, _ = _invite_and_accept(api["owner"], mailbox, "estimator")
    assert secret is not None
    browser = _browser(settings, store)
    _sign_in(browser, email, "correct horse battery 42", secret)
    assert browser.get("/api/v1/auth/session").status_code == 200
    anon = _browser(settings, store)
    unknown = anon.post("/api/v1/auth/password-reset", json={"email": f"nobody.{uuid.uuid4().hex[:8]}@example.test"})
    known = anon.post("/api/v1/auth/password-reset", json={"email": email})
    assert unknown.status_code == known.status_code == 202 and unknown.json() == known.json()  # no enumeration
    token = _read_link(mailbox, email, "reset")
    new_password = "a brand new synthetic passphrase"
    no_code = anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": new_password})
    assert no_code.status_code == 401  # a reset never skips the authenticator
    with owner_engine.begin() as conn:  # test-only: let the next code be the current step again
        conn.execute(text("UPDATE users SET totp_last_step = totp_last_step - 2 WHERE email = :e"), {"e": email})
    r = anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": new_password, "totp_code": _code(secret)})
    assert r.status_code == 200 and r.json()["sessions_ended"] >= 1, r.text
    assert "set-cookie" not in r.headers  # the reset does not sign in
    assert browser.get("/api/v1/auth/session").status_code == 401  # every session ended
    assert anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": new_password}).status_code == 410
    assert anon.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery 42"}).status_code == 401
    # An expired link is refused.
    anon.post("/api/v1/auth/password-reset", json={"email": email})
    mailbox_before = len(mailbox)
    deadline = time.monotonic() + 10
    second = None
    while time.monotonic() < deadline and second is None:
        found = httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{email}" subject:"Password reset"'}, timeout=5).json()["messages"]
        fresh = [m for m in found if m["ID"] not in mailbox]
        if fresh:
            mailbox.append(fresh[0]["ID"])
            second = re.search(
                r"/reset#token=([A-Za-z0-9_\-]+)", httpx.get(f"{MAILPIT}/message/{fresh[0]['ID']}", timeout=5).json()["Text"]
            )
        else:
            time.sleep(0.2)
    assert second and len(mailbox) == mailbox_before + 1
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE password_resets SET created_at = now() - interval '31 minutes', expires_at = now() - interval '1 minute' "
                "WHERE used_at IS NULL AND user_id = (SELECT id FROM users WHERE email = :e)"
            ),
            {"e": email},
        )
    expired = anon.post("/api/v1/auth/password-reset/confirm", json={"token": second.group(1), "password": "yet another synthetic phrase"})
    assert expired.status_code == 410


def test_b2_cross_tenant_session_refused(
    settings: Any, store: MemoryObjectStore, api: dict[str, Api], shop: Shop, other_shop: Shop, mailbox: list[str], owner_engine: Any
) -> None:
    email, secret, _ = _invite_and_accept(api["owner"], mailbox, "estimator")
    browser = _browser(settings, store)
    _sign_in(browser, email, "correct horse battery 42", secret)
    api_b = Api(_browser(settings, store), other_shop.tokens["estimator"])
    b_ro = api_b.post("/ros", json={"location_id": str(other_shop.location_id), "ro_number": "RO-B2-X"}).json()
    assert browser.get(f"/api/v1/ros/{b_ro['id']}").status_code == 404  # signed in to A: B's record does not exist
    assert all(r["tenant_id"] == str(shop.tenant_id) for r in browser.get("/api/v1/ros").json())
    fresh = _browser(settings, store)
    r = fresh.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct horse battery 42", "tenant_id": str(other_shop.tenant_id)}
    )
    assert r.status_code == 401  # not a member of B: refused like a wrong password
    # A session row pointed at another tenant (as if tampered with) finds no membership there: 404.
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET tenant_id = :b WHERE user_id = (SELECT id FROM users WHERE email = :e) AND revoked_at IS NULL"),
            {"b": str(other_shop.tenant_id), "e": email},
        )
    assert browser.get(f"/api/v1/ros/{b_ro['id']}").status_code == 404
    assert browser.get("/api/v1/ros").status_code == 404


def test_b2_rate_limit_and_lockout(settings: Any, store: MemoryObjectStore, api: dict[str, Api], mailbox: list[str]) -> None:
    email, _secret, _ = _invite_and_accept(api["owner"], mailbox, "estimator")
    browser = _browser(settings, store)
    for _ in range(5):
        assert browser.post("/api/v1/auth/login", json={"email": email, "password": "wrong password guess"}).status_code == 401
    locked = browser.post("/api/v1/auth/login", json={"email": email, "password": "correct horse battery 42"})
    assert locked.status_code == 429 and "15 minutes" in locked.json()["detail"] and locked.headers["Retry-After"] == "900"
    # An unknown email locks the same way, so lockout does not reveal accounts.
    ghost = f"ghost.{uuid.uuid4().hex[:8]}@example.test"
    for _ in range(5):
        assert browser.post("/api/v1/auth/login", json={"email": ghost, "password": "wrong password guess"}).status_code == 401
    assert browser.post("/api/v1/auth/login", json={"email": ghost, "password": "wrong password guess"}).status_code == 429
    # Sign-in requests per email are limited even before any failure counts.
    flood = f"flood.{uuid.uuid4().hex[:8]}@example.test"
    codes = [browser.post("/api/v1/auth/login", json={"email": flood, "password": "x" * 12}).status_code for _ in range(12)]
    assert codes.count(429) >= 2


def test_b2_idle_and_absolute_expiry_and_disabled_user(api: dict[str, Api], shop: Shop, owner_engine: Any) -> None:
    est, office, owner = api["estimator"], api["office"], api["owner"]
    assert est.get("/ros").status_code == 200
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET last_seen_at = now() - interval '61 minutes' WHERE user_id = :u"), {"u": shop.users["estimator"]}
        )
        conn.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second' WHERE user_id = :u"), {"u": shop.users["office"]})
        conn.execute(text("UPDATE users SET status = 'disabled' WHERE id = :u"), {"u": shop.users["owner"]})
    assert est.get("/ros").status_code == 401  # idle 60 minutes
    assert office.get("/ros").status_code == 401  # absolute 12 hours
    assert owner.get("/ros").status_code == 401  # deactivated: every session stops working
