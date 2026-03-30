"""Job search pipeline digest — reads Google Sheets tracker and outputs JSON summary."""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv
load_dotenv()

import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials


DEFAULT_SPREADSHEET = "https://docs.google.com/spreadsheets/d/1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q/edit"
DEFAULT_WORKSHEET = "Sheet1"


def _extract_gid_from_url(url: str) -> Optional[int]:
    """Parse the gid (worksheet tab ID) from a Google Sheets URL, if present."""
    # gid appears as a query param (?gid=...) or fragment (#gid=...)
    parsed = urlparse(url)
    for source in [parsed.query, parsed.fragment]:
        params = parse_qs(source)
        if "gid" in params:
            try:
                return int(params["gid"][0])
            except (ValueError, IndexError):
                pass
    return None

# Column indices (0-based) matching job_agent.py schema
COL_TITLE = 0
COL_SUMMARY = 1
COL_LINK = 2
COL_DATE_ADDED = 3
COL_CONTACTS = 4
COL_NOTES = 5
COL_DATE_APPLIED = 6


def _sheet_client(service_account_json: str) -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(service_account_json, scopes=scopes)
    return gspread.authorize(creds)


def _open_worksheet(client: gspread.Client, spreadsheet: str, worksheet_name: str, gid: Optional[int] = None):
    url = spreadsheet.strip()

    # Auto-extract gid from URL if not explicitly provided
    if gid is None and (url.startswith("http://") or url.startswith("https://")):
        gid = _extract_gid_from_url(url)

    if url.startswith("http://") or url.startswith("https://"):
        spread = client.open_by_url(url)
    elif re.match(r"^[A-Za-z0-9-_]+$", url):
        spread = client.open_by_key(url)
    else:
        spread = client.open(url)

    # GID-based lookup (most reliable when a specific tab is requested)
    if gid is not None:
        for ws in spread.worksheets():
            if ws.id == gid:
                return ws

    for candidate in [worksheet_name, "Sheet1", "job tracker", "Job Tracker"]:
        try:
            return spread.worksheet(candidate)
        except WorksheetNotFound:
            continue

    # header-based fallback
    for ws in spread.worksheets():
        headers = ws.row_values(1)
        if headers and "Job Title" in headers and "Link" in headers:
            return ws

    raise RuntimeError(f"Could not find a job tracker worksheet in '{spreadsheet}'")


def get_all_rows(
    spreadsheet: str = DEFAULT_SPREADSHEET,
    worksheet_name: str = DEFAULT_WORKSHEET,
    service_account_json: Optional[str] = None,
    gid: Optional[int] = None,
) -> list[dict]:
    """Read all data rows from the job tracker sheet, skipping header and empty rows."""
    if service_account_json is None:
        service_account_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not service_account_json:
        raise ValueError(
            "Google service account JSON path required via --service-account-json "
            "or GOOGLE_APPLICATION_CREDENTIALS env var"
        )

    client = _sheet_client(service_account_json)
    ws = _open_worksheet(client, spreadsheet, worksheet_name, gid=gid)
    all_values = ws.get_all_values()

    rows = []
    for raw in all_values[1:]:  # skip header
        # pad short rows
        while len(raw) <= COL_DATE_APPLIED:
            raw.append("")
        if not any(raw):
            continue
        rows.append({
            "title": raw[COL_TITLE].strip(),
            "summary": raw[COL_SUMMARY].strip(),
            "link": raw[COL_LINK].strip(),
            "date_added": raw[COL_DATE_ADDED].strip(),
            "contacts": raw[COL_CONTACTS].strip(),
            "notes": raw[COL_NOTES].strip(),
            "date_applied": raw[COL_DATE_APPLIED].strip(),
        })
    return rows


def _parse_date(value: str) -> Optional[date]:
    """Try common date formats, return None on failure."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def classify_status(row: dict) -> str:
    """Return 'applied', 'stale', or 'not_applied'."""
    if row.get("date_applied"):
        return "applied"
    added = _parse_date(row.get("date_added", ""))
    if added and (date.today() - added) > timedelta(days=14):
        return "stale"
    return "not_applied"


def compute_stats(rows: list[dict]) -> dict:
    today = date.today()
    cutoff_7 = today - timedelta(days=7)

    applied = stale = not_applied = 0
    added_last_7 = applied_last_7 = 0

    for row in rows:
        status = row.get("status", classify_status(row))
        if status == "applied":
            applied += 1
        elif status == "stale":
            stale += 1
        else:
            not_applied += 1

        added = _parse_date(row.get("date_added", ""))
        if added and added >= cutoff_7:
            added_last_7 += 1

        app_date = _parse_date(row.get("date_applied", ""))
        if app_date and app_date >= cutoff_7:
            applied_last_7 += 1

    return {
        "total": len(rows),
        "applied": applied,
        "not_applied": not_applied,
        "stale": stale,
        "added_last_7_days": added_last_7,
        "applied_last_7_days": applied_last_7,
    }


def build_digest(
    spreadsheet: str = DEFAULT_SPREADSHEET,
    worksheet_name: str = DEFAULT_WORKSHEET,
    service_account_json: Optional[str] = None,
    gid: Optional[int] = None,
) -> dict:
    """Read the sheet, classify rows, compute stats, return digest dict."""
    rows = get_all_rows(spreadsheet, worksheet_name, service_account_json, gid=gid)
    for row in rows:
        row["status"] = classify_status(row)
    stats = compute_stats(rows)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_jobs": len(rows),
        "rows": rows,
        "stats": stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Output job tracker pipeline as JSON")
    parser.add_argument(
        "--spreadsheet",
        default=os.getenv("JOB_TRACKER_SPREADSHEET", DEFAULT_SPREADSHEET),
        help="Spreadsheet URL, ID, or name",
    )
    parser.add_argument(
        "--worksheet",
        default=os.getenv("JOB_TRACKER_WORKSHEET", DEFAULT_WORKSHEET),
        help="Worksheet tab name",
    )
    parser.add_argument(
        "--service-account-json",
        default=None,
        help="Path to Google service account JSON credentials",
    )
    parser.add_argument(
        "--gid",
        default=None,
        type=int,
        help="Worksheet tab GID (auto-extracted from spreadsheet URL if present)",
    )
    args = parser.parse_args()

    try:
        digest = build_digest(
            spreadsheet=args.spreadsheet,
            worksheet_name=args.worksheet,
            service_account_json=args.service_account_json,
            gid=args.gid,
        )
        print(json.dumps(digest, indent=2))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
