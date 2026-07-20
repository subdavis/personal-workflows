"""DBOS workflows for Paperless document classification and receipt extraction."""

from __future__ import annotations

from datetime import date

from dbos import DBOS

from harness.jobs import dedup_key, enqueue

from .agents import (
    build_classification_prompt,
    build_extraction_prompt,
    get_classifier_agent,
    get_receipt_agent,
)
from .client import (
    DOLLAR_AMOUNT_FIELD,
    PURCHASE_CATEGORY_FIELD,
    build_processed_custom_fields,
    create_correspondent,
    ensure_processed_field,
    get_correspondent,
    get_custom_field_by_name,
    get_document,
    has_custom_field_value,
    id_for_name,
    is_processed,
    load_archive_lists,
    merge_receipt_custom_fields,
    normalize_card_last_four,
    normalize_created_date,
    option_id_for_label,
    should_trigger_receipt,
    update_document,
)
from .schemas import DocumentPatch, ProcessDocumentResult, ProcessReceiptResult
from .sheets import append_receipt_row


@DBOS.step()
def current_date_iso() -> str:
    return date.today().isoformat()


@DBOS.workflow()
def process_receipt(document_id: int, *, force: bool = False) -> ProcessReceiptResult:
    doc = get_document(document_id)
    amount_field = get_custom_field_by_name(DOLLAR_AMOUNT_FIELD)
    category_field = get_custom_field_by_name(PURCHASE_CATEGORY_FIELD)
    if amount_field is None:
        raise RuntimeError(f'[paperless] custom field "{DOLLAR_AMOUNT_FIELD}" does not exist.')
    if category_field is None:
        raise RuntimeError(f'[paperless] custom field "{PURCHASE_CATEGORY_FIELD}" does not exist.')

    amount_populated = has_custom_field_value(doc, amount_field.id)
    category_populated = has_custom_field_value(doc, category_field.id)
    if not force and amount_populated and category_populated:
        return ProcessReceiptResult(document_id=document_id, status="skipped")

    category_options = category_field.extra_data.select_options
    prompt = build_extraction_prompt(category_options=category_options, content=doc.content)
    result = get_receipt_agent().run_sync(prompt).output

    category_option_id = option_id_for_label(category_options, result.purchase_category)
    custom_fields = merge_receipt_custom_fields(
        doc,
        amount_field_id=amount_field.id,
        category_field_id=category_field.id,
        dollar_amount=result.dollar_amount,
        category_option_id=category_option_id,
        default_currency=amount_field.extra_data.default_currency,
    )
    update_document(document_id, DocumentPatch(custom_fields=custom_fields))

    store_name: str | None = None
    if doc.correspondent is not None:
        store_name = get_correspondent(doc.correspondent).name

    receipt_date = normalize_created_date(doc.created) if doc.created else current_date_iso()
    category_label = result.purchase_category if category_option_id is not None else None
    append_receipt_row(
        receipt_date=receipt_date,
        store=store_name,
        category=category_label,
        card_last_four=normalize_card_last_four(result.card_last_four),
        amount=result.dollar_amount,
    )

    return ProcessReceiptResult(
        document_id=document_id,
        status="processed",
        dollar_amount=result.dollar_amount,
        purchase_category=result.purchase_category if category_option_id is not None else None,
    )


@DBOS.workflow()
def process_document(document_id: int, *, force: bool = False) -> ProcessDocumentResult:
    processed_field_id = ensure_processed_field()
    doc = get_document(document_id)
    if not force and is_processed(doc, processed_field_id):
        return ProcessDocumentResult(document_id=document_id, status="skipped")

    tags, correspondents, document_types = load_archive_lists()
    prompt = build_classification_prompt(
        tags=tags,
        correspondents=correspondents,
        document_types=document_types,
        content=doc.content,
    )
    classification = get_classifier_agent().run_sync(prompt).output

    new_tag_ids = [
        tag_id
        for name in classification.tag_names
        if (tag_id := id_for_name(tags, name)) is not None
    ]
    merged_tags = list(dict.fromkeys([*doc.tags, *new_tag_ids]))

    correspondent_id: int | None = None
    if doc.correspondent is None:
        correspondent_id = id_for_name(correspondents, classification.correspondent_name)
        proposed = classification.correspondent_name
        if correspondent_id is None and proposed and proposed.strip():
            correspondent_id = create_correspondent(proposed).id

    document_type_id: int | None = None
    if doc.document_type is None:
        document_type_id = id_for_name(document_types, classification.document_type_name)

    custom_fields = build_processed_custom_fields(
        doc,
        processed_field_id,
        processed_on=date.fromisoformat(current_date_iso()),
    )
    patch = DocumentPatch(
        title=classification.title,
        tags=merged_tags,
        custom_fields=custom_fields,
    )
    if correspondent_id is not None:
        patch.correspondent = correspondent_id
    if document_type_id is not None:
        patch.document_type = document_type_id

    created_raw = classification.document_date or doc.created
    if created_raw:
        patch.created = normalize_created_date(created_raw)

    update_document(document_id, patch)

    receipt_triggered = should_trigger_receipt(
        document_type_name=classification.document_type_name,
        existing_document_type_id=doc.document_type,
        merged_tag_ids=merged_tags,
        tags=tags,
        document_types=document_types,
    )
    if receipt_triggered:
        enqueue(
            process_receipt,
            document_id,
            force=force,
            dedup_key=dedup_key(f"paperless:receipt:{document_id}", force=force),
        )

    return ProcessDocumentResult(
        document_id=document_id,
        status="processed",
        title=classification.title,
        tag_ids=merged_tags,
        correspondent_id=doc.correspondent if doc.correspondent is not None else correspondent_id,
        document_type_id=doc.document_type if doc.document_type is not None else document_type_id,
        receipt_triggered=receipt_triggered or None,
    )
