"""Paperless-ngx REST client with DBOS-stepped side effects."""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from dbos import DBOS

from harness.config import get_settings

from .schemas import (
    CustomFieldDefinition,
    CustomFieldValue,
    DocumentPatch,
    NamedEntity,
    PaperlessDocument,
    PaperlessDocumentSummary,
    SelectOption,
)

PROCESSED_FIELD_NAME = "paperless-ai-processed"
DOLLAR_AMOUNT_FIELD = "dollar-amount"
PURCHASE_CATEGORY_FIELD = "purchase-category"
RECEIPT_DOCUMENT_TYPE = "purchase receipts"
RECEIPT_TAG = "receipts"
MAX_CONTENT_CHARS = 12_000
EMPTY_LIST_LABEL = "(none)"
NO_CONTENT_LABEL = "(no extracted text)"


def _base_url() -> str:
    url = get_settings().paperless_url.strip()
    if not url:
        raise RuntimeError("[paperless] PAPERLESS_URL is not configured.")
    return url.rstrip("/")


def _auth_headers() -> dict[str, str]:
    token = get_settings().paperless_token.strip()
    if not token:
        raise RuntimeError("[paperless] PAPERLESS_TOKEN is not configured.")
    return {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def _request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
    url = path if path.startswith("http") else f"{_base_url()}{path}"
    with _http_client() as client:
        response = client.request(method, url, headers=_auth_headers(), json=json_body)
    if not response.is_success:
        body = response.text
        raise RuntimeError(
            f"[paperless] {method} {url} -> {response.status_code} "
            f"{response.reason_phrase} {body}".strip()
        )
    if response.status_code == 204:
        return None
    return response.json()


def _collect(first_path: str) -> list[Any]:
    out: list[Any] = []
    next_path: str | None = first_path
    while next_path:
        page = _request("GET", next_path)
        out.extend(page["results"])
        next_path = page.get("next")
    return out


def id_for_name(entities: list[NamedEntity], name: str | None) -> int | None:
    if not name:
        return None
    target = name.strip().lower()
    for entity in entities:
        if entity.name.strip().lower() == target:
            return entity.id
    return None


def option_id_for_label(options: list[SelectOption], label: str | None) -> str | None:
    if not label:
        return None
    target = label.strip().lower()
    for option in options:
        if option.label.strip().lower() == target:
            return option.id
    return None


def format_monetary(amount: float, default_currency: str | None) -> str:
    currency = (default_currency or "USD").upper()
    return f"{currency}{amount:.2f}"


def _custom_field_is_set(custom_fields: list[CustomFieldValue], field_id: int) -> bool:
    return any(
        field.field == field_id and field.value is not None and field.value != ""
        for field in custom_fields
    )


def is_processed(doc: PaperlessDocument, field_id: int) -> bool:
    return _custom_field_is_set(doc.custom_fields, field_id)


def has_custom_field_value(doc: PaperlessDocument, field_id: int) -> bool:
    return _custom_field_is_set(doc.custom_fields, field_id)


def document_id_from_payload(*, body: dict[str, Any], url: str | None) -> int | None:
    raw_id = body.get("documentId") or body.get("document_id")
    if raw_id is not None:
        try:
            document_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        return document_id if document_id > 0 else None

    doc_url = str(body.get("url") or url or "")
    if not doc_url:
        return None
    parts = [part for part in urlparse(doc_url).path.split("/") if part]
    for part in reversed(parts):
        if part.isdigit():
            document_id = int(part)
            return document_id if document_id > 0 else None
    return None


def truncate_content(content: str | None) -> str:
    if not content:
        return NO_CONTENT_LABEL
    return content[:MAX_CONTENT_CHARS]


@DBOS.step()
def get_document(document_id: int) -> PaperlessDocument:
    data = _request("GET", f"/documents/{document_id}/")
    return PaperlessDocument.model_validate(data)


@DBOS.step()
def load_archive_lists() -> tuple[list[NamedEntity], list[NamedEntity], list[NamedEntity]]:
    tags = [
        NamedEntity.model_validate(item) for item in _collect("/tags/?fields=id,name&page_size=100")
    ]
    correspondents = [
        NamedEntity.model_validate(item)
        for item in _collect("/correspondents/?fields=id,name&page_size=100")
    ]
    document_types = [
        NamedEntity.model_validate(item)
        for item in _collect("/document_types/?fields=id,name&page_size=100")
    ]
    return tags, correspondents, document_types


@DBOS.step()
def update_document(document_id: int, patch: DocumentPatch) -> PaperlessDocument:
    payload = patch.model_dump(exclude_none=True)
    data = _request("PATCH", f"/documents/{document_id}/", json_body=payload)
    return PaperlessDocument.model_validate(data)


@DBOS.step()
def create_correspondent(name: str) -> NamedEntity:
    trimmed = name.strip()
    try:
        data = _request("POST", "/correspondents/", json_body={"name": trimmed})
        return NamedEntity.model_validate(data)
    except RuntimeError as error:
        page = _request("GET", f"/correspondents/?name__iexact={quote(trimmed)}")
        for item in page["results"]:
            entity = NamedEntity.model_validate(item)
            if entity.name.strip().lower() == trimmed.lower():
                return entity
        raise error


@DBOS.step()
def get_custom_field_by_name(name: str) -> CustomFieldDefinition | None:
    page = _request("GET", f"/custom_fields/?name__iexact={quote(name)}")
    results = page.get("results") or []
    if not results:
        return None
    return CustomFieldDefinition.model_validate(results[0])


@DBOS.step()
def ensure_processed_field() -> int:
    existing = _request("GET", f"/custom_fields/?name__iexact={quote(PROCESSED_FIELD_NAME)}")
    results = existing.get("results") or []
    if results:
        return int(results[0]["id"])
    created = _request(
        "POST",
        "/custom_fields/",
        json_body={"name": PROCESSED_FIELD_NAME, "data_type": "date"},
    )
    return int(created["id"])


@DBOS.step()
def list_document_ids_needing_processing(field_id: int, limit: int) -> list[int]:
    ids: list[int] = []
    next_path: str | None = "/documents/?ordering=-added&fields=id,custom_fields&page_size=100"
    while next_path and len(ids) < limit:
        page = _request("GET", next_path)
        for item in page["results"]:
            doc = PaperlessDocumentSummary.model_validate(item)
            if not _custom_field_is_set(doc.custom_fields, field_id):
                ids.append(doc.id)
            if len(ids) >= limit:
                break
        next_path = page.get("next")
    return ids


def build_processed_custom_fields(
    doc: PaperlessDocument, processed_field_id: int, *, processed_on: date | None = None
) -> list[CustomFieldValue]:
    marker = (processed_on or date.today()).isoformat()
    kept = [field for field in doc.custom_fields if field.field != processed_field_id]
    kept.append(CustomFieldValue(field=processed_field_id, value=marker))
    return kept


def merge_receipt_custom_fields(
    doc: PaperlessDocument,
    *,
    amount_field_id: int,
    category_field_id: int,
    dollar_amount: float | None,
    category_option_id: str | None,
    default_currency: str | None,
) -> list[CustomFieldValue]:
    touched = {amount_field_id, category_field_id}
    custom_fields = [field for field in doc.custom_fields if field.field not in touched]
    if dollar_amount is not None:
        custom_fields.append(
            CustomFieldValue(
                field=amount_field_id,
                value=format_monetary(dollar_amount, default_currency),
            )
        )
    if category_option_id is not None:
        custom_fields.append(CustomFieldValue(field=category_field_id, value=category_option_id))
    return custom_fields


def should_trigger_receipt(
    *,
    document_type_name: str | None,
    existing_document_type_id: int | None,
    merged_tag_ids: list[int],
    tags: list[NamedEntity],
    document_types: list[NamedEntity],
) -> bool:
    if document_type_name and document_type_name.strip().lower() == RECEIPT_DOCUMENT_TYPE:
        return True
    if existing_document_type_id is not None:
        for document_type in document_types:
            if document_type.id == existing_document_type_id:
                if document_type.name.strip().lower() == RECEIPT_DOCUMENT_TYPE:
                    return True
                break
    receipts_tag_id = id_for_name(tags, RECEIPT_TAG)
    return receipts_tag_id is not None and receipts_tag_id in merged_tag_ids
