"""FastAPI application: REST under /api/v1, RFC 9457 problems, correlation IDs (TRD 8.1).

There is deliberately no endpoint that transmits anything to an insurer (AD-05).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from sp_api.context import AppState, PermissionDenied, Problem
from sp_api.routes import router
from sp_core.settings import Settings, get_settings
from sp_db.session import get_engine
from sp_files import LocalObjectStore, ObjectStore
from sp_obs import configure_logging, correlation_scope, get_logger

__all__ = ["create_app"]

log = get_logger("sp_api")
PROBLEM = "application/problem+json"


def _problem_response(problem: Problem, correlation_id: str | None) -> JSONResponse:
    body = problem.body()
    if correlation_id:
        body["correlation_id"] = correlation_id
    return JSONResponse(body, status_code=problem.status, media_type=PROBLEM)


def _db_problem(exc: DBAPIError) -> Problem:
    orig = exc.orig
    if isinstance(orig, pg_errors.InsufficientPrivilege):
        return Problem(403, "Forbidden", "refused by a database rule")
    if isinstance(orig, pg_errors.UniqueViolation):
        return Problem(409, "Conflict", "a record with the same identity already exists")
    if isinstance(orig, pg_errors.CheckViolation | pg_errors.NotNullViolation):
        return Problem(422, "Invalid", "refused by a data rule")
    if isinstance(orig, pg_errors.ForeignKeyViolation):
        return Problem(404, "Not found")
    if isinstance(orig, pg_errors.RaiseException):
        return Problem(409, "Refused", "refused by an integrity rule")
    if isinstance(orig, pg_errors.InvalidTextRepresentation | pg_errors.DataError):
        return Problem(422, "Invalid value")
    return Problem(500, "Database error")


def create_app(settings: Settings | None = None, store: ObjectStore | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="SupplementPacket API", version="0.1.0-b1", docs_url=None, redoc_url=None)
    app.state.sp = AppState(settings=settings, store=store or LocalObjectStore(settings.storage_root()))
    log.info("api starting", extra={"settings_fingerprint": settings.fingerprint()})

    @app.middleware("http")
    async def correlation(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-correlation-id")
        try:
            cid = str(uuid.UUID(incoming)) if incoming else None
        except ValueError:
            cid = None
        with correlation_scope(cid) as correlation_id:
            request.state.correlation_id = correlation_id
            if settings.read_only and request.method not in ("GET", "HEAD", "OPTIONS"):
                response: Response = _problem_response(Problem(503, "Read-only", "the application is read-only"), correlation_id)
            else:
                response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            route = request.scope.get("route")
            log.info(
                "request",
                extra={"method": request.method, "route": getattr(route, "path", None), "status": response.status_code},
            )
            return response

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        if isinstance(exc, PermissionDenied):
            ctx = getattr(request.state, "ctx", None)
            if ctx is not None:
                ctx.record_denial(exc)
            log.warning("permission denied", extra={"action": exc.action.value, "entity_type": exc.entity_type})
        return _problem_response(exc, getattr(request.state, "correlation_id", None))

    @app.exception_handler(DBAPIError)
    async def db_handler(request: Request, exc: DBAPIError) -> JSONResponse:
        problem = _db_problem(exc)
        log.warning("database refusal", extra={"error_type": type(exc.orig).__name__, "status": problem.status})
        return _problem_response(problem, getattr(request.state, "correlation_id", None))

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> Any:
        try:
            with get_engine(settings.database_url).connect() as conn:
                conn.execute(text("SELECT 1 FROM alembic_version")).first()
        except Exception:  # noqa: BLE001 - readiness reports, never raises
            return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
        return {"status": "ready", "database": "up"}

    app.include_router(router, prefix="/api/v1")
    return app
