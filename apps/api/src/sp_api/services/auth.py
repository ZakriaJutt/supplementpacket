"""Sign-in, sessions, invitations and password reset (TRD 8.2, App-flow S-01 and S-02; T-2.2.2, B2).

Password plus TOTP (AD-11): there is no emailed sign-in link or code. TOTP is mandatory for
Owners, Estimators and Operators and optional for Office users. Email carries invitations and
password-reset links only; a reset never signs the user in and never skips the TOTP code.

Rate limits and lockout (ASVS 6.3.1), counted in ``auth_throttle`` and committed before the
request is answered, so a refused attempt still counts:
- sign-in requests: 10 per email and 30 per client address in 15 minutes;
- failed password or code: after 5 failures for an email in 15 minutes the account waits
  15 minutes, whether or not the email has an account (no enumeration);
- reset requests: 3 per email and 20 per client address per hour;
- invitation and reset completion: 20 per client address in 15 minutes.

Every count-and-record runs under a transaction-scoped advisory lock on its bucket and key,
so parallel requests cannot pass the same check (B2-S05). A password, code or reset-code
check first reserves a failure slot for the account (refused with 429 once 5 are used);
the slot is released only when the check succeeds, so a locked account evaluates no guess
on any path, the reset path included (B2-S02). Tokens travel only in request bodies, never
in a URL path or query string (B2-S03).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session as DbSession

from sp_api.context import AppState, Ctx, Problem, check_csrf, check_origin, csrf_token, session_token
from sp_api.mailer import send_in_background
from sp_core.auth import (
    PasswordPolicyError,
    check_password_policy,
    decrypt_secret,
    derive_key,
    encrypt_secret,
    hash_password,
    hash_token,
    new_token,
    new_totp_secret,
    totp_uri,
    verify_password,
    verify_totp,
)
from sp_core.permissions import Action, Role
from sp_db.models import AuthThrottle, Invite, Membership, PasswordReset, Tenant, User
from sp_db.models import Session as SessionRow
from sp_db.session import global_transaction, set_context, tenant_transaction
from sp_obs import get_logger

__all__ = [
    "INVITE_HOURS",
    "PENDING_MINUTES",
    "RESET_MINUTES",
    "SignIn",
    "accept_invite",
    "choose_tenant",
    "complete_totp",
    "confirm_password_reset",
    "create_invite",
    "invite_totp_setup",
    "invite_view",
    "list_members",
    "login",
    "logout",
    "request_password_reset",
    "session_view",
]

log = get_logger("sp_api.auth")

PENDING_MINUTES = 5  # a password-only session lives this long and only reaches the TOTP step
INVITE_HOURS = 72
RESET_MINUTES = 30
TOTP_REQUIRED_ROLES = frozenset({Role.OWNER, Role.ESTIMATOR, Role.OPERATOR})
WINDOW = timedelta(minutes=15)
HOUR = timedelta(hours=1)
LOCK_FAILURES = 5
GENERIC_FAILURE = "Email, password or code is incorrect"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$")
EXPIRED_INVITE = "This invitation has expired. Ask your shop owner to send a new one."
EXPIRED_RESET = "This link has expired or was already used. Request a new one."


@dataclass(frozen=True)
class SignIn:
    """What a route returns: the JSON body, and the new cookie token if a session was created."""

    body: dict[str, Any]
    token: str | None = None
    clear_cookie: bool = False


# Input -------------------------------------------------------------------------------------------
def _str(body: dict[str, Any], key: str, *, limit: int, required: bool = True) -> str | None:
    value = body.get(key)
    if value is None or value == "":
        if required:
            raise Problem(422, "Missing field", f"{key} is required", field=key)
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise Problem(422, "Invalid field", f"{key} must be text of at most {limit} characters", field=key)
    return value


def _email(body: dict[str, Any]) -> str:
    value = _str(body, "email", limit=254)
    assert value is not None
    value = value.strip()
    if not _EMAIL.match(value) or any(c in value for c in "\r\n<>,;"):
        raise Problem(422, "Invalid email", field="email")
    return value.lower()


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _keyed(value: str) -> bytes:
    return hash_token(value.lower())


# Throttle ----------------------------------------------------------------------------------------
def _count(db: DbSession, bucket: str, key: str, since: datetime) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(AuthThrottle)
            .where(AuthThrottle.bucket == bucket, AuthThrottle.key_hash == _keyed(key), AuthThrottle.created_at > since)
        ).scalar_one()
    )


def _lock_key(db: DbSession, bucket: str, key: str) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"auth:{bucket}:{_keyed(key).hex()}"})


def _limit(state: AppState, rules: list[tuple[str, str, int, timedelta]]) -> None:
    """Count and record one attempt per rule atomically (advisory lock per key); 429 when over."""
    now = datetime.now(UTC)
    with global_transaction(state.settings.database_url) as db:
        for bucket, key, limit, window in sorted(rules):
            _lock_key(db, bucket, key)
            if _count(db, bucket, key, now - window) >= limit:
                raise Problem(
                    429,
                    "Too many requests",
                    "too many attempts; wait and try again",
                    headers={"Retry-After": str(int(window.total_seconds()))},
                )
        for bucket, key, _, _ in rules:
            db.add(AuthThrottle(bucket=bucket, key_hash=_keyed(key)))


def _reserve(state: AppState, email: str) -> int:
    """Take one of the account's 5 failure slots before checking a password or code.

    The check and the insert run under one advisory lock, so at most 5 guesses are ever
    evaluated per window however many arrive at once. Returns the slot to release on success.
    """
    with global_transaction(state.settings.database_url) as db:
        _lock_key(db, "fail", email)
        if _count(db, "fail", email, datetime.now(UTC) - WINDOW) >= LOCK_FAILURES:
            log.info("sign-in refused: account locked")
            raise Problem(
                429,
                "Account locked",
                "Too many failed attempts. Wait 15 minutes, then try again.",
                headers={"Retry-After": str(int(WINDOW.total_seconds()))},
            )
        row = AuthThrottle(bucket="fail", key_hash=_keyed(email))
        db.add(row)
        db.flush()
        return int(row.id)


def _release(state: AppState, slot: int) -> None:
    with global_transaction(state.settings.database_url) as db:
        db.execute(delete(AuthThrottle).where(AuthThrottle.id == slot))


def _failed(detail: str = GENERIC_FAILURE) -> Problem:
    log.info("sign-in failed")
    return Problem(401, "Sign-in failed", detail)


def _clear_failures(db: DbSession, email: str) -> None:
    db.execute(delete(AuthThrottle).where(AuthThrottle.bucket == "fail", AuthThrottle.key_hash == _keyed(email)))


# Sessions ----------------------------------------------------------------------------------------
def _new_session(db: DbSession, state: AppState, user_id: uuid.UUID, tenant_id: uuid.UUID | None, level: str) -> str:
    token = new_token()
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=PENDING_MINUTES) if level != "full" else timedelta(hours=state.settings.session_absolute_hours)
    db.add(
        SessionRow(
            id=hash_token(token),
            user_id=user_id,
            tenant_id=tenant_id,
            auth_level=level,
            created_at=now,
            last_seen_at=now,
            expires_at=now + lifetime,
        )
    )
    return token


def _revoke(db: DbSession, sid: bytes) -> None:
    db.execute(update(SessionRow).where(SessionRow.id == sid, SessionRow.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))


def _revoke_all(db: DbSession, user_id: uuid.UUID) -> int:
    result = db.execute(
        update(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC))
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _totp_key(state: AppState) -> bytes:
    return derive_key(state.settings.session_key, "totp-secret")


def _check_totp(db: DbSession, state: AppState, user: User, code: str | None) -> bool:
    """Verify and consume a code: the step is stored with a compare-and-set, so a code works once."""
    if not code or user.totp_secret_enc is None:
        return False
    result = verify_totp(decrypt_secret(_totp_key(state), user.totp_secret_enc), code, last_step=user.totp_last_step)
    if not result.ok or result.step is None:
        return False
    updated = db.execute(
        update(User)
        .where(User.id == user.id, (User.totp_last_step.is_(None)) | (User.totp_last_step < result.step))
        .values(totp_last_step=result.step)
    )
    return bool(updated.rowcount)  # type: ignore[attr-defined]


def login(state: AppState, request: Request, body: dict[str, Any]) -> SignIn:
    """Password step. Returns a short password-only session when TOTP follows, else a full one."""
    check_origin(request, state.settings)
    email = _email(body)
    password = _str(body, "password", limit=256)
    assert password is not None
    wanted = body.get("tenant_id")
    _limit(state, [("login_ip", _client(request), 30, WINDOW), ("login_email", email, 10, WINDOW)])
    slot = _reserve(state, email)
    tenants: list[tuple[uuid.UUID, str, str]] = []
    with global_transaction(state.settings.database_url) as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        ok = verify_password(password, user.password_hash if user else None) and user is not None and user.status == "active"
        if ok and user is not None:
            tenants = [
                (row[0], row[1], row[2])
                for row in db.execute(text("SELECT tenant_id, tenant_name, role FROM sp_login_tenants(:u)"), {"u": user.id})
            ]
    if wanted is not None:
        tenants = [t for t in tenants if str(t[0]) == str(wanted)]
    if not ok or user is None or not tenants:
        raise _failed()  # the reserved slot stays: it counts as a failure
    # The second factor is required if any role the person holds needs it; no tenant is named before it (B2-S07).
    needs_totp = user.totp_enabled_at is not None or any(Role(t[2]) in TOTP_REQUIRED_ROLES for t in tenants)
    if needs_totp and (user.totp_secret_enc is None or user.totp_enabled_at is None):
        _release(state, slot)
        raise Problem(403, "Authenticator required", "this role needs an authenticator; ask the shop owner for a new invitation")
    single = tenants[0][0] if len(tenants) == 1 else None
    with global_transaction(state.settings.database_url) as db:
        old = session_token(request)
        if old:
            _revoke(db, hash_token(old))  # no session fixation: a new token on every authentication (ASVS 7.2.4)
        if needs_totp:
            level = "password"
        else:
            level = "full" if single is not None else "choose_tenant"
            _clear_failures(db, email)
        token = _new_session(db, state, user.id, single, level)
    if needs_totp:
        _release(state, slot)  # the password was right; only real failures count
    log.info("sign-in password step passed", extra={"user_id": str(user.id), "next": level})
    csrf = csrf_token(state.settings.session_key, hash_token(token))
    if level == "choose_tenant":
        return SignIn({"next": "choose_tenant", "tenants": _tenant_choices(tenants), "csrf_token": csrf}, token)
    return SignIn({"next": "totp" if needs_totp else "done", "csrf_token": csrf}, token)


def _tenant_choices(tenants: list[tuple[uuid.UUID, str, str]]) -> list[dict[str, str]]:
    return [{"tenant_id": str(t[0]), "name": t[1], "role": t[2]} for t in tenants]


def _staged_session(state: AppState, request: Request, level: str) -> tuple[bytes, SessionRow, User]:
    token = session_token(request)
    if not token:
        raise Problem(401, "Not signed in", "start again with your email and password")
    sid = hash_token(token)
    with global_transaction(state.settings.database_url) as db:
        row = db.execute(
            select(SessionRow, User)
            .join(User, User.id == SessionRow.user_id)
            .where(
                SessionRow.id == sid,
                SessionRow.auth_level == level,
                SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > datetime.now(UTC),
            )
        ).first()
    if row is None:
        raise Problem(401, "Not signed in", "start again with your email and password")
    check_csrf(request, state.settings, sid)
    return sid, row[0], row[1]


def complete_totp(state: AppState, request: Request, body: dict[str, Any]) -> SignIn:
    """TOTP step: the password-only session is ended and a new session is issued (full, or tenant choice)."""
    sid, pending, user = _staged_session(state, request, "password")
    _limit(state, [("totp_ip", _client(request), 30, WINDOW)])
    code = _str(body, "code", limit=12)
    slot = _reserve(state, user.email)
    with global_transaction(state.settings.database_url) as db:
        fresh = db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
        ok = fresh.status == "active" and _check_totp(db, state, fresh, code)
    if not ok:
        raise _failed()
    tenants: list[tuple[uuid.UUID, str, str]] = []
    with global_transaction(state.settings.database_url) as db:
        _revoke(db, sid)
        if pending.tenant_id is None:
            tenants = [
                (r[0], r[1], r[2])
                for r in db.execute(text("SELECT tenant_id, tenant_name, role FROM sp_login_tenants(:u)"), {"u": user.id})
            ]
        level = "full" if pending.tenant_id is not None else "choose_tenant"
        new = _new_session(db, state, user.id, pending.tenant_id, level)
        _clear_failures(db, user.email)
    _release(state, slot)
    log.info("sign-in second factor passed", extra={"user_id": str(user.id), "next": level})
    csrf = csrf_token(state.settings.session_key, hash_token(new))
    if level == "choose_tenant":
        return SignIn({"next": "choose_tenant", "tenants": _tenant_choices(tenants), "csrf_token": csrf}, new)
    return SignIn({"next": "done", "csrf_token": csrf}, new)


def choose_tenant(state: AppState, request: Request, body: dict[str, Any]) -> SignIn:
    """After every factor: the person picks one of their shops; a new full session for that shop only."""
    sid, _, user = _staged_session(state, request, "choose_tenant")
    wanted = _str(body, "tenant_id", limit=40)
    with global_transaction(state.settings.database_url) as db:
        tenants = [r[0] for r in db.execute(text("SELECT tenant_id FROM sp_login_tenants(:u)"), {"u": user.id})]
        chosen = next((t for t in tenants if str(t) == wanted), None)
        if chosen is None or user.status != "active":
            raise Problem(404, "Not found")
        _revoke(db, sid)
        new = _new_session(db, state, user.id, chosen, "full")
    log.info("sign-in complete", extra={"user_id": str(user.id)})
    return SignIn({"next": "done", "csrf_token": csrf_token(state.settings.session_key, hash_token(new))}, new)


def logout(ctx: Ctx, *, everywhere: bool = False) -> SignIn:
    with global_transaction(ctx.state.settings.database_url) as db:
        if everywhere:
            ended = _revoke_all(db, ctx.user_id)
        else:
            _revoke(db, ctx.session_id)
            ended = 1
    log.info("signed out", extra={"user_id": str(ctx.user_id), "sessions_ended": ended})
    return SignIn({"status": "signed out", "sessions_ended": ended}, clear_cookie=True)


def session_view(ctx: Ctx) -> dict[str, Any]:
    with global_transaction(ctx.state.settings.database_url) as db:
        user = db.execute(select(User).where(User.id == ctx.user_id)).scalar_one()
        session = db.execute(select(SessionRow).where(SessionRow.id == ctx.session_id)).scalar_one()
    return {
        "user_id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "tenant_id": str(ctx.tenant_id),
        "role": ctx.role.value,
        "totp_enabled": user.totp_enabled_at is not None,
        "expires_at": session.expires_at.isoformat(),
        "idle_minutes": ctx.state.settings.session_idle_minutes,
        "csrf_token": csrf_token(ctx.state.settings.session_key, ctx.session_id),
    }


# Invitations -------------------------------------------------------------------------------------
def create_invite(ctx: Ctx, db: DbSession, body: dict[str, Any]) -> dict[str, Any]:
    """Owner invites a person with one role; the link is emailed, valid 72 hours, used once."""
    ctx.require(Action.MANAGE_USERS, "invite", uuid.UUID(int=0))
    email = _email(body)
    role = body.get("role")
    if role not in ("owner", "estimator", "office"):
        raise Problem(422, "Invalid role", "role is owner, estimator or office", field="role")
    member = db.execute(select(Membership.id).join(User, User.id == Membership.user_id).where(User.email == email)).scalar_one_or_none()
    if member is not None:
        raise Problem(409, "Already a member")
    token = new_token()
    now = datetime.now(UTC)
    invite = Invite(
        tenant_id=ctx.tenant_id,
        email=email,
        role=role,
        token_hash=hash_token(token),
        created_by=ctx.user_id,
        created_at=now,
        expires_at=now + timedelta(hours=INVITE_HOURS),
    )
    db.add(invite)
    db.flush()
    shop = db.execute(select(Tenant.name)).scalar_one()
    ctx.audit(db, "invite.created", "invite", invite.id, None, {"role": role})
    link = f"{ctx.state.settings.public_base_url}/invite#token={token}"  # fragment: never sent to a server or logged
    ctx.state.mailer.send(
        to=email,
        subject=f"Invitation: join {shop} on SupplementPacket",
        body=(
            f"You have been invited to {shop} on SupplementPacket as {role}.\n\n"
            f"Open this link within 72 hours to set your password and authenticator:\n{link}\n\n"
            "If you did not expect this, ignore this email."
        ),
    )
    return {"id": str(invite.id), "email": email, "role": role, "expires_at": invite.expires_at.isoformat()}


def list_members(ctx: Ctx, db: DbSession) -> dict[str, Any]:
    ctx.require(Action.MANAGE_USERS, "invite", uuid.UUID(int=0))
    members = db.execute(select(Membership, User).join(User, User.id == Membership.user_id).order_by(User.email)).all()
    invites = db.execute(select(Invite).where(Invite.accepted_at.is_(None)).order_by(Invite.created_at.desc())).scalars()
    return {
        "members": [
            {"user_id": str(u.id), "email": u.email, "role": m.role, "status": u.status, "totp_enabled": u.totp_enabled_at is not None}
            for m, u in members
        ],
        "pending_invites": [{"id": str(i.id), "email": i.email, "role": i.role, "expires_at": i.expires_at.isoformat()} for i in invites],
    }


def _invite_tenant(state: AppState, token: str) -> tuple[uuid.UUID, uuid.UUID]:
    with global_transaction(state.settings.database_url) as db:
        row = db.execute(text("SELECT invite_id, tenant_id FROM sp_invite_lookup(:h)"), {"h": hash_token(token)}).first()
    if row is None:
        raise Problem(404, "Not found")
    return row[0], row[1]


def _open_invite(db: DbSession, invite_id: uuid.UUID, *, lock: bool = False) -> Invite:
    query = select(Invite).where(Invite.id == invite_id)
    invite = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if invite is None:
        raise Problem(404, "Not found")
    if invite.accepted_at is not None or invite.expires_at <= datetime.now(UTC):
        raise Problem(410, "Invitation expired", EXPIRED_INVITE)
    return invite


def _token(body: dict[str, Any]) -> str:
    token = _str(body, "token", limit=128)
    assert token is not None
    return token


def invite_view(state: AppState, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    check_origin(request, state.settings)
    _limit(state, [("invite_ip", _client(request), 60, WINDOW)])
    invite_id, tenant_id = _invite_tenant(state, _token(body))
    with tenant_transaction(state.settings.database_url, tenant_id=tenant_id, user_id=None, actor_role=None, correlation_id=None) as db:
        invite = _open_invite(db, invite_id)
        shop = db.execute(select(Tenant.name)).scalar_one()
        exists = db.execute(select(User.id).where(User.email == invite.email)).scalar_one_or_none() is not None
        return {
            "email": invite.email,
            "role": invite.role,
            "shop": shop,
            "account_exists": exists,
            "totp_required": Role(invite.role) in TOTP_REQUIRED_ROLES,
            "expires_at": invite.expires_at.isoformat(),
        }


def invite_totp_setup(state: AppState, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """A new authenticator secret for this invitation, kept encrypted until the invitation is accepted."""
    check_origin(request, state.settings)
    _limit(state, [("invite_ip", _client(request), 20, WINDOW)])
    invite_id, tenant_id = _invite_tenant(state, _token(body))
    with tenant_transaction(state.settings.database_url, tenant_id=tenant_id, user_id=None, actor_role=None, correlation_id=None) as db:
        invite = _open_invite(db, invite_id, lock=True)
        if db.execute(select(User.id).where(User.email == invite.email)).scalar_one_or_none() is not None:
            raise Problem(409, "Account exists", "sign in with your existing password and authenticator to accept")
        secret = new_totp_secret()
        invite.totp_pending_enc = encrypt_secret(_totp_key(state), secret)
        return {"secret": secret, "otpauth_uri": totp_uri(secret, invite.email)}


def accept_invite(state: AppState, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Set a password and authenticator (new account) or prove the existing ones, then join the tenant."""
    check_origin(request, state.settings)
    token = _token(body)
    _limit(state, [("invite_ip", _client(request), 20, WINDOW), ("invite_token", token, 10, WINDOW)])
    invite_id, tenant_id = _invite_tenant(state, token)
    password = _str(body, "password", limit=256)
    assert password is not None
    code = _str(body, "totp_code", limit=12, required=False)
    display_name = _str(body, "display_name", limit=120, required=False)
    now = datetime.now(UTC)
    slot: int | None = None
    with tenant_transaction(state.settings.database_url, tenant_id=tenant_id, user_id=None, actor_role=None, correlation_id=None) as db:
        invitee = _open_invite(db, invite_id).email
        exists = db.execute(select(User.id).where(User.email == invitee)).scalar_one_or_none() is not None
    if exists:
        slot = _reserve(state, invitee)  # proving an existing account's password and code is a sign-in attempt
    with tenant_transaction(state.settings.database_url, tenant_id=tenant_id, user_id=None, actor_role=None, correlation_id=None) as db:
        invite = _open_invite(db, invite_id, lock=True)
        role = Role(invite.role)
        user = db.execute(select(User).where(User.email == invite.email).with_for_update()).scalar_one_or_none()
        if user is not None:
            if user.status != "active" or not verify_password(password, user.password_hash):
                raise _failed()
            if (user.totp_enabled_at is not None or role in TOTP_REQUIRED_ROLES) and not _check_totp(db, state, user, code):
                raise _failed()
        else:
            try:
                check_password_policy(password, email=invite.email)
            except PasswordPolicyError as exc:
                raise Problem(422, "Password not accepted", str(exc), field="password") from exc
            secret_enc = invite.totp_pending_enc
            enabled: datetime | None = None
            last_step: int | None = None
            if secret_enc is not None and code:
                result = verify_totp(decrypt_secret(_totp_key(state), secret_enc), code, last_step=None)
                if not result.ok:
                    raise Problem(422, "Authenticator code incorrect", "check the time on your phone and enter the current code")
                enabled, last_step = now, result.step
            elif role in TOTP_REQUIRED_ROLES:
                raise Problem(422, "Authenticator required", "set up the authenticator and enter its current code", field="totp_code")
            user = User(
                email=invite.email,
                password_hash=hash_password(password),
                display_name=display_name,
                totp_secret_enc=secret_enc if enabled else None,
                totp_enabled_at=enabled,
                totp_last_step=last_step if enabled else None,
                password_changed_at=now,
            )
            db.add(user)
            db.flush()
        db.add(Membership(tenant_id=tenant_id, user_id=user.id, role=role.value))
        invite.accepted_at = now
        invite.accepted_user_id = user.id
        invite.totp_pending_enc = None
        db.flush()
        set_context(
            db, tenant_id=tenant_id, user_id=user.id, actor_role=role.value, correlation_id=getattr(request.state, "correlation_id", None)
        )
        db.execute(
            text("SELECT sp_audit(:t, 'invite.accepted', 'invite', :i, NULL, CAST(:a AS jsonb))"),
            {"t": tenant_id, "i": invite.id, "a": f'{{"role": "{role.value}"}}'},
        )
        user_id = user.id
    if slot is not None:
        _release(state, slot)
    log.info("invitation accepted", extra={"user_id": str(user_id)})
    return {"status": "accepted", "next": "sign_in"}


