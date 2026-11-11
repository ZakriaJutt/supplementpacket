"""Permanent regression tests for the B2 security review, round 1 (B2-S01 to B2-S07).

Each test is the reviewer's failing case from ``supplementpacket-b2-sec_attack.py`` (named in its
docstring), adapted to this suite's fixtures, plus a test for every ASVS ID the verification
report claims that had none (B2-S06). Needs PostgreSQL and Mailpit; the access-log test also
starts a real uvicorn on a free local port and stops it.
"""

from __future__ import annotations

import concurrent.futures as cf
import contextlib
import logging
import os
import re
import secrets
import socket
import statistics
import struct
import subprocess
import time
import uuid
import zlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sp_api.context import csrf_token
from sp_api.main import create_app
from sp_core.auth import TOTP_STEP_SECONDS, derive_key, encrypt_secret, hash_password, hash_token, new_totp_secret, totp_code
from sp_files import MemoryObjectStore
from tests.conftest import APP_URL, SYNTHETIC_PDF, TEST_SESSION_KEY, Api, Shop, create_ro, jpeg

ROOT = Path(__file__).resolve().parents[2]
MAILPIT = "http://127.0.0.1:8025/api/v1"
PW = "synthetic review passphrase 51"
GPS = b"SYNTHETIC-GPS"


def _user(owner_engine: Any, tenant_id: uuid.UUID, role: str, *, totp: bool = True) -> tuple[str, str | None, uuid.UUID]:
    uid = uuid.uuid4()
    email = f"sec.{role}.{uid.hex[:10]}@example.test"
    secret = new_totp_secret() if totp else None
    enc = encrypt_secret(derive_key(TEST_SESSION_KEY, "totp-secret"), secret) if secret else None
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, display_name, password_hash, totp_secret_enc, totp_enabled_at) "
                "VALUES (:id, :e, 'Synthetic Sec', :p, :s, :t)"
            ),
            {"id": uid, "e": email, "p": hash_password(PW), "s": enc, "t": datetime.now(UTC) if secret else None},
        )
        conn.execute(text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, :r)"), {"t": tenant_id, "u": uid, "r": role})
    return email, secret, uid


