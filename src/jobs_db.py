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


_META_DDL = """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
"""


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
    _ensure_interviews_schema(conn)
    conn.execute(_META_DDL)


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


def get_meta(key: str, default: str = "") -> str:
    """
    Reads a scalar from the `meta` key/value table.

    Returns `default` when the DB does not exist yet or the key was never set,
    so first-run callers get a usable value without special-casing.
    """
    conn = _connect()
    if not conn:
        return default
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_meta(key: str, value: str) -> None:
    """Writes a scalar to the `meta` key/value table, creating the DB if needed."""
    conn = _connect(create=True)
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()


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


def update_summary(company: str, date_added: str, job_summary: str,
                   position_title: Optional[str] = None,
                   link: Optional[str] = None) -> bool:
    return update_field(company, date_added, "job_summary", job_summary,
                        position_title, link)


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


# ---------------------------------------------------------------------------
# Interviews
# ---------------------------------------------------------------------------

INTERVIEW_TYPES = [
    "recruiter_screen",
    "phone_screen",
    "technical",
    "behavioral",
    "system_design",
    "take_home",
    "pair_programming",
    "final_round",
    "other",
]

INTERVIEW_COLUMNS = [
    "id", "company", "date_added", "position_title", "link",
    "interview_type", "type_label", "loop_id", "occurred_date",
    "self_rating", "notes",
]

# Terminal job statuses, matched case-insensitively against jobs.status.
TERMINAL_FAIL_STATUSES = {"rejected"}
TERMINAL_WIN_STATUSES = {"offer", "accepted"}

# Silence this long after a round, with nothing following it and no terminal
# status, is a decision that was made and never communicated. Three weeks can
# still be a slow loop; a month is not.
GHOSTED_AFTER_DAYS = 30

_INTERVIEWS_DDL = """
        CREATE TABLE IF NOT EXISTS interviews (
            id             INTEGER PRIMARY KEY,
            company        TEXT NOT NULL,
            date_added     TEXT NOT NULL DEFAULT '',
            position_title TEXT NOT NULL DEFAULT '',
            link           TEXT NOT NULL DEFAULT '',
            interview_type TEXT NOT NULL,
            type_label     TEXT,
            loop_id        TEXT,
            occurred_date  TEXT NOT NULL,
            self_rating    INTEGER,
            notes          TEXT
        )
"""


def _ensure_interviews_schema(conn: sqlite3.Connection) -> None:
    """
    The job key is copied in as plain columns rather than referenced.

    `jobs` is rebuilt wholesale by _migrate_key(), and sync_jobs_to_sqlite.py
    writes with INSERT OR REPLACE, which SQLite implements as delete-then-insert.
    Either one reassigns every rowid, so a rowid foreign key would dangle and
    ON DELETE CASCADE would take the interview history down with it — silently,
    on a routine sync. Interview rounds are the one thing in this DB that cannot
    be re-fetched from anywhere, so they survive by construction.
    """
    conn.execute(_INTERVIEWS_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_interviews_job "
        "ON interviews (company, date_added, position_title, link)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_interviews_type ON interviews (interview_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_interviews_loop ON interviews (loop_id)")