# Password reset ----------------------------------------------------------------------------------
RESET_REQUEST_FLOOR_SECONDS = 0.25  # every reset request takes at least this long (B2-S04)


def request_password_reset(state: AppState, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Always the same answer in the same time; a link goes out only when an active account has this email.

    The email is handed to a background sender and the response is padded to a fixed floor, so
    neither the SMTP round trip nor the extra insert shows whether the account exists (ASVS 6.3.8).
    """
    started = time.monotonic()
    try:
        check_origin(request, state.settings)
        email = _email(body)
        _limit(state, [("reset_ip", _client(request), 20, HOUR), ("reset_email", email, 3, HOUR)])
        token = new_token()
        with global_transaction(state.settings.database_url) as db:
            user = db.execute(select(User).where(User.email == email, User.status == "active")).scalar_one_or_none()
            if user is not None:
                now = datetime.now(UTC)
                db.add(
                    PasswordReset(
                        user_id=user.id, token_hash=hash_token(token), created_at=now, expires_at=now + timedelta(minutes=RESET_MINUTES)
                    )
                )
                db.flush()
                send_in_background(
                    state.mailer,
                    to=user.email,
                    subject="Password reset: SupplementPacket",
                    body=(
                        "Someone asked to reset the password for this email on SupplementPacket.\n\n"
                        "Open this link within 30 minutes to choose a new password:\n"
                        f"{state.settings.public_base_url}/reset#token={token}\n\n"
                        "You will still need your authenticator code. If you did not ask, ignore this email."
                    ),
                )
        return {"status": "If the address has an account, a reset link was sent."}
    finally:
        time.sleep(max(0.0, RESET_REQUEST_FLOOR_SECONDS - (time.monotonic() - started)))


def confirm_password_reset(state: AppState, request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """New password from a valid link; the TOTP code is still required and counts against the same
    per-account lock as sign-in (refused while locked, even when correct; B2-S02); every session
    ends; no sign-in."""
    check_origin(request, state.settings)
    _limit(state, [("reset_confirm_ip", _client(request), 20, WINDOW)])
    token = _str(body, "token", limit=128)
    password = _str(body, "password", limit=256)
    assert token is not None and password is not None
    code = _str(body, "totp_code", limit=12, required=False)
    now = datetime.now(UTC)
    with global_transaction(state.settings.database_url) as db:
        reset = db.execute(select(PasswordReset).where(PasswordReset.token_hash == hash_token(token))).scalar_one_or_none()
        if reset is None or reset.used_at is not None or reset.expires_at <= now:
            raise Problem(410, "Link expired", EXPIRED_RESET)
        email = db.execute(select(User.email).where(User.id == reset.user_id, User.status == "active")).scalar_one_or_none()
    if email is None:
        raise Problem(410, "Link expired", EXPIRED_RESET)
    slot = _reserve(state, email)  # 429 while the account is locked, whatever the code
    try:
        check_password_policy(password, email=email)
    except PasswordPolicyError as exc:
        _release(state, slot)
        raise Problem(422, "Password not accepted", str(exc), field="password") from exc
    with global_transaction(state.settings.database_url) as db:
        reset = db.execute(select(PasswordReset).where(PasswordReset.id == reset.id).with_for_update()).scalar_one()
        if reset.used_at is not None or reset.expires_at <= now:
            raise Problem(410, "Link expired", EXPIRED_RESET)
        user = db.execute(select(User).where(User.id == reset.user_id).with_for_update()).scalar_one()
        totp_ok = user.totp_enabled_at is None or _check_totp(db, state, user, code)
    if not totp_ok:
        raise _failed("The authenticator code is incorrect")  # the reserved slot stays: a failure
    with global_transaction(state.settings.database_url) as db:
        db.execute(update(User).where(User.id == reset.user_id).values(password_hash=hash_password(password), password_changed_at=now))
        db.execute(update(PasswordReset).where(PasswordReset.user_id == reset.user_id, PasswordReset.used_at.is_(None)).values(used_at=now))
        ended = _revoke_all(db, reset.user_id)
        _clear_failures(db, email)
    _release(state, slot)
    log.info("password reset", extra={"user_id": str(reset.user_id), "sessions_ended": ended})
    return {"status": "Password changed. Sign in with the new password.", "next": "sign_in", "sessions_ended": ended}
