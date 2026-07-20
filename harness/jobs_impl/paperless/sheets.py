"""Google Sheets export for processed receipts."""

from __future__ import annotations

import os

from dbos import DBOS
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.discovery import Resource

from harness.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _credentials_path() -> str:
    settings = get_settings()
    path = (settings.google_application_credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if not path:
        raise RuntimeError(
            "[sheets] GOOGLE_APPLICATION_CREDENTIALS is not configured "
            "(path to a service account JSON key file)."
        )
    return path


def _sheets_service() -> Resource:
    credentials = service_account.Credentials.from_service_account_file(
        _credentials_path(),
        scopes=SCOPES,
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


@DBOS.step()
def append_receipt_row(
    *,
    receipt_date: str | None,
    store: str | None,
    category: str | None,
    card_last_four: str | None,
    amount: float | None,
) -> None:
    """Append one receipt row: date, store, category, card last four, amount."""
    settings = get_settings()
    spreadsheet_id = settings.google_sheets_spreadsheet_id.strip()
    if not spreadsheet_id:
        return

    worksheet = settings.google_sheets_worksheet_name.strip() or "Receipts"
    range_name = f"{worksheet}!A:E"
    row = [
        receipt_date or "",
        store or "",
        category or "",
        card_last_four or "",
        amount if amount is not None else "",
    ]

    (
        _sheets_service()
        .spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        )
        .execute()
    )
