"""B2 unit tests: password hashing and policy, TOTP (RFC 6238 vectors, drift, replay), secret
encryption, and photo metadata removal."""

from __future__ import annotations

import struct

import pytest

from sp_core.auth import (
    PasswordPolicyError,
    check_password_policy,
    decrypt_secret,
    derive_key,
    encrypt_secret,
    hash_password,
    totp_code,
    verify_password,
    verify_totp,
)
from sp_files import MetadataError, strip_metadata

RFC6238_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of the RFC 6238 SHA-1 key "12345678901234567890"


def test_password_hash_and_policy() -> None:
    stored = hash_password("correct horse battery 42")
    assert stored.startswith("scrypt$") and "correct" not in stored
    assert verify_password("correct horse battery 42", stored)
    assert not verify_password("correct horse battery 43", stored)
    assert not verify_password("correct horse battery 42", None)  # unknown user still costs a hash
    assert not verify_password("anything at all", "not-a-real-hash")
    assert hash_password("same password here") != hash_password("same password here")  # salted
    for bad in ("short", "password1234", "aaaaaaaaaaaaaaaa", "x" * 257):
        with pytest.raises(PasswordPolicyError):
            check_password_policy(bad)
    with pytest.raises(PasswordPolicyError):
        check_password_policy("estimator.one@example.test", email="estimator.one@example.test")
    check_password_policy("a long passphrase with spaces")  # no composition rules
    check_password_policy("Ünïcödé pässwörd ✓ 2026")


def test_totp_rfc6238_vectors_drift_and_replay() -> None:
    # RFC 6238 appendix B, SHA-1, last 6 digits: T=59 -> 94287082, T=1111111109 -> 07081804.
    assert totp_code(RFC6238_SECRET, 59 // 30) == "287082"
    assert totp_code(RFC6238_SECRET, 1111111109 // 30) == "081804"
    now = 1111111109.0
    step = int(now // 30)
    ok = verify_totp(RFC6238_SECRET, "081804", last_step=None, now=now)
    assert ok.ok and ok.step == step
    assert verify_totp(RFC6238_SECRET, totp_code(RFC6238_SECRET, step + 1), last_step=None, now=now).ok  # one step of drift
    assert not verify_totp(RFC6238_SECRET, totp_code(RFC6238_SECRET, step + 2), last_step=None, now=now).ok
    assert not verify_totp(RFC6238_SECRET, "081804", last_step=step, now=now).ok  # the same code twice
    assert not verify_totp(RFC6238_SECRET, totp_code(RFC6238_SECRET, step - 1), last_step=step, now=now).ok  # an older one
    assert not verify_totp(RFC6238_SECRET, "08180", last_step=None, now=now).ok
    assert not verify_totp(RFC6238_SECRET, "abcdef", last_step=None, now=now).ok


def test_secret_encryption_round_trip_and_key_separation() -> None:
    key = derive_key("test-session-key-not-secret", "totp-secret")
    blob = encrypt_secret(key, RFC6238_SECRET)
    assert RFC6238_SECRET.encode() not in blob and decrypt_secret(key, blob) == RFC6238_SECRET
    with pytest.raises(Exception):  # noqa: B017 - any authentication failure
        decrypt_secret(derive_key("another-session-key-value", "totp-secret"), blob)


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def test_jpeg_metadata_removed_image_data_kept() -> None:
    jfif = _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    exif = _segment(0xE1, b"Exif\x00\x00MM\x00*GPS-47.6N-122.3W")
    xmp = _segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>gps</x:xmpmeta>")
    icc = _segment(0xE2, b"ICC_PROFILE\x00profile")
    iptc = _segment(0xED, b"Photoshop 3.0\x00location")
    comment = _segment(0xFE, b"taken at 1 Synthetic Way")
    dqt = _segment(0xDB, b"\x00" + bytes(64))
    scan = _segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\xff\x00\x56" + b"\xff\xd9"
    original = b"\xff\xd8" + jfif + exif + xmp + icc + iptc + comment + dqt + scan
    cleaned, removed = strip_metadata(original, "image/jpeg")
    assert removed == 4
    assert b"GPS" not in cleaned and b"xmpmeta" not in cleaned and b"location" not in cleaned and b"Synthetic Way" not in cleaned
    assert cleaned == b"\xff\xd8" + jfif + icc + dqt + scan  # every image segment and the scan data byte for byte
    assert strip_metadata(cleaned, "image/jpeg") == (cleaned, 0)
    for broken in (b"\xff\xd8\xff\xe1\x00", b"\xff\xd8\x00\x00", b"not a jpeg"):
        with pytest.raises(MetadataError):
            strip_metadata(broken, "image/jpeg")


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + b"\x00\x00\x00\x00"


def test_png_text_and_exif_chunks_removed() -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr, idat, iend = _chunk(b"IHDR", bytes(13)), _chunk(b"IDAT", b"pixels"), _chunk(b"IEND", b"")
    meta = _chunk(b"eXIf", b"MM\x00*GPS") + _chunk(b"tEXt", b"Location\x00Seattle") + _chunk(b"iTXt", b"XML\x00gps")
    cleaned, removed = strip_metadata(sig + ihdr + meta + idat + iend, "image/png")
    assert removed == 3 and cleaned == sig + ihdr + idat + iend
    with pytest.raises(MetadataError):
        strip_metadata(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 999) + b"IDAT", "image/png")
    with pytest.raises(MetadataError):
        strip_metadata(b"....ftypheic", "image/heic")