def add_interview(company: str, date_added: str, position_title: str, link: str,
                  interview_type: str, occurred_date: str, type_label: str = "",
                  loop_id: str = "", self_rating: Optional[int] = None,
                  notes: str = "") -> int:
    """
    Records one interview round that HAPPENED. Returns the new row id.

    `occurred_date` is deliberately not "scheduled date" — advancement is derived
    from which rounds took place, so a cancelled or rescheduled invite that never
    happened must never reach this table or it inflates the denominator.
    """
    if interview_type not in INTERVIEW_TYPES:
        raise ValueError(
            f"Unknown interview_type '{interview_type}'. One of: {', '.join(INTERVIEW_TYPES)}"
        )
    if not occurred_date or not occurred_date.strip():
        raise ValueError("occurred_date is required — only rounds that happened are logged.")
    if self_rating is not None and not (1 <= int(self_rating) <= 5):
        raise ValueError("self_rating must be between 1 and 5, or None.")

    conn = _connect(create=True)
    try:
        cur = conn.execute(
            "INSERT INTO interviews (company, date_added, position_title, link, "
            "interview_type, type_label, loop_id, occurred_date, self_rating, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company, date_added, position_title, link, interview_type,
             type_label or None, loop_id or None, occurred_date.strip(),
             int(self_rating) if self_rating is not None else None, notes or None),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_interview(interview_id: int) -> int:
    """Deletes one interview round by id. Returns rows removed."""
    conn = _connect()
    if not conn:
        return 0
    try:
        cur = conn.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_interviews(company: str = "", date_added: str = "", position_title: str = "",
                   link: str = "") -> list[dict]:
    """
    Returns interview rounds, oldest first. With no arguments, returns all of them;
    pass the full job key to scope to one posting.
    """
    conn = _connect()
    if not conn:
        return []
    try:
        query = "SELECT * FROM interviews"
        params: list = []
        if company:
            clauses = ["LOWER(company) = LOWER(?)"]
            params.append(company)
            for col, val in (("date_added", date_added), ("position_title", position_title),
                             ("link", link)):
                if val:
                    clauses.append(f"{col} = ?")
                    params.append(val)
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY occurred_date ASC, id ASC"
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def _unit_key(row: dict) -> tuple:
    """A loop is one unit; a standalone round is a unit of one."""
    if row.get("loop_id"):
        return ("loop", row["loop_id"])
    return ("round", row["id"])


def classify_interviews() -> list[dict]:
    """
    Labels every interview round 'advanced', 'failed', or 'in_flight'.

    No verdict is ever stored, because for most rounds it is not observable — a
    rejection email after a four-round loop does not say which round lost it.
    What IS observable is whether the process continued, so that is what gets
    derived here:

      * a later unit exists for this job  -> advanced
      * last unit, job status Rejected    -> failed
      * last unit, job status Offer/Accepted -> advanced
      * last unit, job active, silent 30d+ -> ghosted (counts against the rate)
      * last unit, job still active       -> in_flight (excluded from the rate)

    Loops are atomic: rounds sharing a loop_id resolve together and every round
    in the loop inherits the loop's outcome. Ordering rounds inside a same-day
    onsite by date would otherwise mark the earlier ones 'advanced' for merely
    having siblings and pin the whole loop's failure on whichever one sorted last.
    """
    rows = get_interviews()
    if not rows:
        return []

    status_by_key = {
        (j["company"], j["date_added"], j["position_title"], j["link"]):
            (j.get("status") or "").strip().lower()
        for j in get_all_jobs(include_archived=True)
    }

    by_job: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["company"], r["date_added"], r["position_title"], r["link"])
        by_job.setdefault(key, []).append(r)

    out: list[dict] = []
    for key, job_rows in by_job.items():
        units: dict[tuple, list[dict]] = {}
        for r in job_rows:
            units.setdefault(_unit_key(r), []).append(r)
        # get_interviews() already sorted by occurred_date, so ordering units by
        # their earliest round preserves that order across loops.
        ordered = sorted(units.values(), key=lambda u: (u[0]["occurred_date"], u[0]["id"]))

        status = status_by_key.get(key)
        for i, unit in enumerate(ordered):
            if i < len(ordered) - 1:
                outcome = "advanced"
            elif status is None:
                outcome = "in_flight"   # job row gone (link changed?) — never guess
            elif status in TERMINAL_FAIL_STATUSES:
                outcome = "failed"
            elif status in TERMINAL_WIN_STATUSES:
                outcome = "advanced"
            else:
                # Nothing followed this round and the job never closed. Past the
                # silence threshold that is a ghosting, not an open process.
                last_seen = max(_parse_date(r["occurred_date"]) or date.min for r in unit)
                idle = (date.today() - last_seen).days if last_seen != date.min else 0
                outcome = "ghosted" if idle >= GHOSTED_AFTER_DAYS else "in_flight"
            for r in unit:
                out.append({**r, "outcome": outcome, "job_orphaned": status is None})
    return out


