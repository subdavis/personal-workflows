"""Pydantic models for Paperless ingestion workflows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NamedEntity(BaseModel):
    id: int
    name: str


class CustomFieldValue(BaseModel):
    field: int
    value: Any = None


class SelectOption(BaseModel):
    id: str
    label: str


class CustomFieldExtraData(BaseModel):
    select_options: list[SelectOption] = Field(default_factory=list)
    default_currency: str | None = None


class CustomFieldDefinition(BaseModel):
    id: int
    name: str
    data_type: str
    extra_data: CustomFieldExtraData = Field(default_factory=CustomFieldExtraData)


class PaperlessDocument(BaseModel):
    id: int
    title: str
    content: str = ""
    tags: list[int] = Field(default_factory=list)
    correspondent: int | None = None
    document_type: int | None = None
    created: str | None = None
    custom_fields: list[CustomFieldValue] = Field(default_factory=list)


class PaperlessDocumentSummary(BaseModel):
    """Subset returned by list endpoints with ``fields=id,custom_fields``."""

    id: int
    custom_fields: list[CustomFieldValue] = Field(default_factory=list)


class DocumentPatch(BaseModel):
    title: str | None = None
    tags: list[int] | None = None
    correspondent: int | None = None
    document_type: int | None = None
    created: str | None = None
    custom_fields: list[CustomFieldValue] | None = None


class ClassificationResult(BaseModel):
    title: str
    tag_names: list[str] = Field(default_factory=list, alias="tagNames")
    correspondent_name: str | None = Field(default=None, alias="correspondentName")
    document_type_name: str | None = Field(default=None, alias="documentTypeName")
    document_date: str | None = Field(default=None, alias="documentDate")

    model_config = {"populate_by_name": True}


class ExtractionResult(BaseModel):
    dollar_amount: float | None = Field(default=None, alias="dollarAmount")
    purchase_category: str | None = Field(default=None, alias="purchaseCategory")
    card_last_four: str | None = Field(default=None, alias="cardLastFour")

    model_config = {"populate_by_name": True}


class ProcessDocumentResult(BaseModel):
    document_id: int
    status: Literal["processed", "skipped"]
    title: str | None = None
    tag_ids: list[int] | None = None
    correspondent_id: int | None = None
    document_type_id: int | None = None
    receipt_triggered: bool | None = None


class ProcessReceiptResult(BaseModel):
    document_id: int
    status: Literal["processed", "skipped"]
    dollar_amount: float | None = None
    purchase_category: str | None = None
