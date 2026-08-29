"""
The libSQL driver and its row shim.

libSQL is marketed as a drop-in for SQLite. For this codebase it is not: it
returns plain tuples, and `conn.row_factory` does not merely go unused — reading
it raises AttributeError. Rows are indexed by name in 146 places here, so
without a shim every one of them breaks.

These tests run against a real libSQL connection to a local file, which
exercises the same client the cloud will use without needing a Turso account or
a network. They are the only place the shim's behaviour is checked.
"""

import os
import sqlite3

import pytest

from src import jobs_db

libsql = pytest.importorskip("libsql", reason="libsql not installed")


@pytest.fixture
def raw(tmp_path):
    """A real libSQL connection, unshimmed, for establishing the baseline."""
    return libsql.connect(str(tmp_path / "raw.db"))


@pytest.fixture
def shimmed(tmp_path):
    conn = jobs_db._ShimConnection(libsql.connect(str(tmp_path / "shim.db")))
    # PRIMARY KEY on purpose: without a uniqueness constraint INSERT OR REPLACE
    # silently appends instead of replacing, and the test below would pass
    # while proving nothing.
    conn.execute("CREATE TABLE jobs (company TEXT PRIMARY KEY, status TEXT, "
                 "archived INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO jobs VALUES ('Acme', 'Applied', 0)")
    conn.execute("INSERT INTO jobs VALUES ('Beta', 'Rejected', 1)")
    conn.commit()
    return conn


# --- the baseline this shim exists to fix -----------------------------------

def test_raw_libsql_has_no_row_factory(raw):
    """
    Documents WHY the shim exists. If a future libSQL release grows row_factory,
    this test fails and the shim can be deleted — which is the outcome we want
    to notice.
    """
    with pytest.raises(AttributeError):
        raw.row_factory = sqlite3.Row


def test_raw_libsql_returns_tuples_not_named_rows(raw):
    raw.execute("CREATE TABLE t (company TEXT)")
    raw.execute("INSERT INTO t VALUES ('Acme')")
    row = raw.execute("SELECT * FROM t").fetchone()
    assert isinstance(row, tuple)
    with pytest.raises(TypeError):
        row["company"]


def test_raw_libsql_raises_plain_valueerror(raw):
    """
    Not sqlite3.OperationalError, not libsql.Error. _ensure_schema depends on a
    duplicate-column ALTER failing predictably, so _SCHEMA_EXC must cover this.
    """
    raw.execute("CREATE TABLE t (a TEXT)")
    with pytest.raises(ValueError):
        raw.execute("ALTER TABLE t ADD COLUMN a TEXT")
    assert ValueError in jobs_db._SCHEMA_EXC


# --- what the shim restores -------------------------------------------------

def test_rows_are_indexable_by_name(shimmed):
    assert shimmed.execute("SELECT * FROM jobs").fetchone()["company"] == "Acme"


def test_rows_are_still_indexable_by_position(shimmed):
    assert shimmed.execute("SELECT * FROM jobs").fetchone()[0] == "Acme"


def test_dict_conversion_works(shimmed):
    row = shimmed.execute("SELECT * FROM jobs").fetchone()
    assert dict(row) == {"company": "Acme", "status": "Applied", "archived": 0}


def test_keys_returns_column_names(shimmed):
    row = shimmed.execute("SELECT * FROM jobs").fetchone()
    assert row.keys() == ["company", "status", "archived"]


def test_fetchall_wraps_every_row(shimmed):
    rows = shimmed.execute("SELECT * FROM jobs ORDER BY company").fetchall()
    assert [r["company"] for r in rows] == ["Acme", "Beta"]


def test_cursor_is_iterable(shimmed):
    """
    libSQL cursors are not iterable at all. _relationship_index iterates one
    directly, so the shim materialises instead of delegating.
    """
    assert [r["company"] for r in shimmed.execute("SELECT * FROM jobs ORDER BY company")] \
        == ["Acme", "Beta"]


def test_aggregate_aliases_are_addressable(shimmed):
    """Used throughout — recruiter_coverage reads COUNT(*) AS n by name."""
    assert shimmed.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"] == 2


def test_fetchone_returns_none_on_empty(shimmed):
    assert shimmed.execute("SELECT * FROM jobs WHERE company = 'Nope'").fetchone() is None


