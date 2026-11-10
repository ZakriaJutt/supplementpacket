"""Job runner: claim with SKIP LOCKED, one tenant per job, compare-and-set transitions.

TRD 8.5, R-01, R-02. The worker never approves, freezes or marks sent; its actor role is
"worker" and the database triggers refuse those changes from it.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from sp_core.jobs import decide_transition
from sp_core.settings import Settings
from sp_db.session import global_transaction, tenant_transaction
from sp_files import ObjectStore
from sp_obs import correlation_scope, get_logger

__all__ = ["ClaimedJob", "JobFailure", "Outcome", "Worker", "apply_event"]

log = get_logger("sp_worker")


@dataclass(frozen=True)
class ClaimedJob:
    job_id: uuid.UUID
    tenant_id: uuid.UUID
    kind: str
    subject_id: uuid.UUID
    state_version: int
    attempt: int
    correlation_id: uuid.UUID


@dataclass(frozen=True)
class Outcome:
    state: str  # succeeded | partial
    result: dict[str, Any] | None = None


class JobFailure(Exception):
    def __init__(self, error_code: str, *, retryable: bool) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.retryable = retryable


Handler = Callable[[Session, ClaimedJob, ObjectStore, dict[str, Any] | None], Outcome]


def _cas(db: Session, job_id: uuid.UUID, target: str, based_on: int, **fields: Any) -> bool:
    current = db.execute(text("SELECT state, state_version FROM jobs WHERE id = :id FOR UPDATE"), {"id": job_id}).first()
    if current is None:
        return False
    decision = decide_transition(current[0], current[1], target, based_on)
    if not decision.accepted:
        log.info("stale job transition discarded", extra={"job_id": str(job_id), "target": target, "reason": decision.reason})
        return False
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    db.execute(
        text(
            f"UPDATE jobs SET state = :target, state_version = :new_version, updated_at = now()"
            f"{', ' + sets if sets else ''} WHERE id = :id AND state_version = :based_on"
        ),
        {"target": target, "new_version": decision.new_version, "id": job_id, "based_on": based_on, **fields},
    )
    return True


def apply_event(db_url: str, tenant_id: uuid.UUID, job_id: uuid.UUID, target: str, based_on_version: int) -> bool:
    """Apply a (possibly late or duplicate) job event; stale events are discarded and logged."""
    with tenant_transaction(db_url, tenant_id=tenant_id, user_id=None, actor_role="worker", correlation_id=None) as db:
        return _cas(db, job_id, target, based_on_version)


class Worker:
    def __init__(self, settings: Settings, store: ObjectStore, handlers: dict[str, Handler]) -> None:
        self.settings = settings
        self.store = store
        self.handlers = handlers

    def claim(self) -> ClaimedJob | None:
        with global_transaction(self.settings.database_url) as db:
            row = db.execute(
                text("SELECT * FROM sp_claim_job(:kinds, :lock)"),
                {"kinds": list(self.handlers), "lock": self.settings.job_lock_seconds},
            ).first()
        if row is None:
            return None
        return ClaimedJob(*row)

    def sweep(self) -> int:
        with global_transaction(self.settings.database_url) as db:
            return int(db.execute(text("SELECT sp_sweep_jobs()")).scalar() or 0)

    def run_one(self) -> ClaimedJob | None:
        job = self.claim()
        if job is None:
            return None
        with correlation_scope(str(job.correlation_id)):
            log.info("job started", extra={"job_id": str(job.job_id), "kind": job.kind, "attempt": job.attempt})
            handler = self.handlers[job.kind]
            try:
                with tenant_transaction(
                    self.settings.database_url,
                    tenant_id=job.tenant_id,
                    user_id=None,
                    actor_role="worker",
                    correlation_id=str(job.correlation_id),
                ) as db:
                    stored = db.execute(text("SELECT result FROM jobs WHERE id = :id"), {"id": job.job_id}).scalar()
                    outcome = handler(db, job, self.store, stored)
                    _cas(
                        db,
                        job.job_id,
                        outcome.state,
                        job.state_version,
                        result=json.dumps(outcome.result) if outcome.result is not None else None,
                        locked_until=None,
                    )
                log.info("job finished", extra={"job_id": str(job.job_id), "state": outcome.state})
            except JobFailure as failure:
                self._fail(job, failure.error_code, failure.retryable)
            except Exception as exc:  # noqa: BLE001 - any crash is a retryable failure, logged without text
                log.warning("job crashed", extra={"job_id": str(job.job_id), "error_type": type(exc).__name__})
                self._fail(job, "crashed", True)
        return job

    def _fail(self, job: ClaimedJob, code: str, retryable: bool) -> None:
        with tenant_transaction(
            self.settings.database_url, tenant_id=job.tenant_id, user_id=None, actor_role="worker", correlation_id=str(job.correlation_id)
        ) as db:
            max_attempts = db.execute(text("SELECT max_attempts FROM jobs WHERE id = :id"), {"id": job.job_id}).scalar() or 0
            target = "queued" if retryable and job.attempt < max_attempts else "failed"
            _cas(db, job.job_id, target, job.state_version, error_code=code, locked_until=None)
        log.info("job not completed", extra={"job_id": str(job.job_id), "state": target, "error_code": code})

    def heartbeat(self) -> None:
        path = Path(self.settings.worker_heartbeat_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(datetime.now(UTC).isoformat())

    def run_forever(self, stop: Callable[[], bool] = lambda: False) -> None:
        while not stop():
            self.heartbeat()
            self.sweep()
            if self.run_one() is None:
                time.sleep(self.settings.worker_poll_seconds)
