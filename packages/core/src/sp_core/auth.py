"""Credentials: password hashing and policy, TOTP, opaque tokens, secret encryption (TRD 8.2, B2).

Deterministic and free of web frameworks. Passwords use scrypt from the standard library
(ASVS 11.4.2); TOTP is RFC 6238 (SHA-1, 6 digits, 30-second steps, one step of drift) and
a code is accepted once only (ASVS 6.5.1). TOTP secrets are stored encrypted with AES-GCM
under a key derived from SESSION_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from dataclasses import dataclass
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = [
    "PASSWORD_MAX",
    "PASSWORD_MIN",
    "TOTP_STEP_SECONDS",
    "PasswordPolicyError",
    "TotpResult",
    "check_password_policy",
    "decrypt_secret",
    "derive_key",
    "encrypt_secret",
    "hash_password",
    "hash_token",
    "new_token",
    "new_totp_secret",
    "totp_code",
    "totp_uri",
    "verify_password",
    "verify_totp",
]

PASSWORD_MIN = 12  # TRD 8.2; ASVS 6.2.1 requires at least 8
PASSWORD_MAX = 256  # ASVS 6.2.9: at least 64 allowed
TOTP_STEP_SECONDS = 30
TOTP_DRIFT_STEPS = 1
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024

# A short local deny-list of very common passwords of 12+ characters. The breached-password
# service the TRD names (ASVS 6.2.12) needs an outside call and is deferred.
_COMMON = frozenset(
    {
        "123456789012",
        "1234567890123",
        "12345678901234",
        "aaaaaaaaaaaa",
        "abcdefghijkl",
        "abc123abc123",
        "iloveyou1234",
        "letmein12345",
        "password1234",
        "password12345",
        "passwordpassword",
        "qwertyuiop12",
        "qwertyuiopasdf",
        "qwerty123456",
        "welcome12345",
        "changeme1234",
        "administrator",
        "supplementpacket",
        "111111111111",
        "000000000000",
    }
)


class PasswordPolicyError(ValueError):
    pass


def check_password_policy(password: str, *, email: str | None = None) -> None:
    """Length 12 to 256, not a common password, not the email. No composition rules (ASVS 6.2.5)."""
    if len(password) < PASSWORD_MIN:
        raise PasswordPolicyError(f"use at least {PASSWORD_MIN} characters")
    if len(password) > PASSWORD_MAX:
        raise PasswordPolicyError(f"use at most {PASSWORD_MAX} characters")
    lowered = password.lower()
    if lowered in _COMMON or len(set(password)) < 4:
        raise PasswordPolicyError("this password is too common; choose another")
    if email and lowered in (email.lower(), email.split("@", 1)[0].lower()):
        raise PasswordPolicyError("do not use your email address as the password")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32)
    return "$".join(
        ("scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode())
    )


_DUMMY_HASH: str | None = None


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-shape check: an unknown user still costs one scrypt run (enumeration, ASVS 6.3.8)."""
    global _DUMMY_HASH
    if stored is None or not stored.startswith("scrypt$"):
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password(secrets.token_hex(8))
        stored, ok_format = _DUMMY_HASH, False
    else:
        ok_format = True
    try:
        _, n, r, p, salt_b64, digest_b64 = stored.split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM, dklen=32
        )
    except (ValueError, TypeError):
        return False
    return ok_format and hmac.compare_digest(digest, base64.b64decode(digest_b64))


def new_token() -> str:
    """Opaque token with 256 bits from the operating system CSPRNG (ASVS 7.2.3)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    """Tokens are stored only as their SHA-256 digest."""
    return hashlib.sha256(token.encode()).digest()


# TOTP --------------------------------------------------------------------------------------------
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _b32(secret: str) -> bytes:
    return base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))


def totp_code(secret: str, step: int) -> str:
    mac = hmac.new(_b32(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


@dataclass(frozen=True)
class TotpResult:
    ok: bool
    step: int | None


def verify_totp(secret: str, code: str, *, last_step: int | None, now: float | None = None) -> TotpResult:
    """Accept the current step or one either side, and only a step later than the last one used."""
    code = code.strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return TotpResult(False, None)
    current = int((now if now is not None else time.time()) // TOTP_STEP_SECONDS)
    for step in range(current - TOTP_DRIFT_STEPS, current + TOTP_DRIFT_STEPS + 1):
        if hmac.compare_digest(totp_code(secret, step), code):
            if last_step is not None and step <= last_step:
                return TotpResult(False, None)  # replay of a code already used
            return TotpResult(True, step)
    return TotpResult(False, None)


def totp_uri(secret: str, account: str, issuer: str = "SupplementPacket") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


# Secret encryption -------------------------------------------------------------------------------
def derive_key(session_key: str, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"supplementpacket/{purpose}".encode()).derive(session_key.encode())


def encrypt_secret(key: bytes, plaintext: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), b"totp")


def decrypt_secret(key: bytes, blob: bytes) -> str:
    return AESGCM(key).decrypt(blob[:12], blob[12:], b"totp").decode()
