"""Paperless ingestion job package."""

from __future__ import annotations

from fastapi import APIRouter

from . import triggers


def post_launch_setup() -> None:
    triggers.apply_schedules()


def get_routers() -> list[APIRouter]:
    return [triggers.router]


def produce(limit: int | None = None) -> int:
    return triggers.produce(limit)
