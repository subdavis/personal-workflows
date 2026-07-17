"""Workflow tests with mocked Paperless steps and agents."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from harness.jobs_impl.paperless.schemas import (
    ClassificationResult,
    CustomFieldDefinition,
    CustomFieldExtraData,
    CustomFieldValue,
    DocumentPatch,
    ExtractionResult,
    NamedEntity,
    PaperlessDocument,
    ProcessDocumentResult,
    ProcessReceiptResult,
    SelectOption,
)
from harness.jobs_impl.paperless.workflows import process_document, process_receipt

PROCESSED_FIELD_ID = 100
AMOUNT_FIELD_ID = 101
CATEGORY_FIELD_ID = 102

TAGS = [
    NamedEntity(id=1, name="receipts"),
    NamedEntity(id=2, name="personal"),
]
CORRESPONDENTS = [NamedEntity(id=10, name="Starbucks")]
DOCUMENT_TYPES = [NamedEntity(id=20, name="purchase receipts")]
CATEGORY_OPTIONS = [
    SelectOption(id="cat-food", label="Food & Drink"),
    SelectOption(id="cat-other", label="Other"),
]


def _sample_doc(*, processed: bool = False) -> PaperlessDocument:
    custom_fields: list[CustomFieldValue] = []
    if processed:
        custom_fields.append(CustomFieldValue(field=PROCESSED_FIELD_ID, value="2026-07-16"))
    return PaperlessDocument(
        id=42,
        title="Untitled",
        content="Starbucks receipt total $5.47",
        tags=[],
        custom_fields=custom_fields,
    )


def _amount_field() -> CustomFieldDefinition:
    return CustomFieldDefinition(
        id=AMOUNT_FIELD_ID,
        name="dollar-amount",
        data_type="monetary",
        extra_data=CustomFieldExtraData(default_currency="USD"),
    )


def _category_field() -> CustomFieldDefinition:
    return CustomFieldDefinition(
        id=CATEGORY_FIELD_ID,
        name="purchase-category",
        data_type="select",
        extra_data=CustomFieldExtraData(select_options=CATEGORY_OPTIONS),
    )


def _classifier_agent(output: ClassificationResult) -> MagicMock:
    agent = MagicMock()
    agent.run_sync.return_value = MagicMock(output=output)
    return agent


def _receipt_agent(output: ExtractionResult) -> MagicMock:
    agent = MagicMock()
    agent.run_sync.return_value = MagicMock(output=output)
    return agent


@pytest.fixture()
def classify_mocks():
    """Patch Paperless steps and classifier agent for process_document tests."""
    classification = ClassificationResult(
        title="Starbucks receipt",
        tag_names=["receipts"],
        correspondent_name="Starbucks",
        document_type_name="purchase receipts",
        document_date="2026-07-16",
    )
    with (
        patch(
            "harness.jobs_impl.paperless.workflows.ensure_processed_field",
            return_value=PROCESSED_FIELD_ID,
        ),
        patch(
            "harness.jobs_impl.paperless.workflows.get_document",
            return_value=_sample_doc(),
        ),
        patch(
            "harness.jobs_impl.paperless.workflows.load_archive_lists",
            return_value=(TAGS, CORRESPONDENTS, DOCUMENT_TYPES),
        ),
        patch(
            "harness.jobs_impl.paperless.workflows.get_classifier_agent",
            return_value=_classifier_agent(classification),
        ) as mock_get_agent,
        patch("harness.jobs_impl.paperless.workflows.update_document") as mock_update,
        patch("harness.jobs_impl.paperless.workflows.current_date_iso", return_value="2026-07-16"),
        patch("harness.jobs_impl.paperless.workflows.enqueue") as mock_enqueue,
    ):
        yield {
            "classification": classification,
            "get_agent": mock_get_agent,
            "update_document": mock_update,
            "enqueue": mock_enqueue,
        }


def test_process_document_skips_when_already_processed(dbos_app, classify_mocks):
    with patch(
        "harness.jobs_impl.paperless.workflows.get_document",
        return_value=_sample_doc(processed=True),
    ):
        result = process_document(42)

    assert result == ProcessDocumentResult(document_id=42, status="skipped")
    classify_mocks["get_agent"].return_value.run_sync.assert_not_called()
    classify_mocks["update_document"].assert_not_called()
    classify_mocks["enqueue"].assert_not_called()


def test_process_document_classifies_and_patches(dbos_app, classify_mocks):
    result = process_document(42)

    assert result.status == "processed"
    assert result.title == "Starbucks receipt"
    assert result.tag_ids == [1]
    assert result.correspondent_id == 10
    assert result.document_type_id == 20
    assert result.receipt_triggered is True

    classify_mocks["update_document"].assert_called_once()
    document_id, patch = classify_mocks["update_document"].call_args.args
    assert document_id == 42
    assert isinstance(patch, DocumentPatch)
    assert patch.title == "Starbucks receipt"
    assert patch.tags == [1]
    assert patch.correspondent == 10
    assert patch.document_type == 20
    assert patch.created == "2026-07-16"
    assert any(field.field == PROCESSED_FIELD_ID for field in patch.custom_fields or [])


def test_process_document_enqueues_receipt_workflow(dbos_app, classify_mocks):
    process_document(42)

    classify_mocks["enqueue"].assert_called_once()
    workflow, document_id = classify_mocks["enqueue"].call_args.args[:2]
    assert workflow.__name__ == "process_receipt"
    assert document_id == 42
    assert classify_mocks["enqueue"].call_args.kwargs["dedup_key"] == "paperless:receipt:42"


@pytest.fixture()
def receipt_mocks():
    """Patch Paperless steps and receipt agent for process_receipt tests."""
    extraction = ExtractionResult(dollar_amount=5.47, purchase_category="Food & Drink")
    with (
        patch(
            "harness.jobs_impl.paperless.workflows.get_document",
            return_value=_sample_doc(),
        ),
        patch(
            "harness.jobs_impl.paperless.workflows.get_custom_field_by_name",
            side_effect=lambda name: {
                "dollar-amount": _amount_field(),
                "purchase-category": _category_field(),
            }[name],
        ),
        patch(
            "harness.jobs_impl.paperless.workflows.get_receipt_agent",
            return_value=_receipt_agent(extraction),
        ) as mock_get_agent,
        patch("harness.jobs_impl.paperless.workflows.update_document") as mock_update,
    ):
        yield {
            "extraction": extraction,
            "get_agent": mock_get_agent,
            "update_document": mock_update,
        }


def test_process_receipt_skips_when_fields_populated(dbos_app, receipt_mocks):
    doc = _sample_doc()
    doc.custom_fields = [
        CustomFieldValue(field=AMOUNT_FIELD_ID, value="USD5.47"),
        CustomFieldValue(field=CATEGORY_FIELD_ID, value="cat-food"),
    ]
    with patch("harness.jobs_impl.paperless.workflows.get_document", return_value=doc):
        result = process_receipt(42)

    assert result == ProcessReceiptResult(document_id=42, status="skipped")
    receipt_mocks["get_agent"].return_value.run_sync.assert_not_called()
    receipt_mocks["update_document"].assert_not_called()


def test_process_receipt_extracts_and_patches(dbos_app, receipt_mocks):
    result = process_receipt(42)

    assert result == ProcessReceiptResult(
        document_id=42,
        status="processed",
        dollar_amount=5.47,
        purchase_category="Food & Drink",
    )

    receipt_mocks["update_document"].assert_called_once()
    document_id, patch = receipt_mocks["update_document"].call_args.args
    assert document_id == 42
    assert isinstance(patch, DocumentPatch)
    assert patch.custom_fields is not None
    amount = next(field for field in patch.custom_fields if field.field == AMOUNT_FIELD_ID)
    category = next(field for field in patch.custom_fields if field.field == CATEGORY_FIELD_ID)
    assert amount.value == "USD5.47"
    assert category.value == "cat-food"