def _code(secret: str | None, offset: int = 0) -> str:
    return totp_code(secret or "", int(time.time() // TOTP_STEP_SECONDS) + offset)


def _browser(settings: Any, store: Any, addr: str = "testclient") -> TestClient:
    return TestClient(create_app(settings, store), base_url="https://testserver", client=(addr, 50000))


def _mail_delete_to(addresses: list[str]) -> None:
    ids: list[str] = []
    for a in addresses:
        with contextlib.suppress(httpx.HTTPError):
            ids += [m["ID"] for m in httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{a}"'}, timeout=5).json()["messages"]]
    if ids:
        httpx.request("DELETE", f"{MAILPIT}/messages", json={"IDs": ids}, timeout=5)


def _read_token(to: str, path: str, skip: set[str] | None = None) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        for m in httpx.get(f"{MAILPIT}/search", params={"query": f'to:"{to}"'}, timeout=5).json()["messages"]:
            if skip and m["ID"] in skip:
                continue
            body = httpx.get(f"{MAILPIT}/message/{m['ID']}", timeout=5).json()["Text"]
            found = re.search(rf"/{path}#token=([A-Za-z0-9_\-]+)", body)
            if found:
                if skip is not None:
                    skip.add(m["ID"])
                return found.group(1)
        time.sleep(0.2)
    raise AssertionError(f"no mail to {to}")


# B2-S05: lock under concurrency (reviewer A05, A05b) ----------------------------------------------
def test_b2_s05_parallel_password_guesses_evaluate_at_most_five(settings: Any, store: Any, owner_engine: Any, shop: Shop) -> None:
    email, _, _ = _user(owner_engine, shop.tenant_id, "office", totp=False)
    clients = [_browser(settings, store, f"192.0.2.{i}") for i in range(40)]

    def guess(i: int) -> int:
        return clients[i].post("/api/v1/auth/login", json={"email": email, "password": f"wrong guess number {i:04d}"}).status_code

    with cf.ThreadPoolExecutor(40) as ex:
        results = list(ex.map(guess, range(40)))
    assert results.count(401) <= 5 and results.count(429) >= 35, results


def test_b2_s05_parallel_code_guesses_evaluate_at_most_five(settings: Any, store: Any, owner_engine: Any, shop: Shop) -> None:
    email, _, _ = _user(owner_engine, shop.tenant_id, "estimator")
    first = _browser(settings, store)
    r = first.post("/api/v1/auth/login", json={"email": email, "password": PW})
    session, csrf = r.cookies.get("__Host-sp_session"), r.json()["csrf_token"]
    clients = [_browser(settings, store, f"198.51.100.{i}") for i in range(30)]

    def guess(i: int) -> int:
        return (
            clients[i]
            .post(
                "/api/v1/auth/totp",
                json={"code": f"{(i * 104729) % 1000000:06d}"},
                headers={"Cookie": f"__Host-sp_session={session}", "X-CSRF-Token": csrf},
            )
            .status_code
        )

    with cf.ThreadPoolExecutor(30) as ex:
        results = list(ex.map(guess, range(30)))
    assert results.count(401) <= 5, results


# B2-S02: reset confirm under the account lock (reviewer A06) ---------------------------------------
def test_b2_s02_reset_confirm_refused_while_locked_even_with_the_right_code(
    settings: Any, store: Any, owner_engine: Any, shop: Shop
) -> None:
    email, secret, uid = _user(owner_engine, shop.tenant_id, "owner")
    b = _browser(settings, store)
    for _ in range(5):
        assert b.post("/api/v1/auth/login", json={"email": email, "password": "wrong guess wrong guess"}).status_code == 401
    assert b.post("/api/v1/auth/login", json={"email": email, "password": PW}).status_code == 429
    token = secrets.token_urlsafe(32)  # stands in for the emailed link
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (:u, :h, now() + interval '30 minutes')"),
            {"u": uid, "h": hash_token(token)},
        )
    body = {"token": token, "password": "new synthetic passphrase 77"}
    statuses = [
        _browser(settings, store, f"203.0.113.{n}")
        .post("/api/v1/auth/password-reset/confirm", json={**body, "totp_code": f"{n:06d}"})
        .status_code
        for n in range(8)
    ]
    good = _browser(settings, store, "203.0.113.99").post("/api/v1/auth/password-reset/confirm", json={**body, "totp_code": _code(secret)})
    assert statuses == [429] * 8 and good.status_code == 429, (statuses, good.status_code)
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT password_changed_at FROM users WHERE id = :u"), {"u": uid}).scalar() is None


def test_b2_s02_reset_confirm_failures_count_toward_the_lock(settings: Any, store: Any, owner_engine: Any, shop: Shop) -> None:
    email, _secret, uid = _user(owner_engine, shop.tenant_id, "estimator")
    token = secrets.token_urlsafe(32)
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (:u, :h, now() + interval '30 minutes')"),
            {"u": uid, "h": hash_token(token)},
        )
    body = {"token": token, "password": "new synthetic passphrase 77"}
    wrong = [
        _browser(settings, store, f"203.0.113.{n}")
        .post("/api/v1/auth/password-reset/confirm", json={**body, "totp_code": "000000"})
        .status_code
        for n in range(5)
    ]
    assert wrong == [401] * 5
    assert _browser(settings, store).post("/api/v1/auth/login", json={"email": email, "password": PW}).status_code == 429  # same lock


# B2-S03: no token in any URL; the server's access log never records one (reviewer A07) --------------
def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    try:
        httpx.get(f"{MAILPIT}/messages", params={"limit": 1}, timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Mailpit is not running on 127.0.0.1:8025")
    port = _free_port()
    log_path = tmp_path / "uvicorn.log"
    env = {
        **os.environ,
        "PUBLIC_BASE_URL": "https://app.example.test",
        "DATABASE_URL": APP_URL,
        "STORAGE_BACKEND": "local",
        "STORAGE_BUCKET": str(tmp_path / "storage"),
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": "1025",
        "SESSION_KEY": TEST_SESSION_KEY,
        "WORKER_HEARTBEAT_PATH": str(tmp_path / "hb"),
    }
    with log_path.open("wb") as log:
        # The same command line as scripts/dev.py, uvicorn's access log left on.
        proc = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "sp_api.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if httpx.get(f"{url}/readyz", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("server did not start: " + log_path.read_text())
            yield url, log_path
        finally:
            proc.terminate()
            proc.wait(10)


def test_b2_s03_tokens_never_reach_the_access_log(live_server: tuple[str, Path], owner_engine: Any, shop: Shop) -> None:
    url, log_path = live_server
    owner = shop.tokens["owner"]
    headers = {"Cookie": f"__Host-sp_session={owner}", "X-CSRF-Token": csrf_token(TEST_SESSION_KEY, hash_token(owner))}
    invitee = f"sec.log.{uuid.uuid4().hex[:10]}@example.test"
    signature = "SIGNATURE" + secrets.token_hex(16)
    try:
        r = httpx.post(
            f"{url}/api/v1/users", json={"email": invitee, "role": "office"}, headers={**headers, "Idempotency-Key": uuid.uuid4().hex}
        )
        assert r.status_code == 201, r.text
        invite_token = _read_token(invitee, "invite")
        assert httpx.post(f"{url}/api/v1/invites/lookup", json={"token": invite_token}).status_code == 200
        assert httpx.post(f"{url}/api/v1/invites/accept", json={"token": invite_token, "password": PW}).status_code == 201
        assert httpx.post(f"{url}/api/v1/auth/password-reset", json={"email": invitee}).status_code == 202
        reset_token = _read_token(invitee, "reset", skip=set())
        assert (
            httpx.post(
                f"{url}/api/v1/auth/password-reset/confirm", json={"token": reset_token, "password": "a different synthetic phrase"}
            ).status_code
            == 200
        )
        # A token-shaped path segment and a query-string signature are both kept out of the log too.
        httpx.get(f"{url}/api/v1/invites/{invite_token}")
        httpx.get(f"{url}/readyz", params={"expires": "1", "sig": signature})
        time.sleep(0.5)
    finally:
        _mail_delete_to([invitee])
    logged = log_path.read_text()
    assert "POST /api/v1/invites/accept" in logged and "GET /readyz" in logged  # the access log is on
    for secret_value in (invite_token, reset_token, signature):
        assert secret_value not in logged, f"{secret_value[:8]}... written to the access log"


def test_b2_s03_no_route_takes_a_token_in_its_path(client: TestClient) -> None:
    from fastapi.routing import APIRoute

    for route in client.app.routes:  # type: ignore[attr-defined]
        if isinstance(route, APIRoute):
            assert "token" not in route.path, route.path


# B2-S04: constant-time reset request (reviewer A14b) ----------------------------------------------
def test_b2_s04_reset_request_takes_the_same_time_known_or_unknown(settings: Any, store: Any, owner_engine: Any, shop: Shop) -> None:
    known = [_user(owner_engine, shop.tenant_id, "office", totp=False)[0] for _ in range(6)]
    unknown = [f"sec.ghost.{uuid.uuid4().hex[:10]}@example.test" for _ in range(6)]
    b = _browser(settings, store)

    def timed(email: str) -> float:
        with owner_engine.begin() as conn:
            conn.execute(text("DELETE FROM auth_throttle"))
        started = time.perf_counter()
        r = b.post("/api/v1/auth/password-reset", json={"email": email})
        assert r.status_code == 202
        return (time.perf_counter() - started) * 1000

    try:
        k = statistics.median(timed(e) for e in known)
        u = statistics.median(timed(e) for e in unknown)
        assert abs(k - u) < 10.0 and min(k, u) >= 240, (k, u)  # both padded to the 250 ms floor
    finally:
        time.sleep(1)
        _mail_delete_to(known)


# B2-S07: no shop data before the second factor (reviewer A17) --------------------------------------
def test_b2_s07_shop_choice_only_after_every_factor(settings: Any, store: Any, owner_engine: Any, shop: Shop, other_shop: Shop) -> None:
    email, secret, uid = _user(owner_engine, shop.tenant_id, "estimator")
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'office')"), {"t": other_shop.tenant_id, "u": uid}
        )
    b = _browser(settings, store)
    r = b.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200 and set(r.json()) == {"next", "csrf_token"} and r.json()["next"] == "totp"
    assert "Synthetic Shop" not in r.text and str(shop.tenant_id) not in r.text
    pending_csrf = r.json()["csrf_token"]
    assert b.post("/api/v1/auth/tenant", json={"tenant_id": str(shop.tenant_id)}, headers={"X-CSRF-Token": pending_csrf}).status_code == 401
    r = b.post("/api/v1/auth/totp", json={"code": _code(secret)}, headers={"X-CSRF-Token": pending_csrf})
    assert r.status_code == 200 and r.json()["next"] == "choose_tenant"
    assert {t["tenant_id"] for t in r.json()["tenants"]} == {str(shop.tenant_id), str(other_shop.tenant_id)}
    choose_csrf = r.json()["csrf_token"]
    assert b.get("/api/v1/ros").status_code == 401 and b.get("/api/v1/auth/session").status_code == 401  # no shop yet
    unknown = b.post("/api/v1/auth/tenant", json={"tenant_id": str(uuid.uuid4())}, headers={"X-CSRF-Token": choose_csrf})
    assert unknown.status_code == 404
    done = b.post("/api/v1/auth/tenant", json={"tenant_id": str(other_shop.tenant_id)}, headers={"X-CSRF-Token": choose_csrf})
    assert done.status_code == 200 and done.json()["next"] == "done"
    me = b.get("/api/v1/auth/session").json()
    assert me["tenant_id"] == str(other_shop.tenant_id) and me["role"] == "office"