def interview_stats() -> dict:
    """
    Round outcomes per interview type. The single source of this computation —
    the GUI view and the MCP tool both call it so the two can never disagree.

    Rate = advanced / (advanced + failed). In-flight rounds are excluded from the
    denominator entirely: every job's most recent round has no successor yet, so
    counting those as failures would drag every rate down and hit whichever types
    you interviewed for most recently the hardest.
    """
    classified = classify_interviews()

    def blank() -> dict:
        return {"advanced": 0, "failed": 0, "ghosted": 0, "in_flight": 0}

    by_type: dict[str, dict] = {}
    for r in classified:
        entry = by_type.setdefault(r["interview_type"], {
            "interview_type": r["interview_type"],
            "total": blank(), "standalone": blank(), "loop": blank(),
        })
        bucket = "loop" if r.get("loop_id") else "standalone"
        entry["total"][r["outcome"]] += 1
        entry[bucket][r["outcome"]] += 1

    def rate(c: dict) -> Optional[float]:
        # Ghosted rounds are in the denominator: they demonstrably did not advance
        # you. Leaving them out would compute a rate only over companies polite
        # enough to send a rejection, which is not the population you interview with.
        decided = c["advanced"] + c["failed"] + c["ghosted"]
        return round(100.0 * c["advanced"] / decided, 1) if decided else None

    rows = []
    for t in INTERVIEW_TYPES:
        if t not in by_type:
            continue
        e = by_type[t]
        for scope in ("total", "standalone", "loop"):
            e[scope]["rate"] = rate(e[scope])
        rows.append(e)

    return {
        "by_type": rows,
        "totals": {
            "rounds": len(classified),
            "advanced": sum(1 for r in classified if r["outcome"] == "advanced"),
            "failed": sum(1 for r in classified if r["outcome"] == "failed"),
            "ghosted": sum(1 for r in classified if r["outcome"] == "ghosted"),
            "in_flight": sum(1 for r in classified if r["outcome"] == "in_flight"),
            "orphaned": sum(1 for r in classified if r["job_orphaned"]),
        },
    }


# ---------------------------------------------------------------------------
# Application funnel
# ---------------------------------------------------------------------------

# Statuses that mean "currently sitting at an interview stage". This reads
# CURRENT state, not history: a job that reached a phone screen and was then
# rejected reads only as 'Rejected', so this stage is a floor, not a total.
SCREEN_STATUSES = {"phone screen", "technical", "system design", "behavioral", "final round"}

# A screen filters for plausibility; an evaluation tests whether you can do the
# job. The funnel's last stage counts only the latter, so a 15-minute recruiter
# call cannot graduate a job to "interviewed" — screens stop at the screen stage.
SCREENING_TYPES = {"recruiter_screen", "phone_screen"}
EVALUATION_TYPES = {
    "technical", "behavioral", "system_design",
    "take_home", "pair_programming", "final_round", "other",
}

# Source detection is a string match on notes, not a real column — the ApplyPass
# importer stamps its provenance there. Correct today, and quietly wrong if that
# wording ever changes.
_AUTO_MARKERS = ("applypass", "auto-appl")

# Below this many rows a conversion percentage is noise dressed as a finding, so
# the stage shows a bare count instead.
RATE_MIN_DENOMINATOR = 30


def _is_auto(job: dict) -> bool:
    notes = (job.get("notes") or "").lower()
    return any(m in notes for m in _AUTO_MARKERS)


