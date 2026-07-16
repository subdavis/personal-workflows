"""Logfire / OpenTelemetry setup shared by all processes.

Both DBOS and Pydantic AI emit OpenTelemetry spans. Configuring Logfire installs a global
tracer provider that captures DBOS workflow/step spans and Pydantic AI agent/model/tool spans.
If no ``LOGFIRE_TOKEN`` is set, everything still runs; spans are just not exported.
"""

from __future__ import annotations

from .config import get_settings

_configured = False


def configure_observability() -> None:
    """Idempotently configure Logfire + Pydantic AI instrumentation."""
    global _configured
    if _configured:
        return

    import logfire

    settings = get_settings()
    logfire.configure(
        token=settings.logfire_token or None,
        service_name=settings.dbos_app_name,
        # Only ship spans when a token is present; otherwise stay local + quiet.
        send_to_logfire="if-token-present",
        console=False,
    )
    logfire.instrument_pydantic_ai()
    _configured = True