# B2-S01: the reviewer's six crafted photos through the API, store checked (reviewer A15) ------------
def _seg(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def _exif_gps() -> bytes:
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1) + struct.pack(">HHII", 0x8825, 4, 1, 26) + b"\x00\x00\x00\x00"
    gps = struct.pack(">H", 1) + struct.pack(">HHI", 0x0001, 2, 2) + b"N\x00\x00\x00" + b"\x00\x00\x00\x00"
    return b"Exif\x00\x00" + tiff + gps + b"SYNTHETIC-GPS-47.6062N-122.3321W"


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


_JFIF = _seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
_DQT = _seg(0xDB, b"\x00" + bytes(64))
_SOF2 = _seg(0xC2, b"\x08\x00\x10\x00\x10\x01\x01\x11\x00")
_DHT = _seg(0xC4, b"\x00" + bytes(16))
_SOS = _seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
_PNG = b"\x89PNG\r\n\x1a\n"
_IHDR = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
_IDAT = _png_chunk(b"IDAT", bytes.fromhex("789c63f8cfc0000003010100"))
_IEND = _png_chunk(b"IEND", b"")
_REAL = jpeg(b"real photo")

REVIEWER_FILES = {  # verbatim shapes from the reviewer's A15, plus the same shapes on a real photo
    "jpeg_app1_between_scans": b"\xff\xd8"
    + _JFIF
    + _DQT
    + _SOF2
    + _DHT
    + _SOS
    + b"\x12\x34"
    + _seg(0xE1, _exif_gps())
    + _DHT
    + _SOS
    + b"\x56\x78\xff\xd9",
    "jpeg_mpf_trailer_second_image": b"\xff\xd8"
    + _JFIF
    + _seg(0xE2, b"MPF\x00MM\x00\x2a" + bytes(8))
    + _DQT
    + _SOF2
    + _DHT
    + _SOS
    + b"\x12\x34\xff\xd9"
    + b"\xff\xd8"
    + _seg(0xE1, _exif_gps())
    + _DQT
    + _SOS
    + b"\x00\xff\xd9",
    "jpeg_trailer_after_eoi": b"\xff\xd8" + _JFIF + _DQT + _SOF2 + _DHT + _SOS + b"\x12\x34\xff\xd9" + _exif_gps(),
    "png_exIf_chunk": _PNG + _IHDR + _png_chunk(b"exIf", _exif_gps()[6:]) + _IDAT + _IEND,
    "png_zxIf_chunk": _PNG + _IHDR + _png_chunk(b"zxIf", _exif_gps()) + _IDAT + _IEND,
    "png_private_chunk": _PNG + _IHDR + _png_chunk(b"caBX", b"c2pa location " + _exif_gps()) + _IDAT + _IEND,
    "real_jpeg_exif_and_trailer": _REAL[:2] + _seg(0xE1, _exif_gps()) + _REAL[2:] + _exif_gps(),
    "real_jpeg_mpf_trailer": _REAL[:2]
    + _seg(0xE2, b"MPF\x00MM\x00*" + bytes(8))
    + _REAL[2:]
    + _REAL[:2]
    + _seg(0xE1, _exif_gps())
    + _REAL[2:],
}


