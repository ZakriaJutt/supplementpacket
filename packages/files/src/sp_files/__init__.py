"""Object keys, storage interface and signed URLs (TRD 8.6, AD-09, R-13, R-16).

Keys come from :func:`build_object_key` only; a user's file name never enters a key.
Storage is behind :class:`ObjectStore`: :class:`S3ObjectStore` speaks the S3 API (local
MinIO in development, a real provider later, chosen by settings only, B2); a local-directory
store and an in-memory fake remain for tests. Objects are private: there are no public URLs,
and downloads go through an authorised API endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlencode

from sp_files.metadata import MetadataError, strip_metadata

if TYPE_CHECKING:
    from sp_core.settings import Settings

__all__ = [
    "PURPOSES",
    "LocalObjectStore",
    "MemoryObjectStore",
    "MetadataError",
    "ObjectStore",
    "S3ObjectStore",
    "build_object_key",
    "build_temp_key",
    "open_store",
    "sha256_hex",
    "sign_download_url",
    "sniff_type",
    "store_from_settings",
    "strip_metadata",
    "verify_download_signature",
]

PURPOSES = ("insurer_estimate", "shop_estimate", "photo", "response", "remittance", "packet", "export")
_EXT = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/heic": "heic", "application/zip": "zip"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_type(data: bytes) -> str | None:
    """Type by content, never by the file name or client header."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) > 12 and data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"heif"):
        return "image/heic"
    return None


def build_object_key(
    *, tenant_id: uuid.UUID, ro_id: uuid.UUID, purpose: str, document_id: uuid.UUID, sha256: str, content_type: str
) -> str:
    if purpose not in PURPOSES:
        raise ValueError("unknown purpose")
    if not _HEX64.match(sha256):
        raise ValueError("sha256 must be 64 lowercase hex characters")
    ext = _EXT.get(content_type)
    if ext is None:
        raise ValueError("unsupported content type")
    return f"t/{uuid.UUID(str(tenant_id))}/ro/{uuid.UUID(str(ro_id))}/{purpose}/{uuid.UUID(str(document_id))}/{sha256}.{ext}"


def build_temp_key(*, tenant_id: uuid.UUID, upload_id: uuid.UUID) -> str:
    return f"tmp/{uuid.UUID(str(tenant_id))}/{uuid.UUID(str(upload_id))}"


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class MemoryObjectStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.objects


class LocalObjectStore:
    """Development store under a local directory (the MinIO stand-in for B1)."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("key escapes the store")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3ObjectStore:
    """Private objects in one bucket through the S3 API (MinIO locally). No ACLs, no public URLs."""

    def __init__(
        self, *, bucket: str, endpoint_url: str | None, region: str, access_key_id: str | None, secret_access_key: str | None
    ) -> None:
        import boto3  # imported here so the fakes and the worker's no-web check do not need it loaded
        from botocore.config import Config

        self.bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentLength=len(data))

    def get(self, key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for page in self._client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys


def open_store(
    *,
    backend: str,
    bucket: str,
    endpoint_url: str | None = None,
    region: str = "us-east-1",
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
) -> ObjectStore:
    """The one place a store is chosen from settings (API and worker)."""
    if backend == "s3":
        return S3ObjectStore(
            bucket=bucket, endpoint_url=endpoint_url, region=region, access_key_id=access_key_id, secret_access_key=secret_access_key
        )
    if backend == "local":
        return LocalObjectStore(Path(bucket))
    raise ValueError("STORAGE_BACKEND must be s3 or local")


def store_from_settings(settings: Settings) -> ObjectStore:
    """API and worker open the same store from the same settings (R-06)."""
    return open_store(
        backend=settings.storage_backend,
        bucket=settings.storage_bucket,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
    )


def _signature(secret: str, path: str, expires: int) -> str:
    return hmac.new(secret.encode(), f"{path}|{expires}".encode(), hashlib.sha256).hexdigest()


def sign_download_url(*, public_base_url: str, path: str, secret: str, ttl_seconds: int = 300, now: float | None = None) -> str:
    """Links are built only from PUBLIC_BASE_URL (R-16); valid 5 minutes by default."""
    if not path.startswith("/"):
        raise ValueError("path must be absolute")
    expires = int((now if now is not None else time.time()) + ttl_seconds)
    query = urlencode({"expires": expires, "sig": _signature(secret, path, expires)})
    return f"{public_base_url.rstrip('/')}{path}?{query}"


def verify_download_signature(*, path: str, expires: int, sig: str, secret: str, now: float | None = None) -> bool:
    if (now if now is not None else time.time()) > expires:
        return False
    return hmac.compare_digest(_signature(secret, path, expires), sig)
