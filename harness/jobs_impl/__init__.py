"""Job implementations.

Importing this package imports every job (registering their DBOS workflows, scheduled
producers, and DBOSAgents). ``harness.dbos_app`` imports it after constructing DBOS and before
launch. Add new jobs by importing their package here and wiring them into the helpers below.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import paperless


def post_launch_setup() -> None:
    """Run each job's post-launch setup (DDL, schedules) after DBOS.launch()."""
    paperless.post_launch_setup()


def get_routers() -> list[APIRouter]:
    """Collect the webhook routers contributed by each job."""
    return paperless.get_routers()


def produce(limit: int | None = None, *, force: bool = False) -> int:
    """Run each job's one-shot producer; return the total number of jobs enqueued."""
    return paperless.produce(limit, force=force)
