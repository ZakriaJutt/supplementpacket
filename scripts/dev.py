"""Local start command behind `make dev` (T-2.1.2, R-17, E2E-09 adapted).

Docker is not available on this machine, so services run directly: PostgreSQL,
Redis, MinIO (S3 API, B2) and Mailpit (SMTP, B2) are the already-running local services; the API (uvicorn) and the worker are
started here in the background. Exits non-zero naming the unhealthy service.
"""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".run"
PY = ROOT / ".venv" / "bin" / "python"
TIMEOUT = 90


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env_file = ROOT / ".env"
    for line in env_file.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    return env


def _start(name: str, args: list[str], env: dict[str, str]) -> int:
    log = open(RUN / f"{name}.log", "ab")  # noqa: SIM115 - handed to the child process
    proc = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)  # noqa: S603 - fixed local commands
    (RUN / f"{name}.pid").write_text(str(proc.pid))
    return proc.pid


def _alive(name: str) -> bool:
    pid_file = RUN / f"{name}.pid"
    if not pid_file.exists():
        return False
    try:
        os.kill(int(pid_file.read_text()), 0)
    except (OSError, ValueError):
        return False
    return True


def stop() -> int:
    for name in ("api", "worker"):
        pid_file = RUN / f"{name}.pid"
        if pid_file.exists():
            with contextlib.suppress(OSError, ValueError):
                os.killpg(int(pid_file.read_text()), signal.SIGTERM)
            pid_file.unlink()
    print("stopped api and worker")
    return 0


def up() -> int:
    RUN.mkdir(exist_ok=True)
    env = _env()
    port = env.get("API_PORT", "8103")
    started = time.monotonic()
    if not _alive("api"):
        _start("api", [str(PY), "-m", "uvicorn", "sp_api.main:create_app", "--factory", "--host", "127.0.0.1", "--port", port], env)
    if not _alive("worker"):
        _start("worker", [str(PY), "-m", "sp_worker"], env)
    heartbeat = ROOT / env.get("WORKER_HEARTBEAT_PATH", ".run/worker.heartbeat")
    status = {"database": False, "storage": False, "mail": False, "api": False, "worker": False}
    while time.monotonic() - started < TIMEOUT:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=2) as resp:
                status["api"] = status["database"] = status["storage"] = resp.status == 200
        except OSError:
            status["api"] = False
        try:
            with socket.create_connection((env.get("SMTP_HOST", "127.0.0.1"), int(env.get("SMTP_PORT", "1025"))), timeout=2):
                status["mail"] = True
        except OSError:
            status["mail"] = False
        if heartbeat.exists():
            age = (datetime.now(UTC) - datetime.fromisoformat(heartbeat.read_text().strip())).total_seconds()
            status["worker"] = _alive("worker") and age < 10
        if all(status.values()):
            break
        time.sleep(0.5)
    elapsed = time.monotonic() - started
    for name, ok in status.items():
        print(f"{name:9} {'healthy' if ok else 'UNHEALTHY'}")
    print(f"api http://127.0.0.1:{port}  ready in {elapsed:.1f}s")
    unhealthy = [n for n, ok in status.items() if not ok]
    if unhealthy:
        print(f"unhealthy: {', '.join(unhealthy)} (see .run/*.log)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(stop() if sys.argv[1:] == ["stop"] else up())
