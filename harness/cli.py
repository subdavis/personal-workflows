"""Command-line entrypoints for the harness.

- ``serve``         : launch DBOS + the FastAPI webhook listener (+ cron + queue workers).
- ``populate_jobs`` : run producers once, enqueuing up to ``--limit`` jobs, then exit.
- ``run_jobs``      : consume the durable queue; with ``--limit`` drain that many then exit,
                      otherwise run forever.

The producer and consumer are separable so they can run as distinct processes (see
docker-compose) while sharing the Postgres system database.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import threading
import time

from dbos import DBOS

from .config import get_settings
from .dbos_app import launch_dbos
from .jobs import JOBS_QUEUE

_TERMINAL = ("SUCCESS", "ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED")


def _shutdown() -> None:
    # Best-effort cleanup on exit.
    with contextlib.suppress(Exception):
        DBOS.destroy()


def serve_main() -> None:
    """Launch DBOS and serve the FastAPI webhook listener."""
    import uvicorn

    launch_dbos()
    from .api import create_app

    settings = get_settings()
    app = create_app()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


def populate_jobs_main(argv: list[str] | None = None) -> None:
    """Run producers once, enqueuing up to ``--limit`` jobs."""
    parser = argparse.ArgumentParser(prog="populate_jobs")
    parser.add_argument("--limit", type=int, default=None, help="max jobs to enqueue")
    args = parser.parse_args(argv)

    launch_dbos()
    try:
        from . import jobs_impl

        enqueued = jobs_impl.produce(limit=args.limit)
        print(f"enqueued {enqueued} job(s)")
    finally:
        _shutdown()


def run_jobs_main(argv: list[str] | None = None) -> None:
    """Consume the jobs queue. Drain ``--limit`` jobs then exit, or run forever."""
    parser = argparse.ArgumentParser(prog="run_jobs")
    parser.add_argument("--limit", type=int, default=None, help="drain this many jobs then exit")
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=10.0,
        help="with --limit, seconds to wait with an empty queue before giving up",
    )
    args = parser.parse_args(argv)

    launch_dbos()

    if args.limit is None:
        # Production worker: queue workers drain continuously; block until interrupted.
        print(f"draining queue {JOBS_QUEUE!r} (Ctrl-C to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            _shutdown()
        return

    try:
        drained = _drain(limit=args.limit, idle_timeout=args.idle_timeout)
        print(f"drained {drained} job(s)")
    finally:
        _shutdown()


def _drain(*, limit: int, idle_timeout: float) -> int:
    """Wait until ``limit`` queued jobs reach a terminal state (or the queue stays empty)."""
    baseline = _terminal_count()
    last_progress = time.monotonic()
    completed = 0

    while completed < limit:
        completed = _terminal_count() - baseline
        pending = DBOS.list_queued_workflows(queue_name=JOBS_QUEUE)
        if completed >= limit:
            break
        if pending:
            last_progress = time.monotonic()
        elif time.monotonic() - last_progress > idle_timeout:
            # Nothing running and nothing enqueued for a while: stop waiting.
            break
        time.sleep(0.5)

    return min(completed, limit)


def _terminal_count() -> int:
    workflows = DBOS.list_workflows(
        queue_name=JOBS_QUEUE,
        status=list(_TERMINAL),
        load_input=False,
        load_output=False,
    )
    return len(workflows)


def main(argv: list[str] | None = None) -> None:
    """Dispatch ``python -m harness.cli <command>``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m harness.cli {serve|populate_jobs|run_jobs} [options]")
        raise SystemExit(2)
    command, rest = argv[0], argv[1:]
    if command == "serve":
        serve_main()
    elif command == "populate_jobs":
        populate_jobs_main(rest)
    elif command == "run_jobs":
        run_jobs_main(rest)
    else:
        print(f"unknown command: {command}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
