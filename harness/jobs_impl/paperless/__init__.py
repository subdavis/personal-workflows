"""Paperless ingestion job package."""

from __future__ import annotations

from fastapi import APIRouter

from . import agents, triggers  # noqa: F401 — agents registers DBOSAgents before launch


def post_launch_setup() -> None:
    triggers.apply_schedules()


def get_routers() -> list[APIRouter]:
    return [triggers.router]


def produce(limit: int | None = None, *, force: bool = False) -> int:
    return triggers.produce(limit, force=force)
