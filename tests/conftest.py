"""Shared fixtures for DBOS + FastAPI integration tests."""

from __future__ import annotations

import pytest
from dbos import DBOS
from fastapi.testclient import TestClient

from harness.api import create_app
from harness.config import get_settings
from harness.dbos_app import launch_dbos


@pytest.fixture()
def dbos_app(tmp_path, monkeypatch):
    """Launch DBOS against an isolated SQLite database for each test."""
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("WEBHOOK_BEARER_TOKEN", "test-token")
    monkeypatch.setenv("PAPERLESS_URL", "http://paperless.test")
    monkeypatch.setenv("PAPERLESS_TOKEN", "fake")
    get_settings.cache_clear()

    import harness.dbos_app as dbos_mod

    dbos_mod._dbos = None
    dbos_mod._launched = False

    DBOS.destroy()
    launch_dbos()

    yield DBOS

    DBOS.destroy()
    dbos_mod._dbos = None
    dbos_mod._launched = False
    get_settings.cache_clear()


@pytest.fixture()
def client(dbos_app):
    """FastAPI test client with DBOS already launched."""
    return TestClient(create_app())


@pytest.fixture()
def auth_headers():
    return {"Authorization": "Bearer test-token"}
