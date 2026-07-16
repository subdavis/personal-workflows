"""Webhook, schedule, and CLI producers for Paperless ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from dbos import DBOS
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from harness.config import get_settings
from harness.jobs import enqueue
from harness.security import require_bearer

from .client import (
    document_id_from_payload,
    ensure_processed_field,
    list_document_ids_needing_processing,
)
from .workflows import process_document, process_receipt

router = APIRouter(prefix="/webhooks/paperless", tags=["paperless"])
INVALID_DOCUMENT_DETAIL = "missing or invalid document id"


class WebhookResponse(BaseModel):
    accepted: bool
    document_id: int


def _parse_document_id(body: dict[str, Any] | None, url: str | None) -> int:
    document_id = document_id_from_payload(body=body or {}, url=url)
    if document_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_DOCUMENT_DETAIL)
    return document_id


@router.post("", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_bearer)])
def paperless_webhook(
    body: dict[str, Any] | None = None,
    url: Annotated[str | None, Query()] = None,
) -> WebhookResponse:
    document_id = _parse_document_id(body, url)
    enqueue(process_document, document_id, dedup_key=f"paperless:doc:{document_id}")
    return WebhookResponse(accepted=True, document_id=document_id)


@router.post(
    "/receipt",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_bearer)],
)
def paperless_receipt_webhook(
    body: dict[str, Any] | None = None,
    url: Annotated[str | None, Query()] = None,
) -> WebhookResponse:
    document_id = _parse_document_id(body, url)
    enqueue(process_receipt, document_id, dedup_key=f"paperless:receipt:{document_id}")
    return WebhookResponse(accepted=True, document_id=document_id)


@DBOS.workflow()
def paperless_scan(scheduled_time: datetime, context: Any) -> None:
    del scheduled_time, context
    settings = get_settings()
    field_id = ensure_processed_field()
    document_ids = list_document_ids_needing_processing(field_id, settings.paperless_scan_limit)
    for document_id in document_ids:
        enqueue(process_document, document_id, dedup_key=f"paperless:doc:{document_id}")


def apply_schedules() -> None:
    settings = get_settings()
    DBOS.apply_schedules(
        [
            {
                "schedule_name": "paperless-scan",
                "workflow_fn": paperless_scan,
                "schedule": settings.paperless_scan_cron,
                "context": None,
                "queue_name": "jobs",
            }
        ]
    )


def produce(limit: int | None = None) -> int:
    settings = get_settings()
    scan_limit = limit if limit is not None else settings.paperless_scan_limit
    field_id = ensure_processed_field()
    document_ids = list_document_ids_needing_processing(field_id, scan_limit)
    for document_id in document_ids:
        enqueue(process_document, document_id, dedup_key=f"paperless:doc:{document_id}")
    return len(document_ids)
