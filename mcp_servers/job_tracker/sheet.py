import os
from datetime import date, datetime, timedelta

import gspread
from google.oauth2 import service_account

SPREADSHEET_ID = "1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q"
WORKSHEET = "Sheet1"
ARCHIVE_WORKSHEET = "Archive"
SERVICE_ACCOUNT_FILE = "/Users/joelchristabreu/Documents/agents-491602-service-account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COL_COMPANY = 0
COL_TITLE = 1
COL_SUMMARY = 2
COL_LINK = 3
COL_DATE_ADDED = 4
COL_CONTACTS = 5
COL_NOTES = 6
COL_OUTREACH = 7
COL_DATE_APPLIED = 8
COL_STATUS = 9


def _credentials():
    path = SERVICE_ACCOUNT_FILE or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def get_sheet() -> gspread.Worksheet:
    gc = gspread.authorize(_credentials())
    return gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET)


def get_archive_sheet() -> gspread.Worksheet:
    gc = gspread.authorize(_credentials())
    return gc.open_by_key(SPREADSHEET_ID).worksheet(ARCHIVE_WORKSHEET)


def _parse_date(value: str) -> date | None:
    if not value or not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _row_to_dict(row: list, row_index: int) -> dict:
    def cell(i):
        return row[i].strip() if i < len(row) and row[i] else ""

    return {
        "row_index": row_index,
        "company": cell(COL_COMPANY),
        "title": cell(COL_TITLE),
        "summary": cell(COL_SUMMARY),
        "link": cell(COL_LINK),
        "date_added": cell(COL_DATE_ADDED),
        "contacts": cell(COL_CONTACTS),
        "notes": cell(COL_NOTES),
        "outreach_date": cell(COL_OUTREACH),
    }


def read_all_rows() -> list[dict]:
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    rows = []
    for i, row in enumerate(all_values[1:], start=2):  # skip header, 1-based index
        if not row or not row[0].strip():
            continue
        rows.append(_row_to_dict(row, i))
    return rows


def mark_outreached(row_index: int, date_str: str) -> None:
    sheet = get_sheet()
    sheet.update_cell(row_index, COL_OUTREACH + 1, date_str)  # gspread uses 1-based cols


def update_status(row_index: int, status: str) -> None:
    sheet = get_sheet()
    sheet.update_cell(row_index, COL_STATUS + 1, status)


def archive_old_jobs(days: int = 60) -> list[dict]:
    """Move jobs older than `days` days from Sheet1 to Archive. Returns archived rows."""
    ws = get_sheet()
    archive_ws = get_archive_sheet()
    all_values = ws.get_all_values()
    header = all_values[0]
    cutoff = date.today() - timedelta(days=days)

    rows_to_archive = []
    row_indices_to_delete = []

    for i, row in enumerate(all_values[1:], start=2):
        if not row or not row[0].strip():
            continue
        d = _parse_date(row[COL_DATE_ADDED] if COL_DATE_ADDED < len(row) else "")
        if d and d < cutoff:
            rows_to_archive.append(row)
            row_indices_to_delete.append(i)

    if rows_to_archive:
        archive_ws.append_rows(rows_to_archive, value_input_option="USER_ENTERED")
        # Delete in reverse order so indices stay valid
        for row_idx in sorted(row_indices_to_delete, reverse=True):
            ws.delete_rows(row_idx)

    return [_row_to_dict(r, 0) for r in rows_to_archive]
