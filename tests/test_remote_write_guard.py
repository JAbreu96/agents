"""
The guard that stands between a scratch script and the real job tracker.

This exists because the accident already happened. A verification script set
`DB_PATH` to a temp file and wrote through jobs_db, believing it was isolated.
It was not: `TURSO_DATABASE_URL` was live in `.env`, a remote connection ignores
`DB_PATH` completely, and three invented jobs plus seven invented interview rows
went into the tracker -- two of them marked as interviews that had occurred,
which moved the rates.

Nothing about that script looked dangerous, which is the point. The guard is at
the connection layer rather than in the write helpers because the same incident
also ran a hand-written `conn.execute("DELETE FROM jobs ...")`, and a guard on
the helpers would have waved it straight through.
"""

import os

import pytest

from src import jobs_db

libsql = pytest.importorskip("libsql", reason="libsql not installed")


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """
    A connection that believes it is production.

    TURSO_DATABASE_URL is the whole definition of "remote" here, so pointing it
    at a local file exercises the real guard without needing a Turso account.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", str(tmp_path / "cloud.db"))
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("JOBS_DB_ALLOW_REMOTE_WRITES", raising=False)
    jobs_db._reset_schema_cache()
    return jobs_db._connect(create=True)


def _job(**over):
    return {"company": "Acme", "date_added": "2026-01-01", "position_title": "Engineer",
            "link": "https://x/1", "job_summary": "", "location": "", "contacts": "",
            "notes": "", "outreach_date": "", "date_applied": "", "status": "Applied",
            "followup_log": "", **over}


# --- what is refused --------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "INSERT INTO jobs (company) VALUES ('X')",
    "UPDATE jobs SET status = 'Rejected'",
    "DELETE FROM jobs WHERE company = 'Acme'",
    "REPLACE INTO jobs (company) VALUES ('X')",
])
def test_every_data_changing_verb_is_refused(remote, sql):
    with pytest.raises(jobs_db.RemoteWriteBlocked):
        remote.execute(sql)


def test_raw_sql_is_refused_not_just_the_helpers(remote):
    """
    The incident ran a hand-written DELETE straight at the connection. A guard
    living in the write helpers would not have seen it.
    """
    with pytest.raises(jobs_db.RemoteWriteBlocked, match="DELETE"):
        remote.execute("DELETE FROM jobs WHERE company = ?", ("Acme",))


def test_a_write_helper_is_refused(remote):
    with pytest.raises(jobs_db.RemoteWriteBlocked):
        jobs_db.upsert_job(_job())


def test_executemany_is_refused_too(remote):
    """It reaches the driver by a different method, so it needs its own guard."""
    with pytest.raises(jobs_db.RemoteWriteBlocked):
        remote.executemany("INSERT INTO jobs (company) VALUES (?)", [("A",), ("B",)])


def test_the_message_says_how_to_verify_instead(remote):
    """A refusal that does not name the alternative just gets worked around."""
    with pytest.raises(jobs_db.RemoteWriteBlocked) as e:
        jobs_db.upsert_job(_job())
    assert "clone_remote_db.py" in str(e.value)
    assert "JOBS_DB_ALLOW_REMOTE_WRITES" in str(e.value)


# --- what is still allowed --------------------------------------------------

def test_reads_are_never_blocked(remote):
    assert remote.execute("SELECT * FROM jobs").fetchall() == []
    assert jobs_db.get_all_jobs() == []


def test_opening_a_connection_runs_its_migrations(tmp_path, monkeypatch):
    """
    One migration moves rows with INSERT INTO ... SELECT. If the guard caught
    that, no remote connection could be opened at all -- reads included.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", str(tmp_path / "fresh.db"))
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("JOBS_DB_ALLOW_REMOTE_WRITES", raising=False)
    jobs_db._reset_schema_cache()

    conn = jobs_db._connect(create=True)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"jobs", "interviews", "recruiters", "meta"} <= tables


def test_a_declared_entry_point_may_write(remote, monkeypatch):
    monkeypatch.setenv("JOBS_DB_ALLOW_REMOTE_WRITES", "1")
    jobs_db.upsert_job(_job())
    assert [j["company"] for j in jobs_db.get_all_jobs()] == ["Acme"]


def test_allow_remote_writes_is_what_entry_points_call(remote, monkeypatch):
    monkeypatch.delenv("JOBS_DB_ALLOW_REMOTE_WRITES", raising=False)
    assert jobs_db.remote_writes_allowed() is False
    jobs_db.allow_remote_writes()
    assert jobs_db.remote_writes_allowed() is True
    jobs_db.upsert_job(_job())


def test_a_local_database_is_never_guarded(tmp_path, monkeypatch):
    """
    The guard is about the shared remote tracker, not about writing. Local
    files -- fixtures, snapshots from clone_remote_db.py -- stay freely
    writable, which is the whole point of taking a copy.
    """
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("JOBS_DB_ALLOW_REMOTE_WRITES", raising=False)
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "local.db"))
    jobs_db._reset_schema_cache()

    jobs_db.upsert_job(_job())
    assert [j["company"] for j in jobs_db.get_all_jobs()] == ["Acme"]


# --- the escape hatch that actually works -----------------------------------

def test_naming_a_file_beats_the_turso_url(tmp_path, monkeypatch):
    """
    JOBS_DB_PATH has to win, or the documented snapshot workflow is a lie.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "snapshot.db"))
    assert jobs_db._use_libsql() is False


def test_unsetting_the_turso_url_is_not_enough_on_its_own(tmp_path, monkeypatch):
    """
    The trap that caused the incident, pinned so nobody documents `env -u` as
    the fix again: load_dotenv() runs at import and puts the variable back, so
    a caller who only unsets it is still pointed at production.
    """
    monkeypatch.delenv("JOBS_DB_PATH", raising=False)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    assert jobs_db._use_libsql() is False       # unset, for this instant

    import importlib
    monkeypatch.setattr("dotenv.load_dotenv",
                        lambda *a, **k: os.environ.setdefault(
                            "TURSO_DATABASE_URL", "libsql://example.turso.io"))
    importlib.reload(jobs_db)
    assert jobs_db._use_libsql() is True, "dotenv restored it -- this is the trap"

    # and naming a file is what survives that
    monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "snapshot.db"))
    assert jobs_db._use_libsql() is False


# --- the entry points that are allowed to write -----------------------------

def test_importing_an_entry_point_does_not_grant_permission(monkeypatch):
    """
    Permission is declared in __main__, never at import, so `from src import
    jobs_gui` in a scratch script inherits nothing.
    """
    monkeypatch.delenv("JOBS_DB_ALLOW_REMOTE_WRITES", raising=False)
    import importlib

    from src import jobs_gui
    importlib.reload(jobs_gui)
    assert jobs_db.remote_writes_allowed() is False


@pytest.mark.parametrize("path", [
    "src/jobs_gui.py",
    "mcp_servers/job_tracker/server.py",
    "scripts/backfill_interviews.py",
    "scripts/backfill_job_fields.py",
    "scripts/backfill_recruiters.py",
    "scripts/parse_applied_jobs.py",
    "scripts/sync_jobs_to_sqlite.py",
])
def test_each_writing_entry_point_declares_itself(path):
    """
    If a new write path is added without declaring itself it fails at runtime,
    in front of a user. This turns that into a failing test instead.
    """
    assert "allow_remote_writes()" in open(path).read(), (
        f"{path} writes to the tracker but never calls allow_remote_writes()"
    )
