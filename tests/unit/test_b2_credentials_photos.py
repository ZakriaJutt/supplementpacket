"""B2 unit tests: password hashing and policy, TOTP (RFC 6238 vectors, drift, replay), secret
encryption, token entropy, and photo re-encoding (B2-S01: decode to pixels, write a new file)."""

from __future__ import annotations

import io
import struct
import zlib

import pytest
from PIL import Image

from sp_core.auth import (
    PasswordPolicyError,
    check_password_policy,
    decrypt_secret,
    derive_key,
    encrypt_secret,
    hash_password,
    hash_token,
    new_token,
    totp_code,
    verify_password,
    verify_totp,
)
from sp_files import PhotoError, reencode_photo

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


def test_b2_s06_password_length_and_exactness() -> None:
    """ASVS 6.2.9: 64 and 256 characters accepted; 6.2.8: verified exactly as typed, no truncation or case folding."""
    for length in (64, 128, 256):
        pw = ("synthetic passphrase " * 20)[: length - 3] + "x9!"
        check_password_policy(pw)
        stored = hash_password(pw)
        assert verify_password(pw, stored)
        assert not verify_password(pw[:-1], stored) and not verify_password(pw + "a", stored)
        assert not verify_password(pw.upper(), stored) and not verify_password(" " + pw, stored)


def test_b2_s06_token_entropy() -> None:
    """ASVS 7.2.3: 32 bytes from the CSPRNG (43 base64url characters), stored only as SHA-256."""
    tokens = {new_token() for _ in range(2000)}
    assert len(tokens) == 2000 and all(len(t) == 43 for t in tokens)
    sample = next(iter(tokens))
    assert len(hash_token(sample)) == 32 and sample.encode() not in hash_token(sample)
    alphabet = set("".join(tokens))
    assert len(alphabet) >= 60  # the full base64url alphabet is in use


# Photo re-encoding ------------------------------------------------------------------------------
GPS = b"SYNTHETIC-GPS-47.6062N-122.3321W"


def _exif_gps() -> bytes:
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">H", 1) + struct.pack(">HHII", 0x8825, 4, 1, 26) + b"\x00\x00\x00\x00"
    gps = struct.pack(">H", 1) + struct.pack(">HHI", 0x0001, 2, 2) + b"N\x00\x00\x00" + b"\x00\x00\x00\x00"
    return b"Exif\x00\x00" + tiff + gps + GPS


