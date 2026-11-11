"""B2 file storage through the S3 API to the local MinIO (TRD 8.6, R-13), and photo metadata removal.

Needs MinIO on 127.0.0.1:9000 with the bucket ``supplementpacket-dev`` and the local test
credentials in the untracked ``.env`` (or the environment). Every object a test writes is under
its own synthetic tenant's prefix and is deleted at the end.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sp_api.main import create_app
from sp_core.settings import Settings
from sp_files import S3ObjectStore
from tests.conftest import APP_URL, JPEG, OWNER_URL, SYNTHETIC_PDF, TEST_SESSION_KEY, Api, Shop, create_ro

ROOT = Path(__file__).resolve().parents[2]
BUCKET = "supplementpacket-dev"
ENDPOINT = "http://127.0.0.1:9000"


def _local(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip() or None
    return None


@pytest.fixture()
def s3_settings(tmp_path: Path) -> Settings:
    key, secret = _local("S3_ACCESS_KEY_ID"), _local("S3_SECRET_ACCESS_KEY")
    if not key or not secret:
        pytest.skip("S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY are not set in .env")
    try:
        httpx.get(f"{ENDPOINT}/minio/health/live", timeout=3).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("MinIO is not running on 127.0.0.1:9000")
    return Settings(
        PUBLIC_BASE_URL="https://app.example.test",
        DATABASE_URL=APP_URL,
        MIGRATION_DATABASE_URL=OWNER_URL,
        STORAGE_BACKEND="s3",
        STORAGE_BUCKET=BUCKET,
        S3_ENDPOINT_URL=ENDPOINT,
        S3_REGION="us-east-1",
        S3_ACCESS_KEY_ID=key,
        S3_SECRET_ACCESS_KEY=secret,
        SESSION_KEY=TEST_SESSION_KEY,
        WORKER_HEARTBEAT_PATH=str(tmp_path / "hb"),
    )  # type: ignore[call-arg]


@pytest.fixture()
def s3(s3_settings: Settings, shop: Shop, other_shop: Shop) -> Iterator[S3ObjectStore]:
    store = S3ObjectStore(
        bucket=BUCKET,
        endpoint_url=ENDPOINT,
        region="us-east-1",
        access_key_id=s3_settings.s3_access_key_id,
        secret_access_key=s3_settings.s3_secret_access_key,
    )
    yield store
    for tenant in (shop.tenant_id, other_shop.tenant_id):
        for key in store.list_keys(f"t/{tenant}/"):
            store.delete(key)
        assert store.list_keys(f"t/{tenant}/") == []  # cleanup verified


def _exif_with_gps() -> bytes:
    """A JPEG APP1 Exif segment whose IFD0 points at a GPS IFD holding a synthetic latitude."""
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1) + struct.pack(">HHII", 0x8825, 4, 1, 26) + b"\x00\x00\x00\x00"
    gps = struct.pack(">H", 1) + struct.pack(">HHI", 0x0001, 2, 2) + b"N\x00\x00\x00" + b"\x00\x00\x00\x00"
    payload = b"Exif\x00\x00" + tiff + gps + b"SYNTHETIC-GPS-47.6062N"
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def test_b2_upload_download_one_tenant_refused_for_another(
    s3_settings: Settings, s3: S3ObjectStore, shop: Shop, other_shop: Shop, owner_engine: Any
) -> None:
    client = TestClient(create_app(s3_settings), raise_server_exceptions=True, base_url="https://testserver")
    est, other = Api(client, shop.tokens["estimator"]), Api(client, other_shop.tokens["estimator"])
    ro = create_ro(est, shop)
    pdf = SYNTHETIC_PDF + os.urandom(8)
    r = est.post(f"/ros/{ro['id']}/documents", data={"purpose": "shop_estimate"}, files={"file": ("e.pdf", pdf, "application/pdf")})
    assert r.status_code == 202, r.text
    doc_id = r.json()["document"]["id"]
    with owner_engine.connect() as conn:
        key = conn.execute(text("SELECT storage_key FROM documents WHERE id = :d"), {"d": doc_id}).scalar()
    assert key.startswith(f"t/{shop.tenant_id}/ro/{ro['id']}/shop_estimate/{doc_id}/")  # tenant, source and purpose (R-13)
    assert s3.get(key) == pdf  # really in MinIO
    got = est.get(f"/documents/{doc_id}/content")
    assert got.status_code == 200 and got.content == pdf and got.headers["cache-control"] == "private, no-store"
    assert other.get(f"/documents/{doc_id}/content").status_code == 404  # another tenant
    assert httpx.get(f"{ENDPOINT}/{BUCKET}/{key}", timeout=5).status_code == 403  # no public URL
    # A photo with GPS metadata: stored and served without it.
    line = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "other", "description": "Seam sealer", "requested_cents": 1000, "explanation": "Synthetic."},
    ).json()
    photo = JPEG[:2] + _exif_with_gps() + JPEG[2:] + os.urandom(4)
    assert b"SYNTHETIC-GPS" in photo
    r = est.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("p.jpg", photo, "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    result = r.json()["results"][0]
    assert result["status"] == "attached" and result["metadata_blocks_removed"] == 1, result
    served = est.get(f"/photos/{result['photo_id']}/content")
    assert served.status_code == 200 and b"SYNTHETIC-GPS" not in served.content and b"Exif" not in served.content
    assert served.content.startswith(b"\xff\xd8\xff\xe0")  # JFIF kept, still a JPEG
    with owner_engine.connect() as conn:
        pkey = conn.execute(text("SELECT storage_key FROM photos WHERE id = :p"), {"p": result["photo_id"]}).scalar()
    assert b"SYNTHETIC-GPS" not in s3.get(pkey)
    assert other.get(f"/photos/{result['photo_id']}/content").status_code == 404


def test_b2_heic_refused_until_metadata_can_be_removed(api: dict[str, Api], shop: Shop) -> None:
    est = api["estimator"]
    ro = create_ro(est, shop)
    line = est.post(
        f"/ros/{ro['id']}/lines",
        json={"origin": "manual", "category": "other", "description": "Seam sealer", "requested_cents": 1000, "explanation": "Synthetic."},
    ).json()
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + os.urandom(16)
    broken = b"\xff\xd8\xff\xe1\x00"  # claims JPEG, cannot be parsed
    r = est.post(
        f"/lines/{line['id']}/photos",
        files=[("files", ("a.heic", heic, "image/heic")), ("files", ("b.jpg", broken, "image/jpeg"))],
        data={"attested": "true", "taken_by_shop": "true"},
    )
    results = r.json()["results"]
    assert [x["status"] for x in results] == ["rejected", "rejected"]
    assert "HEIC" in results[0]["reason"] and "could not be read" in results[1]["reason"]
