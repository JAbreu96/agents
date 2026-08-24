"""
The GUI's read path.

Two things here are shaped by constraints rather than taste:

`/api/jobs` deliberately omits job_summary -- it was two thirds of the payload
and appears nowhere in the table -- while keeping `notes`, which the search box
matches against. A test asserts both halves, because dropping the wrong column
breaks search silently: the filter just stops matching.

The duplicate-company 409 is detected with a SELECT rather than by catching the
UPDATE's exception, because conftest strips TURSO_* for the whole session and so
no test can ever observe what libSQL raises. A SELECT behaves the same on both
drivers, which is what makes the case testable here at all.
"""

import sqlite3

import pytest

from src import jobs_db, jobs_gui


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    jobs_db._reset_schema_cache()
    jobs_db.upsert_job({
        "company": "Acme", "position_title": "Engineer", "link": "",
        "date_added": "2026-01-01", "job_summary": "A long job description.",
        "notes": "applypass auto-applied", "status": "Tracking",
    })
    jobs_db.upsert_job({
        "company": "Globex", "position_title": "Engineer", "link": "",
        "date_added": "2026-01-01", "job_summary": "Another description.",
        "notes": "", "status": "Tracking",
    })
    jobs_gui.app.config["TESTING"] = True
    with jobs_gui.app.test_client() as c:
        yield c


def test_list_columns_drops_job_summary():
    assert "job_summary" not in jobs_db.LIST_COLUMNS


def test_list_columns_keeps_notes_for_the_search_box():
    assert "notes" in jobs_db.LIST_COLUMNS


def test_list_columns_tracks_columns():
    """Derived, not hand-written: a new column must reach the GUI on its own."""
    assert set(jobs_db.LIST_COLUMNS) == set(jobs_db.COLUMNS) - {"job_summary"}


def test_write_exc_covers_both_drivers():
    assert sqlite3.IntegrityError in jobs_db._WRITE_EXC
    assert ValueError in jobs_db._WRITE_EXC


def test_jobs_list_omits_job_summary(client):
    rows = client.get("/api/jobs").get_json()
    assert rows
    assert all("job_summary" not in r for r in rows)


def test_jobs_list_still_carries_notes(client):
    rows = client.get("/api/jobs").get_json()
    assert any(r["notes"] == "applypass auto-applied" for r in rows)


def test_detail_returns_the_summary_the_list_withheld(client):
    data = client.get("/api/jobs/detail", query_string={
        "company": "Acme", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "",
    }).get_json()
    assert data["job_summary"] == "A long job description."
    assert data["interviews"] == []


def test_detail_skips_the_summary_when_the_client_has_it(client):
    data = client.get("/api/jobs/detail", query_string={
        "company": "Acme", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "", "summary": "0",
    }).get_json()
    assert "job_summary" not in data
    assert "interviews" in data


def test_detail_returns_rounds_for_the_job(client):
    jobs_db.add_interview(company="Acme", date_added="2026-01-01",
                          position_title="Engineer", link="",
                          interview_type="technical", occurred_date="2026-02-01")
    data = client.get("/api/jobs/detail", query_string={
        "company": "Acme", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "", "summary": "0",
    }).get_json()
    assert [r["interview_type"] for r in data["interviews"]] == ["technical"]


def test_detail_does_not_leak_another_jobs_rounds(client):
    jobs_db.add_interview(company="Acme", date_added="2026-01-01",
                          position_title="Engineer", link="",
                          interview_type="technical", occurred_date="2026-02-01")
    data = client.get("/api/jobs/detail", query_string={
        "company": "Globex", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "", "summary": "0",
    }).get_json()
    assert data["interviews"] == []


def test_renaming_onto_an_existing_key_is_rejected(client):
    res = client.post("/api/jobs/update", json={
        "company": "Acme", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "",
        "field": "company", "value": "Globex",
    })
    assert res.status_code == 409
    assert "already exists" in res.get_json()["error"]


def test_the_rejected_rename_left_the_row_alone(client):
    client.post("/api/jobs/update", json={
        "company": "Acme", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "",
        "field": "company", "value": "Globex",
    })
    companies = [r["company"] for r in client.get("/api/jobs").get_json()]
    assert sorted(companies) == ["Acme", "Globex"]


def test_a_rename_to_a_free_key_still_works(client):
    res = client.post("/api/jobs/update", json={
        "company": "Acme", "date_added": "2026-01-01",
        "position_title": "Engineer", "link": "",
        "field": "company", "value": "Initech",
    })
    assert res.status_code == 200
    companies = [r["company"] for r in client.get("/api/jobs").get_json()]
    assert sorted(companies) == ["Globex", "Initech"]
