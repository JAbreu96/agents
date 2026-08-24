"""
shared_connection(): one connection and one jobs snapshot per block.

Rendering /insights called seven helpers that opened eleven connections between
them -- ~2.1s of the 4.6s the page took, because a remote connect costs ~84ms and
every helper opens its own. Importing was worse: upsert_job connects per row, so
a 101-row import spent 8.5s connecting.

The subtle part is close(). Every helper closes its connection in a `finally`, so
sharing one naively means the first helper to finish closes it under the others.
libSQL answers a use-after-close with a Rust PanicException rather than a Python
exception, which no caller can catch and no test can assert against -- so the
no-op close is load-bearing, and `test_close_inside_a_scope_is_a_no_op` is the
guard that keeps it that way.
"""

import sqlite3

import pytest

from src import jobs_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    jobs_db._reset_schema_cache()
    jobs_db.upsert_job({
        "company": "Acme", "position_title": "Engineer", "link": "",
        "date_added": "2026-01-01", "status": "Applied", "job_summary": "x" * 50,
    })
    jobs_db.upsert_job({
        "company": "Globex", "position_title": "Engineer", "link": "",
        "date_added": "2026-01-02", "status": "Tracking",
    })
    return jobs_db


def _count_connects(monkeypatch):
    """
    Returns a list that grows by one for every real connection opened.

    Spies on _open_connection, not _connect: inside a scope _connect hands back a
    wrapper over a connection that already exists, and counting those would count
    sharing as if it were connecting.
    """
    opened = []
    real = jobs_db._open_connection

    def spy(*args, **kwargs):
        conn = real(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(jobs_db, "_open_connection", spy)
    return opened


# --- connection reuse -------------------------------------------------------

def test_a_scope_opens_one_connection_for_many_helpers(db, monkeypatch):
    opened = _count_connects(monkeypatch)
    with jobs_db.shared_connection():
        jobs_db.funnel_stats()
        jobs_db.interview_stats()
        jobs_db.job_silence_stats()
        jobs_db.get_recruiters()
    assert len(opened) == 1


def test_without_a_scope_each_helper_opens_its_own(db, monkeypatch):
    """The old behaviour has to survive untouched, for the MCP server and scripts."""
    opened = _count_connects(monkeypatch)
    jobs_db.funnel_stats()
    jobs_db.get_recruiters()
    assert len(opened) > 1


def test_nested_scopes_share_the_outer_connection(db, monkeypatch):
    opened = _count_connects(monkeypatch)
    with jobs_db.shared_connection():
        with jobs_db.shared_connection():
            jobs_db.funnel_stats()
    assert len(opened) == 1


def test_an_unused_scope_never_connects(db, monkeypatch):
    """
    What makes it safe for the web app to wrap every request. If entering a scope
    connected eagerly, the routes that only render a template would each pay for
    a connection they never use.
    """
    opened = _count_connects(monkeypatch)
    with jobs_db.shared_connection():
        pass
    assert opened == []


def test_close_inside_a_scope_is_a_no_op(db):
    """
    The guard against use-after-close. If close() ever stops being suppressed,
    the second helper in any scope crashes -- and on libSQL it crashes the
    interpreter rather than raising.
    """
    with jobs_db.shared_connection():
        conn = jobs_db._connect()
        conn.close()
        assert conn.execute("select count(*) from jobs").fetchone()[0] == 2


def test_the_real_connection_closes_when_the_scope_exits(db, monkeypatch):
    opened = _count_connects(monkeypatch)
    with jobs_db.shared_connection():
        jobs_db.funnel_stats()
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("select 1")


def test_scope_state_does_not_leak_after_the_block(db):
    with jobs_db.shared_connection():
        pass
    assert jobs_db._SCOPE.get() is None


# --- the jobs snapshot ------------------------------------------------------

def test_jobs_are_fetched_once_per_scope(db):
    """
    Proven by poisoning the snapshot: if a later call re-queried the database it
    would return the real rows, not the sentinel planted here.
    """
    with jobs_db.shared_connection():
        jobs_db._stats_jobs()
        scope = jobs_db._SCOPE.get()
        scope.jobs = [{"company": "SENTINEL", "archived": 0}]
        again = jobs_db._stats_jobs()
    assert [r["company"] for r in again] == ["SENTINEL"]


def test_each_scope_starts_with_a_fresh_snapshot(db):
    with jobs_db.shared_connection():
        jobs_db._stats_jobs()
        jobs_db._SCOPE.get().jobs = [{"company": "SENTINEL", "archived": 0}]
    with jobs_db.shared_connection():
        assert "SENTINEL" not in [r["company"] for r in jobs_db._stats_jobs()]


def test_stats_jobs_omits_job_summary(db):
    """Two thirds of the table by bytes, and no stats function reads it."""
    rows = jobs_db._stats_jobs()
    assert rows and all("job_summary" not in r for r in rows)


def test_stats_jobs_respects_include_archived(db):
    """One fetch serves both callers; the archived split happens in Python."""
    jobs_db.archive_jobs(days=0)
    assert jobs_db._stats_jobs() == []
    assert len(jobs_db._stats_jobs(include_archived=True)) == 2


def test_the_archived_split_is_correct_inside_a_scope(db):
    jobs_db.archive_jobs(days=0)
    with jobs_db.shared_connection():
        every = jobs_db._stats_jobs(include_archived=True)
        active = jobs_db._stats_jobs()
    assert len(every) == 2 and active == []


def test_a_write_invalidates_the_snapshot(db):
    """A read after a write in the same scope must not see the pre-write rows."""
    with jobs_db.shared_connection():
        before = len(jobs_db._stats_jobs(include_archived=True))
        jobs_db.upsert_job({
            "company": "Initech", "position_title": "Engineer", "link": "",
            "date_added": "2026-01-03", "status": "Tracking",
        })
        after = len(jobs_db._stats_jobs(include_archived=True))
    assert after == before + 1


def test_reads_alone_keep_the_snapshot(db):
    with jobs_db.shared_connection():
        jobs_db._stats_jobs()
        scope = jobs_db._SCOPE.get()
        assert scope.jobs is not None
        jobs_db.get_recruiters()          # a read must not clear it
        assert scope.jobs is not None


def test_stats_are_identical_with_and_without_a_scope(db):
    """The optimisation must not change a single derived number."""
    plain = (jobs_db.funnel_stats(), jobs_db.interview_stats(), jobs_db.job_silence_stats())
    with jobs_db.shared_connection():
        scoped = (jobs_db.funnel_stats(), jobs_db.interview_stats(), jobs_db.job_silence_stats())
    assert plain == scoped
