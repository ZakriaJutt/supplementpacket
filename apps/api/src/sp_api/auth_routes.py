"""Sign-in, sign-out, session, password reset and invitation routes (TRD 8.1 Auth row, B2).

These run before a tenant is known, so they do not take an Idempotency-Key; each is safe to
repeat or is limited by the throttle. The session cookie is ``__Host-sp_session``: Secure,
HttpOnly, SameSite=Lax, Path=/ and no Domain (ASVS 3.3.1, 3.3.2, 3.3.4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from sp_api.context import SESSION_COOKIE, AppState, Ctx
from sp_api.routes import get_ctx
from sp_api.services import auth

router = APIRouter()

JsonBody = dict[str, Any]


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.sp
    return state


def _respond(result: auth.SignIn, state: AppState, status: int = 200) -> JSONResponse:
    response = JSONResponse(result.body, status_code=status)
    if result.token:
        level_minutes = auth.PENDING_MINUTES if result.body.get("next") == "totp" else state.settings.session_absolute_hours * 60
        response.set_cookie(SESSION_COOKIE, result.token, max_age=level_minutes * 60, path="/", secure=True, httponly=True, samesite="lax")
    if result.clear_cookie:
        response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'  # ASVS 14.3.1
    return response


@router.post("/auth/login")
def login(request: Request, body: JsonBody = Body(...)) -> JSONResponse:
    state = _state(request)
    return _respond(auth.login(state, request, body), state)


@router.post("/auth/totp")
def totp(request: Request, body: JsonBody = Body(...)) -> JSONResponse:
    state = _state(request)
    return _respond(auth.complete_totp(state, request, body), state)


@router.post("/auth/logout")
def logout(request: Request, ctx: Ctx = Depends(get_ctx)) -> JSONResponse:
    return _respond(auth.logout(ctx), ctx.state)


@router.post("/auth/logout-all")
def logout_all(request: Request, ctx: Ctx = Depends(get_ctx)) -> JSONResponse:
    return _respond(auth.logout(ctx, everywhere=True), ctx.state)


@router.get("/auth/session")
def session(ctx: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    return auth.session_view(ctx)


@router.post("/auth/password-reset")
def password_reset(request: Request, body: JsonBody = Body(...)) -> JSONResponse:
    return JSONResponse(auth.request_password_reset(_state(request), request, body), status_code=202)


@router.post("/auth/password-reset/confirm")
def password_reset_confirm(request: Request, body: JsonBody = Body(...)) -> dict[str, Any]:
    return auth.confirm_password_reset(_state(request), request, body)


@router.get("/invites/{token}")
def invite(token: str, request: Request) -> dict[str, Any]:
    return auth.invite_view(_state(request), token)


@router.post("/invites/{token}/totp-setup")
def invite_totp(token: str, request: Request) -> dict[str, Any]:
    return auth.invite_totp_setup(_state(request), request, token)


@router.post("/invites/{token}/accept")
def invite_accept(token: str, request: Request, body: JsonBody = Body(...)) -> JSONResponse:
    return JSONResponse(auth.accept_invite(_state(request), request, token, body), status_code=201)