@pytest.mark.parametrize("name", sorted(REVIEWER_FILES))
def test_b2_s01_crafted_photo_never_stored_with_gps(api: dict[str, Api], shop: Shop, store: MemoryObjectStore, name: str) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    line = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "other", "description": "Seam sealer", "requested_cents": 1000, "explanation": "Synthetic."},
    ).json()
    r = est.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("p", REVIEWER_FILES[name], "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    result = r.json()["results"][0]
    assert "metadata_blocks_removed" not in result
    assert all(GPS not in data for data in store.objects.values()), name  # nothing with GPS reaches storage
    if name.startswith("real_") or name.startswith("png_"):  # decodable: accepted only as a clean re-encode
        assert result["status"] == "attached" and result["metadata"] == "none: re-encoded from pixels", result
        served = est.get(f"/photos/{result['photo_id']}/content").content
        assert GPS not in served and b"Exif" not in served and b"MPF" not in served
        assert not any(kind in served for kind in (b"exIf", b"zxIf", b"caBX", b"eXIf", b"tEXt", b"iTXt"))
    else:
        assert result["status"] == "rejected", result  # the reviewer's hand-made JPEGs carry no decodable image


# B2-S06: a test for each claimed ASVS ID that had none --------------------------------------------
def test_b2_s06_upload_size_caps(api: dict[str, Api], shop: Shop, store: MemoryObjectStore) -> None:
    """ASVS 5.2.1: 25 MB per PDF (413) and 15 MB per photo (rejected per file); nothing stored."""
    est = api["estimator"]
    ro = create_ro(est, shop)
    big_pdf = SYNTHETIC_PDF + bytes(26_214_401)
    r = est.post(f"/ros/{ro['id']}/documents", data={"purpose": "shop_estimate"}, files={"file": ("e.pdf", big_pdf, "application/pdf")})
    assert r.status_code == 413
    line = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "other", "description": "Seam sealer", "requested_cents": 1000, "explanation": "Synthetic."},
    ).json()
    big_photo = jpeg(b"cap") + bytes(15_728_641)
    r = est.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("big.jpg", big_photo, "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    assert r.json()["results"][0] == {"index": 0, "status": "rejected", "reason": "larger than 15 MB"}
    assert store.objects == {}


def test_b2_s06_login_revokes_a_session_already_in_the_browser(settings: Any, store: Any, owner_engine: Any, shop: Shop) -> None:
    """ASVS 7.2.4: a session planted in the browser before sign-in is ended by the sign-in."""
    email, _secret, _ = _user(owner_engine, shop.tenant_id, "estimator")
    planted = shop.tokens["office"]
    b = _browser(settings, store)
    r = b.post("/api/v1/auth/login", json={"email": email, "password": PW}, headers={"Cookie": f"__Host-sp_session={planted}"})
    assert r.status_code == 200
    assert Api(_browser(settings, store), planted).get("/ros").status_code == 401
    assert r.cookies.get("__Host-sp_session") not in (None, planted)


def test_b2_s06_logout_all_ends_every_session(settings: Any, store: Any, owner_engine: Any, shop: Shop) -> None:
    """ASVS 7.4.1 and 7.4.3: logout ends one session; logout everywhere ends the rest."""
    email, secret, _ = _user(owner_engine, shop.tenant_id, "estimator")
    browsers = [_browser(settings, store) for _ in range(3)]
    csrfs = []
    for offset, b in zip((-1, 0, 1), browsers, strict=True):
        r = b.post("/api/v1/auth/login", json={"email": email, "password": PW})
        r = b.post("/api/v1/auth/totp", json={"code": _code(secret, offset)}, headers={"X-CSRF-Token": r.json()["csrf_token"]})
        assert r.status_code == 200, r.text
        csrfs.append(r.json()["csrf_token"])
    assert browsers[0].post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrfs[0]}).status_code == 200
    assert browsers[0].get("/api/v1/ros").status_code == 401 and browsers[1].get("/api/v1/ros").status_code == 200
    r = browsers[1].post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": csrfs[1]})
    assert r.status_code == 200 and r.json()["sessions_ended"] == 2
    assert all(b.get("/api/v1/ros").status_code == 401 for b in browsers)


