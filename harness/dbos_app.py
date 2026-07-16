"""DBOS application lifecycle.

Order matters (see the Pydantic AI ⇄ DBOS integration + DBOS docs):

1. configure observability
2. construct ``DBOS(config=...)``
3. import job implementations so their workflows, ``DBOSAgent``s, and scheduled workflows are
   defined **before** launch
4. ``DBOS.launch()``
5. register the durable ``jobs`` queue (after launch)
6. per-job post-launch setup: create app tables + apply cron schedules (after launch)
"""

from __future__ import annotations

import importlib

from dbos import DBOS, DBOSConfig

from .config import get_settings
from .jobs import JOBS_QUEUE
from .observability import configure_observability

_dbos: DBOS | None = None
_launched = False


def build_dbos() -> DBOS:
    """Construct the DBOS instance and import all job implementations (pre-launch)."""
    global _dbos
    if _dbos is not None:
        return _dbos

    configure_observability()
    settings = get_settings()
    config: DBOSConfig = {
        "name": settings.dbos_app_name,
        "system_database_url": settings.dbos_system_database_url,
    }
    _dbos = DBOS(config=config)

    # Import job implementations AFTER DBOS() exists so module-level DBOSAgent construction and
    # @DBOS.workflow / scheduled-workflow registration happen before launch.
    importlib.import_module("harness.jobs_impl")
    return _dbos


def launch_dbos() -> DBOS:
    """Idempotently build + launch DBOS, register the queue, and run per-job setup."""
    global _launched
    dbos = build_dbos()
    if _launched:
        return dbos

    DBOS.launch()
    _launched = True

    settings = get_settings()
    DBOS.register_queue(JOBS_QUEUE, concurrency=settings.jobs_queue_concurrency)

    # Per-job post-launch setup (DDL, schedules). Imported lazily to avoid import cycles.
    from . import jobs_impl

    jobs_impl.post_launch_setup()
    return dbos
