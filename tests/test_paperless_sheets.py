"""Tests for receipt Google Sheets export helpers."""

from harness.jobs_impl.paperless.client import normalize_card_last_four


def test_normalize_card_last_four_extracts_digits():
    assert normalize_card_last_four("****4242") == "4242"
    assert normalize_card_last_four("Visa ending in 1234") == "1234"


def test_normalize_card_last_four_returns_none_when_missing():
    assert normalize_card_last_four(None) is None
    assert normalize_card_last_four("123") is None
