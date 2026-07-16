"""The durable jobs queue and a thin enqueue helper.

There is no custom job registry: each job type is simply a DBOS workflow, and DBOS's own
workflow registry handles name lookup, enqueue-by-name, and introspection. Producers enqueue a
workflow onto the shared ``jobs`` queue; passing ``dedup_key`` sets the workflow ID, which makes
the enqueue idempotent (the same key runs at most once; reruns use a fresh key).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from dbos import DBOS, SetWorkflowID, WorkflowHandle

JOBS_QUEUE = "jobs"


def dedup_key(base: str, *, force: bool = False) -> str:
    """Return a stable workflow id, or a unique one when forcing a rerun."""
    if not force:
        return base
    return f"{base}:force:{uuid.uuid4()}"


def enqueue(
    workflow: Callable[..., Any],
    *args: Any,
    dedup_key: str | None = None,
    **kwargs: Any,
) -> WorkflowHandle[Any]:
    """Enqueue ``workflow`` on the jobs queue. ``dedup_key`` becomes the workflow ID."""
    if dedup_key is not None:
        with SetWorkflowID(dedup_key):
            return DBOS.enqueue_workflow(JOBS_QUEUE, workflow, *args, **kwargs)
    return DBOS.enqueue_workflow(JOBS_QUEUE, workflow, *args, **kwargs)