def _seg(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def _picture(size: tuple[int, int] = (64, 48), mode: str = "RGB") -> Image.Image:
    img = Image.new(mode, size)
    img.putdata(
        [
            ((x * 4) % 256, (y * 5) % 256, (x * y) % 256)[: len(mode)] if mode != "L" else (x * 4) % 256
            for y in range(size[1])
            for x in range(size[0])
        ]
    )  # type: ignore[arg-type]
    return img


def _jpeg(**kw: object) -> bytes:
    out = io.BytesIO()
    _picture().save(out, format="JPEG", quality=92, **kw)  # type: ignore[arg-type]
    return out.getvalue()


def _png() -> bytes:
    out = io.BytesIO()
    _picture().save(out, format="PNG")
    return out.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _after_ihdr(png: bytes, chunk: bytes) -> bytes:
    return png[:33] + chunk + png[33:]  # signature (8) + IHDR (25)


def _real_bypasses() -> dict[str, bytes]:
    """The reviewer's six bypass shapes (A15) built on real, decodable images."""
    prog = _jpeg(progressive=True)
    second_sos = prog.index(b"\xff\xda", prog.index(b"\xff\xda") + 2)
    secondary = io.BytesIO()
    _picture((32, 24)).save(secondary, format="JPEG", exif=_exif_gps())
    mpo_buf = io.BytesIO()
    _picture().save(mpo_buf, format="MPO", save_all=True, append_images=[Image.open(io.BytesIO(secondary.getvalue()))])
    mpo = mpo_buf.getvalue()
    second_soi = mpo.index(b"\xff\xd8", mpo.index(b"\xff\xd9") + 2)  # the secondary image starts after the first EOI
    mpo = mpo[: second_soi + 2] + _seg(0xE1, _exif_gps()) + mpo[second_soi + 2 :]
    base = _jpeg()
    return {
        "jpeg_exif_at_start": base[:2] + _seg(0xE1, _exif_gps()) + base[2:],
        "jpeg_app1_between_scans": prog[:second_sos] + _seg(0xE1, _exif_gps()) + prog[second_sos:],
        "jpeg_mpf_second_image_with_gps": mpo,
        "jpeg_mpf_handmade_trailer": base[:2] + _seg(0xE2, b"MPF\x00MM\x00*" + bytes(8)) + base[2:] + secondary.getvalue(),
        "jpeg_trailer_after_eoi": base + _exif_gps(),
        "jpeg_xmp_and_comment": base[:2] + _seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x>" + GPS + b"</x>") + _seg(0xFE, GPS) + base[2:],
        "jpeg_icc_with_gps": _jpeg(icc_profile=b"\x00" * 128 + GPS),
        "png_exIf_chunk": _after_ihdr(_png(), _png_chunk(b"exIf", _exif_gps()[6:])),
        "png_zxIf_chunk": _after_ihdr(_png(), _png_chunk(b"zxIf", _exif_gps())),
        "png_private_chunk": _after_ihdr(_png(), _png_chunk(b"caBX", b"c2pa location " + GPS)),
        "png_text_and_exif": _after_ihdr(_png(), _png_chunk(b"tEXt", b"Location\x00" + GPS) + _png_chunk(b"eXIf", _exif_gps()[6:])),
    }


@pytest.mark.parametrize("name", sorted(_real_bypasses()))
def test_b2_s01_reencode_removes_every_metadata_shape(name: str) -> None:
    data = _real_bypasses()[name]
    assert GPS in data
    kind = "image/png" if name.startswith("png") else "image/jpeg"
    out = reencode_photo(data, kind)
    assert GPS not in out.data and b"Exif" not in out.data and b"MPF" not in out.data and b"ICC_PROFILE" not in out.data
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.format == ("PNG" if kind == "image/png" else "JPEG") and getattr(img, "n_frames", 1) == 1
        assert not img.getexif() and "icc_profile" not in img.info and "xmp" not in img.info
        assert img.size == (64, 48)
    if name == "jpeg_mpf_second_image_with_gps":
        assert out.frames_dropped == 1


def test_b2_s01_orientation_applied_and_size_limits() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to display
    out = reencode_photo(_jpeg(exif=exif.tobytes()), "image/jpeg")
    assert (out.width, out.height) == (48, 64)  # the pixels are upright; no orientation tag is needed
    big = io.BytesIO()
    Image.new("RGB", (3000, 1500), (10, 20, 30)).save(big, format="JPEG")
    shrunk = reencode_photo(big.getvalue(), "image/jpeg")
    assert (shrunk.width, shrunk.height) == (2000, 1000)
    huge = io.BytesIO()
    Image.new("1", (7000, 6000)).save(huge, format="PNG")  # 42 megapixels
    with pytest.raises(PhotoError, match="40 megapixels"):
        reencode_photo(huge.getvalue(), "image/png")


def test_b2_s01_anything_that_does_not_decode_is_refused() -> None:
    base = _jpeg()
    crafted_jfif = (
        b"\xff\xd8" + _seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00") + _seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"x"
    )
    for bad, kind in (
        (base[: len(base) // 2], "image/jpeg"),  # truncated
        (crafted_jfif, "image/jpeg"),  # headers without decodable image data
        (b"\xff\xd8\xff\xe1\x00", "image/jpeg"),
        (_png()[:60], "image/png"),
        (_png(), "image/jpeg"),  # content does not match the type
        (b"....ftypheic", "image/heic"),
        (b"GIF89a" + GPS, "image/gif"),
    ):
        with pytest.raises(PhotoError):
            reencode_photo(bad, kind)