def test_sqlite_specific_sql_still_works(shimmed):
    """INSERT OR REPLACE and PRAGMA are used across the codebase."""
    shimmed.execute("INSERT OR REPLACE INTO jobs VALUES ('Acme', 'Offer', 0)")
    shimmed.commit()
    cols = [r[1] for r in shimmed.execute("PRAGMA table_info(jobs)").fetchall()]
    assert cols == ["company", "status", "archived"]
    assert shimmed.execute(
        "SELECT status FROM jobs WHERE company='Acme'").fetchone()["status"] == "Offer"


# --- driver selection -------------------------------------------------------

def test_importing_jobs_db_does_not_arm_the_cloud_driver():
    """
    jobs_db calls load_dotenv() at import so every entry point agrees on which
    database it is talking to. That import runs during collection, before any
    fixture, and .env carries a real TURSO_DATABASE_URL -- so this asserts the
    conftest guard still wins and the suite is pointed at a local file.

    Without this, the failure is silent and expensive: conftest's own docstring
    records a run that wrote 138 job rows, 78 interviews and 4 recruiters into
    the production database.
    """
    assert jobs_db._use_libsql() is False
    assert not os.environ.get("TURSO_DATABASE_URL")


def test_sqlite_is_the_default(monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    assert jobs_db._use_libsql() is False


def test_libsql_is_selected_by_env(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    assert jobs_db._use_libsql() is True


def test_blank_env_var_does_not_select_libsql(monkeypatch):
    """An empty or whitespace value must not silently switch drivers."""
    monkeypatch.setenv("TURSO_DATABASE_URL", "   ")
    assert jobs_db._use_libsql() is False


def test_local_connection_is_untouched_by_the_new_driver(tmp_path, monkeypatch):
    """
    The whole point of the switch: with no env var, the SQLite path behaves
    exactly as before, returning real sqlite3.Row objects.
    """
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    jobs_db._reset_schema_cache()
    conn = jobs_db._connect(create=True)
    assert isinstance(conn, sqlite3.Connection)
    assert conn.row_factory is sqlite3.Row


def test_full_schema_builds_on_libsql(tmp_path, monkeypatch):
    """
    End to end: every CREATE TABLE, index, and both migrations run against a
    real libSQL connection. This is what proves the cloud database can be
    initialised at all.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", str(tmp_path / "cloud.db"))
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    jobs_db._reset_schema_cache()

    conn = jobs_db._connect(create=True)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"jobs", "interviews", "recruiters", "recruiter_jobs",
            "recruiter_messages", "meta"} <= tables


def test_a_merge_updates_in_place_on_libsql(tmp_path, monkeypatch):
    """
    The ApplyPass importer reports how many rows it merged from
    update_job_fields' return value, which is `cur.rowcount > 0`. libSQL is a
    different client, and a cursor that did not populate rowcount would make
    every successful merge report as zero rows updated -- the number the
    applypass-inbound skill checks the row delta against.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", str(tmp_path / "cloud.db"))
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    # TURSO_DATABASE_URL is what marks a connection as production, so setting it
    # -- even at a temp file -- arms the remote-write guard. This test writes on
    # purpose through that exact path, so it declares itself the way a real entry
    # point does.
    monkeypatch.setenv("JOBS_DB_ALLOW_REMOTE_WRITES", "1")
    jobs_db._reset_schema_cache()

    key = dict(company="Acme", date_added="2026-01-01",
               position_title="Engineer", link="https://x/1")
    jobs_db.upsert_job({**key, "job_summary": "", "location": "", "contacts": "rec@acme.com",
                        "notes": "", "outreach_date": "2026-02-02", "date_applied": "",
                        "status": "Phone Screen", "followup_log": ""})

    assert jobs_db.update_job_fields(
        key["company"], key["date_added"], {"location": "Texas"},
        position_title=key["position_title"], link=key["link"])

    rows = jobs_db.get_all_jobs(include_archived=True)
    assert len(rows) == 1, "a merge must update in place, never insert"
    assert rows[0]["location"] == "Texas"
    assert rows[0]["contacts"] == "rec@acme.com"
    assert rows[0]["status"] == "Phone Screen"

    # A miss must report False, or the importer would overcount silently.
    assert not jobs_db.update_job_fields(
        "Nobody", "2026-01-01", {"location": "Texas"},
        position_title="Engineer", link="https://x/nope")
