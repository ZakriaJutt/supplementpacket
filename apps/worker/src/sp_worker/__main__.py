"""Worker entry point: ``python -m sp_worker`` (TRD 6, IT-13)."""

from __future__ import annotations

import argparse
import signal
import sys

from sp_core.settings import get_settings
from sp_files import store_from_settings
from sp_obs import configure_logging, get_logger
from sp_worker.handlers import default_handlers
from sp_worker.runner import Worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sp_worker")
    parser.add_argument("--once", action="store_true", help="process at most one job and exit")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("sp_worker")
    log.info("worker starting", extra={"settings_fingerprint": settings.fingerprint()})
    worker = Worker(settings, store_from_settings(settings), default_handlers())
    if args.once:
        worker.heartbeat()
        worker.run_one()
        return 0
    stopping = {"flag": False}

    def _stop(*_: object) -> None:
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    worker.run_forever(lambda: stopping["flag"])
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
