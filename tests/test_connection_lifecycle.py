"""
Schema setup must not run on every connection.

Against local SQLite a redundant CREATE TABLE IF NOT EXISTS is free, so the code
grew a habit of ensuring the schema on every connect. An /insights render opens
eleven connections, which meant 220 schema statements to serve 12 data reads —
invisible locally at 83ms, and roughly nine seconds against a remote database
where every statement is a round trip.

These tests pin the statement count. They exist because the regression is
undetectable by any functional test: correctness never changes, only cost.
"""

import sqlite3

import pytest

from src import jobs_db


@pytest.fixture
def counting(tmp_path, monkeypatch):
    """Points jobs_db at a fresh DB and records every statement executed."""
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    jobs_db._reset_schema_cache()

    seen: list[str] = []
    real = sqlite3.connect

    class Counting(sqlite3.Connection):
        def execute(self, sql, *a, **k):
            seen.append(" ".join(sql.split()))
            return super().execute(sql, *a, **k)

    monkeypatch.setattr(sqlite3, "connect",
                        lambda p, *a, **k: real(p, *a, factory=Counting, **k))
    return seen


def _schema_stmts(seen):
    return [s for s in seen
            if s.startswith(("CREATE TABLE", "CREATE INDEX", "ALTER TABLE",
                             "PRAGMA journal_mode", "DROP TABLE"))]


def test_schema_is_built_once_not_per_connection(counting):
    jobs_db._connect(create=True)
    after_first = len(_schema_stmts(counting))
    assert after_first > 0, "first connection must actually build the schema"

    for _ in range(10):
        jobs_db._connect()
    assert len(_schema_stmts(counting)) == after_first, (
        "schema setup ran again on a later connection"
    )


def test_busy_timeout_is_still_set_on_every_connection(counting):
    """
    Unlike the DDL, busy_timeout is per-connection state, not a property of the
    file. Caching it away would silently drop concurrency protection.
    """
    for _ in range(3):
        jobs_db._connect(create=True)
    assert sum(1 for s in counting if s.startswith("PRAGMA busy_timeout")) == 3


def test_a_full_insights_render_stays_under_a_statement_budget(counting):
    """
    The number that matters for a remote database. 232 was the old figure; this
    budget is deliberately tight so a regression fails rather than degrades.
    """
    jobs_db._connect(create=True)
    counting.clear()  # measure the steady state, not first-run schema build

    jobs_db.funnel_stats()
    jobs_db.interview_stats()
    jobs_db.job_silence_stats()
    jobs_db.get_recruiters()
    jobs_db.get_recruiter_jobs()
    jobs_db.recruiter_coverage()
    jobs_db.upcoming_interviews(include_past=True)

    assert len(counting) <= 30, (
        f"an /insights render now costs {len(counting)} statements; "
        f"each one is a network round trip against a remote database"
    )
    assert not _schema_stmts(counting), "schema work leaked into a page render"


def test_a_new_database_path_still_gets_its_schema(tmp_path, monkeypatch):
    """
    The guard is keyed by path, not a bare boolean. Two different databases in
    one process must both be built — this is what every test fixture relies on.
    """
    for name in ("one.db", "two.db"):
        monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / name))
        jobs_db.upsert_job({
            "company": name, "position_title": "Engineer", "job_summary": "",
            "location": "", "link": "http://x/1", "date_added": "2026-01-01",
            "contacts": "", "notes": "", "outreach_date": "", "date_applied": "",
            "status": "Applied", "followup_log": "",
        })
        assert len(jobs_db.get_all_jobs()) == 1
