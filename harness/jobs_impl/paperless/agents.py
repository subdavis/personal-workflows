# ruff: noqa: E501
"""Pydantic AI agents for Paperless ingestion."""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.durable_exec.dbos import DBOSAgent

from harness.agents import build_agent

from .client import EMPTY_LIST_LABEL, truncate_content
from .schemas import ClassificationResult, ExtractionResult, NamedEntity, SelectOption

CLASSIFIER_INSTRUCTIONS = (
    "You classify scanned documents for a Paperless-ngx archive. "
    "You are given the document text plus the archive's existing tags, correspondents, and document types. "
    "Produce a concise, human-readable title (no file extensions, no dates unless part of the name). "
    "Pick a correspondent ONLY from the provided list when one clearly matches; otherwise you may propose "
    "a new name for a clear sender not in the list, or return null if no sender is identifiable. "
    "Pick a document type ONLY from the provided list — never invent new ones. If nothing fits, return null. "
    "Pick zero or more tags ONLY from the provided tag list — never invent new tags. "
    "Choose the ones that genuinely apply. Match names exactly as they appear in the lists."
)

RECEIPT_INSTRUCTIONS = (
    "You extract structured spending data from scanned purchase receipts. "
    "Report the purchase total as the final grand total actually paid — the amount after tax, tips, and discounts, "
    "not a subtotal or any single line item. "
    "Return the total as a plain number (e.g. 42.17), with no currency symbol or thousands separators. "
    "Choose a purchase category ONLY from the list of options provided in the prompt — never invent a new one. "
    "If none clearly fits, return null. Match the category label exactly as it appears in the provided list."
)

_classifier: Agent[None, ClassificationResult] | None = None
_receipt: Agent[None, ExtractionResult] | None = None
_classifier_dbos: DBOSAgent[None, ClassificationResult] | None = None
_receipt_dbos: DBOSAgent[None, ExtractionResult] | None = None


def build_classification_prompt(
    *,
    tags: list[NamedEntity],
    correspondents: list[NamedEntity],
    document_types: list[NamedEntity],
    content: str,
) -> str:
    return "\n".join(
        [
            "Classify the following document.",
            "",
            "=== EXISTING TAGS (choose only from these) ===",
            ", ".join(tag.name for tag in tags) or EMPTY_LIST_LABEL,
            "",
            "=== EXISTING CORRESPONDENTS (prefer one of these; propose a new name only for a clear sender not listed, else null) ===",
            ", ".join(correspondent.name for correspondent in correspondents) or EMPTY_LIST_LABEL,
            "",
            "=== EXISTING DOCUMENT TYPES (choose only from these, or null) ===",
            ", ".join(document_type.name for document_type in document_types) or EMPTY_LIST_LABEL,
            "",
            "=== DOCUMENT TEXT ===",
            truncate_content(content),
        ]
    )


def build_extraction_prompt(*, category_options: list[SelectOption], content: str) -> str:
    return "\n".join(
        [
            "Extract the purchase total and spending category from this receipt.",
            "",
            "=== PURCHASE CATEGORIES (choose only one of these labels, or null) ===",
            ", ".join(option.label for option in category_options) or EMPTY_LIST_LABEL,
            "",
            "=== RECEIPT TEXT ===",
            truncate_content(content),
        ]
    )


def _build_classifier() -> Agent[None, ClassificationResult]:
    return build_agent(
        name="paperless_classifier",
        output_type=ClassificationResult,
        deps_type=type(None),
        instructions=CLASSIFIER_INSTRUCTIONS,
    )


def _build_receipt() -> Agent[None, ExtractionResult]:
    return build_agent(
        name="paperless_receipt_extractor",
        output_type=ExtractionResult,
        deps_type=type(None),
        instructions=RECEIPT_INSTRUCTIONS,
    )


def get_classifier_agent() -> DBOSAgent[None, ClassificationResult]:
    global _classifier, _classifier_dbos
    if _classifier_dbos is None:
        _classifier = _build_classifier()
        _classifier_dbos = DBOSAgent(_classifier)
    return _classifier_dbos


def get_receipt_agent() -> DBOSAgent[None, ExtractionResult]:
    global _receipt, _receipt_dbos
    if _receipt_dbos is None:
        _receipt = _build_receipt()
        _receipt_dbos = DBOSAgent(_receipt)
    return _receipt_dbos