def funnel_stats() -> dict:
    """
    Two-path application funnel, precomputed for each source filter.

    Applying and outreaching turned out to be alternative routes rather than
    sequential stages — of the tracked jobs, hundreds applied without ever
    outreaching, dozens outreached without ever applying, and none did the two on
    different days. So a single linear funnel would render most rows as attrition
    at a stage they never intended to enter. These are two parallel paths that
    converge only at 'interviewed'.

    Rejections are reported alongside rather than inside a path: a rejection is an
    exit, not a step toward an interview.
    """
    # Archived rows are INCLUDED deliberately. Archiving retires jobs older than
    # 60 days from the working table, but a funnel is a historical record and a
    # finished outcome is its most useful input — excluding them drops the
    # majority of outreach history and makes that path look inert.
    jobs = get_all_jobs(include_archived=True)

    rounds = get_interviews()
    def _keys(types):
        return {
            (r["company"], r["date_added"], r["position_title"], r["link"])
            for r in rounds if r["interview_type"] in types
        }
    evaluated_keys = _keys(EVALUATION_TYPES)
    screened_keys = _keys(SCREENING_TYPES)

    def build(rows: list[dict]) -> dict:
        applied = [j for j in rows if (j.get("date_applied") or "").strip()]
        outreached = [j for j in rows if (j.get("outreach_date") or "").strip()]

        def _key(j):
            return (j["company"], j["date_added"], j["position_title"], j["link"])

        def interviewed(subset):
            return sum(1 for j in subset if _key(j) in evaluated_keys)

        def at_screen(subset):
            # Either sitting at a screening status now, or a screening round was
            # logged — a job that was screened and then rejected still reached
            # this stage, and status alone would forget that.
            return sum(
                1 for j in subset
                if (j.get("status") or "").strip().lower() in SCREEN_STATUSES
                or _key(j) in screened_keys
            )

        # An interview can belong to neither path: Base-Power-style rows that came
        # through a contact have no application date and no outreach date. Those
        # would silently vanish from a two-path funnel and make this card
        # contradict the interview table below it, so they are counted out loud.
        interviewed_jobs = [j for j in rows if _key(j) in evaluated_keys]
        unattributed = [
            j for j in interviewed_jobs
            if not (j.get("date_applied") or "").strip() and not (j.get("outreach_date") or "").strip()
        ]

        return {
            "interviewed_total": len(interviewed_jobs),
            "interviewed_unattributed": len(unattributed),
            "application_path": [
                {"stage": "tracked", "count": len(rows)},
                {"stage": "applied", "count": len(applied)},
                {"stage": "at screen", "count": at_screen(applied)},
                {"stage": "interviewed", "count": interviewed(applied)},
            ],
            "outreach_path": [
                {"stage": "tracked", "count": len(rows)},
                {"stage": "outreached", "count": len(outreached)},
                {"stage": "replied", "count": None},   # no reply field exists — never render as 0
                {"stage": "interviewed", "count": interviewed(outreached)},
            ],
            "rejected": sum(1 for j in rows if (j.get("status") or "").strip().lower() == "rejected"),
            "both_paths": sum(
                1 for j in rows
                if (j.get("date_applied") or "").strip() and (j.get("outreach_date") or "").strip()
            ),
        }

    sources = {
        "all": jobs,
        "hand": [j for j in jobs if not _is_auto(j)],
        "auto": [j for j in jobs if _is_auto(j)],
    }
    data = {name: build(rows) for name, rows in sources.items()}

    # Conversion is relative to the stage above it, and only shown once the
    # denominator is big enough to mean anything.
    for payload in data.values():
        for path in ("application_path", "outreach_path"):
            prev = None
            for stage in payload[path]:
                if stage["count"] is None or prev is None or prev < RATE_MIN_DENOMINATOR:
                    stage["rate"] = None
                else:
                    stage["rate"] = round(100.0 * stage["count"] / prev, 1)
                # An unmeasured stage poisons everything downstream: a conversion
                # computed ACROSS the gap would silently claim to measure what the
                # gap says we cannot. Outreach with no reply tracking must read as
                # unknown, never as 0%.
                prev = None if stage["count"] is None else stage["count"]

    return {"sources": data, "rate_min_denominator": RATE_MIN_DENOMINATOR}
