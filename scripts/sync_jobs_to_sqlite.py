"""
Syncs the job tracker Google Sheet into a local SQLite database.
Run this any time you want to refresh the local cache.

Usage:
    python scripts/sync_jobs_to_sqlite.py

DB file: data/jobs.db
"""

import os
import sys
import sqlite3
import warnings
warnings.filterwarnings("ignore")

from google.oauth2 import service_account
from googleapiclient.discovery import build

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import jobs_db  # noqa: E402

SPREADSHEET_ID = "1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q"
SHEET_RANGE = "Sheet1!A2:L"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")
SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.expanduser("~/.config/agents/gcp-service-account.json")
)

COLUMNS = [
    "company", "position_title", "job_summary", "location", "link",
    "date_added", "contacts", "notes", "outreach_date", "date_applied",
    "status", "followup_log"
]


def get_sheet_rows():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_RANGE
    ).execute()
    return result.get("values", [])


def init_db(conn):
    # Schema (and the (company, date_added, position_title) key) is owned by
    # src.jobs_db so every write path agrees on what identifies a row.
    jobs_db._ensure_schema(conn)
    conn.commit()


def sync():
    print("Fetching rows from Google Sheets...")
    rows = get_sheet_rows()
    print(f"Found {len(rows)} rows.")

    db_path = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    synced = 0
    skipped = 0
    for row in rows:
        vals = [row[i].strip() if i < len(row) else "" for i in range(len(COLUMNS))]
        company = vals[0]
        if not company:
            skipped += 1
            continue
        conn.execute(f"""
            INSERT OR REPLACE INTO jobs ({", ".join(COLUMNS)})
            VALUES ({", ".join(["?"] * len(COLUMNS))})
        """, vals)
        synced += 1

    conn.commit()
    conn.close()
    print(f"Sync complete: {synced} rows written to {db_path}, {skipped} skipped.")


if __name__ == "__main__":
    sync()
