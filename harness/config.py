"""Environment-driven settings for the harness and its jobs."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration, sourced from environment / `.env`.

    Field names map to upper-cased env vars (e.g. ``paperless_url`` -> ``PAPERLESS_URL``).
    Boolean fields accept ``yes``/``no``/``true``/``false``/``1``/``0``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- DBOS ---
    dbos_system_database_url: str = "sqlite:///./workflow-explorer.sqlite"
    dbos_app_name: str = "workflow-explorer"
    jobs_queue_concurrency: int = 1

    # --- LLM (Pydantic AI) ---
    llm_model: str = "anthropic:claude-sonnet-5"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None

    # --- Observability ---
    logfire_token: str | None = None

    # --- Webhooks ---
    webhook_bearer_token: str = "change-me"
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # --- Paperless-ngx job ---
    paperless_url: str = ""
    paperless_token: str = ""
    paperless_scan_cron: str = "*/30 * * * *"
    paperless_scan_limit: int = 25


def _sync_llm_api_keys(settings: Settings) -> None:
    """Expose LLM API keys from Settings to os.environ for Pydantic AI providers."""
    for env_var, value in (
        ("OPENAI_API_KEY", settings.openai_api_key),
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        ("OPENROUTER_API_KEY", settings.openrouter_api_key),
    ):
        if value:
            os.environ[env_var] = value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    settings = Settings()
    _sync_llm_api_keys(settings)
    return settings
