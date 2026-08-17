"""
Local SQLite job tracker — source of truth (data/jobs.db).

Usage:
    from src.jobs_db import get_job, get_followup_log, update_followup_log, upsert_job, delete_job
"""

import csv
import io
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")

COLUMNS = [
    "company", "position_title", "job_summary", "location", "link",
    "date_added", "contacts", "notes", "outreach_date", "date_applied",
    "status", "followup_log"
]


_JOBS_DDL = """
        CREATE TABLE IF NOT EXISTS {table} (
            company       TEXT NOT NULL,
            date_added    TEXT NOT NULL DEFAULT '',
            position_title TEXT NOT NULL DEFAULT '',
            link          TEXT NOT NULL DEFAULT '',
            job_summary   TEXT,
            location      TEXT,
            contacts      TEXT,
            notes         TEXT,
            outreach_date TEXT,
            date_applied  TEXT,
            status        TEXT,
            followup_log  TEXT,
            archived      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (company, date_added, position_title, link)
        )
"""

# The columns that identify a row, in key order.
KEY_COLUMNS = ["company", "date_added", "position_title", "link"]


def _migrate_key(conn: sqlite3.Connection) -> None:
    """
    Row identity widened twice as collisions surfaced: (company, date_added) lost
    a second role at the same company on the same day, then adding position_title
    still lost distinct requisitions posted under one title. The posting URL is
    what actually distinguishes them, so `link` completes the key. Rebuilding with
    a wider key only ever preserves more rows. No-op once migrated.
    """
    cols = conn.execute("PRAGMA table_info(jobs)").fetchall()
    if not cols:
        return
    in_pk = {row[1] for row in cols if row[5]}  # row[5] = pk position, 0 when not in PK
    if in_pk == set(KEY_COLUMNS):
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(_JOBS_DDL.format(table="jobs_migrated"))
    conn.execute(
        "INSERT OR REPLACE INTO jobs_migrated "
        "(company, date_added, position_title, link, job_summary, location, contacts, "
        " notes, outreach_date, date_applied, status, followup_log, archived) "
        "SELECT company, date_added, COALESCE(position_title, ''), COALESCE(link, ''), "
        "       job_summary, location, contacts, notes, outreach_date, date_applied, "
        "       status, followup_log, COALESCE(archived, 0) FROM jobs"
    )
    conn.execute("DROP TABLE jobs")
    conn.execute("ALTER TABLE jobs_migrated RENAME TO jobs")
    conn.commit()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(_JOBS_DDL.format(table="jobs"))
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists
    _migrate_key(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs (company)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_archived ON jobs (archived)")


def _connect(create: bool = False) -> Optional[sqlite3.Connection]:
    path = os.path.abspath(DB_PATH)
    if not create and not os.path.exists(path):
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _parse_date(value: str) -> Optional[date]:
    if not value or not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def get_job(company: str) -> Optional[dict]:
    """
    Returns the most recently added, non-archived job for a company, or None if not found.
    Case-insensitive match.
    """
    conn = _connect()
    if not conn:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(company) = LOWER(?) AND archived = 0 "
            "ORDER BY date_added DESC LIMIT 1",
            (company,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_jobs_by_company(company: str) -> list[dict]:
    """Returns all tracked, non-archived jobs for a company."""
    conn = _connect()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(company) = LOWER(?) AND archived = 0 "
            "ORDER BY date_added DESC",
            (company,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_job_by_link(link: str) -> Optional[dict]:
    """
    Returns the most recently added, non-archived job matching a link (exact,
    case-insensitive, whitespace-trimmed match), or None if not found.
    """
    link = (link or "").strip()
    if not link:
        return None
    conn = _connect()
    if not conn:
        return None
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE LOWER(TRIM(link)) = LOWER(?) AND archived = 0 "
            "ORDER BY date_added DESC LIMIT 1",
            (link,)
        ).fetchone()
        return dict(row) if row else None
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
            "SELECT company, date_added, position_title, link, followup_log FROM jobs "
            "WHERE LOWER(company) = LOWER(?) AND archived = 0 ORDER BY date_added DESC LIMIT 1",
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
            "UPDATE jobs SET followup_log = ? WHERE company = ? AND date_added = ? "
            "AND position_title = ? AND link = ?",
            (updated, row["company"], row["date_added"], row["position_title"], row["link"])
        )
        conn.commit()
        return updated
    finally:
        conn.close()


def upsert_job(item: dict) -> None:
    """
    Insert or replace a job row in the local DB.
    `item` must contain at least 'company'. 'date_added' defaults to 'unknown'.
    """
    conn = _connect(create=True)
    try:
        vals = [item.get(c, "") or "" for c in COLUMNS]
        if not vals[0]:
            return
        key = [item.get(c, "") or "" for c in KEY_COLUMNS]
        conn.execute(
            f"INSERT OR REPLACE INTO jobs ({', '.join(COLUMNS)}, archived) "
            f"VALUES ({', '.join(['?'] * len(COLUMNS))}, "
            f"COALESCE((SELECT archived FROM jobs WHERE "
            f"          {' AND '.join(f'{c} = ?' for c in KEY_COLUMNS)}), 0))",
            vals + key
        )
        conn.commit()
    finally:
        conn.close()


def _key_clause(position_title: Optional[str], link: Optional[str]) -> tuple[str, list]:
    """
    Row-identity WHERE clause. Each key column supplied narrows the target;
    omitting them widens it to every row sharing what was given, so callers
    holding only (company, date_added) keep the pre-migration group behavior.
    """
    where = ["company = ?", "date_added = ?"]
    params = []
    if position_title is not None:
        where.append("position_title = ?")
        params.append(position_title)
    if link is not None:
        where.append("link = ?")
        params.append(link)
    return " AND ".join(where), params


def update_field(company: str, date_added: str, field: str, value: str,
                 position_title: Optional[str] = None,
                 link: Optional[str] = None) -> bool:
    """
    Updates a single field on the job row identified by
    (company, date_added, position_title, link). Returns True if a row was updated.
    """
    if field not in set(COLUMNS) - {"company", "date_added"}:
        raise ValueError(f"Field '{field}' is not updatable.")
    conn = _connect()
    if not conn:
        return False
    try:
        where, extra = _key_clause(position_title, link)
        cur = conn.execute(
            f"UPDATE jobs SET {field} = ? WHERE {where}",
            [value, company, date_added] + extra
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def mark_outreached(company: str, date_added: str, outreach_date: str,
                    position_title: Optional[str] = None,
                    link: Optional[str] = None) -> bool:
    return update_field(company, date_added, "outreach_date", outreach_date,
                        position_title, link)


def update_status(company: str, date_added: str, status: str,
                  position_title: Optional[str] = None,
                  link: Optional[str] = None) -> bool:
    return update_field(company, date_added, "status", status, position_title, link)


def update_notes(company: str, date_added: str, notes: str,
                 position_title: Optional[str] = None,
                 link: Optional[str] = None) -> bool:
    return update_field(company, date_added, "notes", notes, position_title, link)


def update_contacts(company: str, date_added: str, contacts: str,
                    position_title: Optional[str] = None,
                    link: Optional[str] = None) -> bool:
    return update_field(company, date_added, "contacts", contacts, position_title, link)


def delete_job_by_key(company: str, date_added: str,
                      position_title: Optional[str] = None,
                      link: Optional[str] = None) -> bool:
    """
    Hard-deletes the job row identified by (company, date_added, position_title, link).
    Omitting the trailing key columns deletes every row sharing what was given.
    Returns True if at least one row was deleted.
    """
    conn = _connect()
    if not conn:
        return False
    try:
        where, extra = _key_clause(position_title, link)
        cur = conn.execute(f"DELETE FROM jobs WHERE {where}", [company, date_added] + extra)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_job(company: str) -> int:
    """
    Hard-deletes all rows for a company from the local DB.
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


def archive_jobs(days: int = 60, dry_run: bool = False) -> dict:
    """
    Soft-archives (sets archived=1) all non-archived jobs where date_added is
    more than `days` days ago. Archived rows are excluded from get_all_jobs()
    and company lookups by default, but stay in the same table.
    - dry_run: if True, returns which jobs would be archived without writing.
    """
    conn = _connect()
    if not conn:
        return {"dry_run": dry_run, "count": 0, "companies": []}

    try:
        cutoff = date.today() - timedelta(days=days)
        rows = conn.execute(
            "SELECT * FROM jobs WHERE archived = 0"
        ).fetchall()
        to_archive = [
            dict(r) for r in rows
            if _parse_date(r["date_added"]) and _parse_date(r["date_added"]) < cutoff
        ]

        if not dry_run and to_archive:
            conn.executemany(
                "UPDATE jobs SET archived = 1 WHERE company = ? AND date_added = ?",
                [(r["company"], r["date_added"]) for r in to_archive]
            )
            conn.commit()

        return {
            "dry_run": dry_run,
            "count": len(to_archive),
            "companies": [r["company"] for r in to_archive],
        }
    finally:
        conn.close()


def get_all_jobs(include_archived: bool = False) -> list[dict]:
    """Returns all jobs in the local DB, excluding archived rows by default."""
    conn = _connect()
    if not conn:
        return []
    try:
        query = "SELECT * FROM jobs"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY date_added DESC"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def export_csv(jobs: list[dict], fileobj) -> None:
    """Writes `jobs` as CSV (COLUMNS as header) to the given file-like object."""
    writer = csv.DictWriter(fileobj, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for job in jobs:
        writer.writerow(job)


def export_csv_string(jobs: list[dict]) -> str:
    """Returns `jobs` rendered as a CSV string (COLUMNS as header)."""
    buf = io.StringIO()
    export_csv(jobs, buf)
    return buf.getvalue()
