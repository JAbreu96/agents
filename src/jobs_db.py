"""
Fast job tracker lookups via local SQLite cache (data/jobs.db).

Sync the DB first:
    python scripts/sync_jobs_to_sqlite.py

Usage:
    from src.jobs_db import get_job, get_followup_log, update_followup_log, upsert_job, delete_job
"""

import os
import sqlite3
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")


def _connect():
    path = os.path.abspath(DB_PATH)
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_job(company: str) -> Optional[dict]:
    """
    Returns the most recently added job for a company, or None if not found.
    Case-insensitive match.
    """
    conn = _connect()
    if not conn:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(company) = LOWER(?) ORDER BY date_added DESC LIMIT 1",
            (company,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_jobs_by_company(company: str) -> list[dict]:
    """Returns all tracked jobs for a company."""
    conn = _connect()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(company) = LOWER(?) ORDER BY date_added DESC",
            (company,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_followup_log(company: str) -> str:
    """
    Returns the followup_log string for a company (e.g. '2026-07-05, 2026-07-12').
    Returns '' if not found.
    """
    job = get_job(company)
    return (job or {}).get("followup_log", "") or ""


def update_followup_log(company: str, date_str: str) -> str:
    """
    Appends date_str to the followup_log for the most recent job entry.
    Enforces a max of 2 dates. Returns the updated log string, or raises
    ValueError if the cap has already been reached.
    """
    conn = _connect()
    if not conn:
        raise RuntimeError("SQLite DB not found. Run sync_jobs_to_sqlite.py first.")

    try:
        row = conn.execute(
            "SELECT company, date_added, followup_log FROM jobs "
            "WHERE LOWER(company) = LOWER(?) ORDER BY date_added DESC LIMIT 1",
            (company,)
        ).fetchone()

        if not row:
            raise ValueError(f"Company '{company}' not found in local DB.")

        existing = (row["followup_log"] or "").strip()
        dates = [d.strip() for d in existing.split(",") if d.strip()] if existing else []

        if len(dates) >= 2:
            raise ValueError(
                f"Max follow-ups (2) already reached for '{company}': {existing}"
            )

        dates.append(date_str)
        updated = ", ".join(dates)

        conn.execute(
            "UPDATE jobs SET followup_log = ? WHERE company = ? AND date_added = ?",
            (updated, row["company"], row["date_added"])
        )
        conn.commit()
        return updated
    finally:
        conn.close()


def upsert_job(item: dict) -> None:
    """
    Insert or replace a job row in the local SQLite cache.
    `item` must contain at least 'company'. 'date_added' defaults to 'unknown'.
    Silently no-ops if the DB file doesn't exist yet.
    """
    path = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                company       TEXT NOT NULL,
                date_added    TEXT NOT NULL DEFAULT '',
                position_title TEXT,
                job_summary   TEXT,
                location      TEXT,
                link          TEXT,
                contacts      TEXT,
                notes         TEXT,
                outreach_date TEXT,
                date_applied  TEXT,
                status        TEXT,
                followup_log  TEXT,
                PRIMARY KEY (company, date_added)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs (company)")
        cols = [
            "company", "position_title", "job_summary", "location", "link",
            "date_added", "contacts", "notes", "outreach_date", "date_applied",
            "status", "followup_log"
        ]
        vals = [item.get(c, "") or "" for c in cols]
        if not vals[0]:
            return
        conn.execute(
            f"INSERT OR REPLACE INTO jobs ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})",
            vals
        )
        conn.commit()
    finally:
        conn.close()


def delete_job(company: str) -> int:
    """
    Removes all rows for a company from the local SQLite cache (e.g. after archiving).
    Returns the number of rows deleted. Silently no-ops if the DB file doesn't exist.
    """
    conn = _connect()
    if not conn:
        return 0
    try:
        cur = conn.execute("DELETE FROM jobs WHERE LOWER(company) = LOWER(?)", (company,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_all_jobs() -> list[dict]:
    """Returns all jobs in the local cache."""
    conn = _connect()
    if not conn:
        return []
    try:
        rows = conn.execute("SELECT * FROM jobs ORDER BY date_added DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