def test_b2_s06_authentication_events_are_logged_without_secrets(
    settings: Any, store: Any, owner_engine: Any, shop: Shop, caplog: pytest.LogCaptureFixture
) -> None:
    """ASVS 16.3.1: success and failure of each step are logged with the user ID, never the email or secret."""
    email, secret, uid = _user(owner_engine, shop.tenant_id, "estimator")
    b = _browser(settings, store)
    with caplog.at_level(logging.INFO, logger="sp_api.auth"):
        b.post("/api/v1/auth/login", json={"email": email, "password": "wrong guess wrong guess"})
        r = b.post("/api/v1/auth/login", json={"email": email, "password": PW})
        b.post("/api/v1/auth/totp", json={"code": _code(secret)}, headers={"X-CSRF-Token": r.json()["csrf_token"]})
    events = [(rec.getMessage(), getattr(rec, "user_id", None)) for rec in caplog.records if rec.name == "sp_api.auth"]
    assert ("sign-in failed", None) in events
    assert ("sign-in password step passed", str(uid)) in events and ("sign-in second factor passed", str(uid)) in events
    text_logged = " ".join(f"{rec.getMessage()} {rec.__dict__}" for rec in caplog.records)
    assert email not in text_logged and PW not in text_logged and (secret or "x") not in text_logged
