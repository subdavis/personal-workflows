"""FastAPI app: health + webhook endpoints.

Webhook routers are contributed by individual jobs and are guarded by
:func:`harness.security.require_bearer`.
No web UI beyond health + webhooks, per the project's limitations.
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the FastAPI application, mounting all job webhook routers."""
    app = FastAPI(title="workflow-explorer", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    from . import jobs_impl

    for router in jobs_impl.get_routers():
        app.include_router(router)

    return app
