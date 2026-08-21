"""
Interview-round classification.

The cases that matter here are the ones the real DB cannot exercise yet: onsite
loops, in-flight processes, offers, and rounds orphaned by a changed job link.
"""

import importlib

import pytest

from src import jobs_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    importlib.reload  # keep module identity; DB_PATH is read per-call
    return jobs_db


def _job(db, company, status, link="http://x/1", title="Engineer", added="2026-01-01"):
    db.upsert_job({
        "company": company, "position_title": title, "job_summary": "", "location": "",
        "link": link, "date_added": added, "contacts": "", "notes": "",
        "outreach_date": "", "date_applied": "", "status": status, "followup_log": "",
    })
    return dict(company=company, date_added=added, position_title=title, link=link)


def _round(db, key, itype, when, loop_id=""):
    return db.add_interview(interview_type=itype, occurred_date=when, loop_id=loop_id, **key)


def _recent(days_ago=1):
    """
    Dates in these tests must be relative, not absolute. A hard-coded date silently
    ages past the ghosting threshold and turns an 'in flight' case into a 'ghosted'
    one — a test that passes today and fails next month for no code reason.
    """
    from datetime import date, timedelta
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _outcomes(db):
    return {(r["interview_type"], r["occurred_date"]): r["outcome"]
            for r in db.classify_interviews()}


def test_earlier_round_advanced_last_round_failed_on_rejection(db):
    key = _job(db, "Acme", "Rejected")
    _round(db, key, "phone_screen", "2026-02-01")
    _round(db, key, "technical", "2026-02-08")
    out = _outcomes(db)
    assert out[("phone_screen", "2026-02-01")] == "advanced"
    assert out[("technical", "2026-02-08")] == "failed"


def test_last_round_of_live_process_is_in_flight_not_failed(db):
    key = _job(db, "Live Co", "Applied")
    when = _recent()
    _round(db, key, "system_design", when)
    assert _outcomes(db)[("system_design", when)] == "in_flight"

    stats = db.interview_stats()
    sd = next(r for r in stats["by_type"] if r["interview_type"] == "system_design")
    assert sd["total"]["in_flight"] == 1
    # Excluded from the denominator entirely, not counted as a loss.
    assert sd["total"]["rate"] is None


@pytest.mark.parametrize("status", ["Offer", "Accepted", "accepted"])
def test_terminal_win_counts_the_final_round_as_advanced(db, status):
    key = _job(db, "Winner Inc", status)
    _round(db, key, "final_round", "2026-04-01")
    assert _outcomes(db)[("final_round", "2026-04-01")] == "advanced"


def test_same_day_loop_resolves_as_one_unit(db):
    """
    Four rounds on one Thursday. Ordering them by date would mark three
    'advanced' purely for having siblings and pin the loss on whichever sorted
    last. All four share the loop's outcome instead.
    """
    key = _job(db, "Loop Co", "Rejected")
    for itype in ("technical", "system_design", "behavioral", "technical"):
        _round(db, key, itype, "2026-05-05", loop_id="onsite-1")
    outcomes = [r["outcome"] for r in db.classify_interviews()]
    assert outcomes == ["failed"] * 4


def test_round_before_a_loop_advanced_and_the_loop_fails(db):
    key = _job(db, "Deep Co", "Rejected")
    _round(db, key, "phone_screen", "2026-06-01")
    _round(db, key, "technical", "2026-06-10", loop_id="onsite-2")
    _round(db, key, "behavioral", "2026-06-10", loop_id="onsite-2")
    out = _outcomes(db)
    assert out[("phone_screen", "2026-06-01")] == "advanced"
    assert out[("technical", "2026-06-10")] == "failed"
    assert out[("behavioral", "2026-06-10")] == "failed"


def test_rate_excludes_in_flight_from_the_denominator(db):
    won = _job(db, "A Co", "Offer", link="http://a/1")
    lost = _job(db, "B Co", "Rejected", link="http://b/1")
    live = _job(db, "C Co", "Applied", link="http://c/1")
    for key in (won, lost, live):
        _round(db, key, "system_design", _recent())

    sd = next(r for r in db.interview_stats()["by_type"]
              if r["interview_type"] == "system_design")
    assert (sd["total"]["advanced"], sd["total"]["failed"], sd["total"]["in_flight"]) == (1, 1, 1)
    assert sd["total"]["rate"] == 50.0


def test_loop_and_standalone_are_reported_separately(db):
    solo = _job(db, "Solo Co", "Offer", link="http://s/1")
    _round(db, solo, "behavioral", "2026-08-01")
    looped = _job(db, "Loopy Co", "Rejected", link="http://l/1")
    _round(db, looped, "behavioral", "2026-08-02", loop_id="onsite-3")

    b = next(r for r in db.interview_stats()["by_type"]
             if r["interview_type"] == "behavioral")
    assert b["standalone"]["rate"] == 100.0
    assert b["loop"]["rate"] == 0.0
    assert b["total"]["rate"] == 50.0


def test_interview_survives_deletion_of_its_job_row(db):
    """
    No foreign key, no cascade — deliberately. sync_jobs_to_sqlite.py writes with
    INSERT OR REPLACE (a delete then an insert), so a cascade would wipe interview
    history on a routine sync.
    """
    key = _job(db, "Gone Co", "Rejected")
    _round(db, key, "technical", "2026-09-01")
    db.delete_job_by_key(key["company"], key["date_added"],
                         position_title=key["position_title"], link=key["link"])

    rows = db.classify_interviews()
    assert len(rows) == 1
    assert rows[0]["job_orphaned"] is True
    # Never guessed at: an orphan is in-flight, not a failure.
    assert rows[0]["outcome"] == "in_flight"
    assert db.interview_stats()["totals"]["orphaned"] == 1


def test_unknown_type_and_missing_date_are_rejected(db):
    key = _job(db, "Strict Co", "Applied")
    with pytest.raises(ValueError):
        _round(db, key, "coffee_chat", "2026-10-01")
    with pytest.raises(ValueError):
        _round(db, key, "technical", "")
    with pytest.raises(ValueError):
        db.add_interview(interview_type="technical", occurred_date="2026-10-01",
                         self_rating=9, **key)


def test_sheet_sync_does_not_destroy_interview_history(db):
    """
    Reproduces what sync_jobs_to_sqlite.py does to every job row on every run.

    INSERT OR REPLACE is a delete followed by an insert, so each sync reassigns
    rowids. Had interviews been keyed on jobs.rowid with ON DELETE CASCADE, one
    routine sync would silently empty this table and still print "Sync complete".
    """
    key = _job(db, "Sync Co", "Rejected")
    _round(db, key, "system_design", "2026-11-01")

    conn = db._connect()
    try:
        db._ensure_schema(conn)  # what the sync script calls on startup
        conn.execute(
            "INSERT OR REPLACE INTO jobs (company, date_added, position_title, link, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (key["company"], key["date_added"], key["position_title"], key["link"], "Rejected"),
        )
        conn.commit()
    finally:
        conn.close()

    rows = db.classify_interviews()
    assert len(rows) == 1, "sync wiped the interview history"
    assert rows[0]["job_orphaned"] is False, "interview lost track of its job after sync"
    assert rows[0]["outcome"] == "failed"


def _age_round(db, key, itype, days_ago):
    from datetime import date, timedelta
    when = (date.today() - timedelta(days=days_ago)).isoformat()
    return db.add_interview(interview_type=itype, occurred_date=when, **key)


def test_a_silent_round_becomes_ghosted_past_the_threshold(db):
    """
    A round with nothing after it, on a job that never closed, is only 'in flight'
    for so long. Past the silence threshold it is a decision that was made and
    never communicated.
    """
    key = _job(db, "Silent Co", "Applied")
    _age_round(db, key, "technical", jobs_db.GHOSTED_AFTER_DAYS + 1)
    assert db.classify_interviews()[0]["outcome"] == "ghosted"


def test_a_recent_silent_round_is_still_in_flight(db):
    key = _job(db, "Recent Co", "Applied")
    _age_round(db, key, "technical", jobs_db.GHOSTED_AFTER_DAYS - 1)
    assert db.classify_interviews()[0]["outcome"] == "in_flight"


def test_an_old_round_that_closed_is_not_ghosted(db):
    """A rejection is a rejection however old — silence is what defines ghosting."""
    key = _job(db, "Closed Co", "Rejected")
    _age_round(db, key, "technical", jobs_db.GHOSTED_AFTER_DAYS + 100)
    assert db.classify_interviews()[0]["outcome"] == "failed"

    won = _job(db, "Won Co", "Offer", link="http://w/1")
    _age_round(db, won, "final_round", jobs_db.GHOSTED_AFTER_DAYS + 100)
    outcomes = {r["company"]: r["outcome"] for r in db.classify_interviews()}
    assert outcomes["Won Co"] == "advanced"


def test_ghosted_counts_against_the_rate_but_in_flight_does_not(db):
    won = _job(db, "Adv Co", "Offer", link="http://a/1")
    _age_round(db, won, "technical", 1)
    ghost = _job(db, "Ghost Co", "Applied", link="http://g/1")
    _age_round(db, ghost, "technical", jobs_db.GHOSTED_AFTER_DAYS + 5)
    live = _job(db, "Live Co", "Applied", link="http://l/1")
    _age_round(db, live, "technical", 1)

    tech = next(r for r in db.interview_stats()["by_type"]
                if r["interview_type"] == "technical")["total"]
    assert (tech["advanced"], tech["ghosted"], tech["in_flight"]) == (1, 1, 1)
    # 1 advanced out of (1 advanced + 0 failed + 1 ghosted); the live round is excluded.
    assert tech["rate"] == 50.0


def test_an_earlier_round_is_never_ghosted(db):
    """Ghosting applies to the last round only — an earlier one already advanced."""
    key = _job(db, "Progressed Co", "Applied")
    _age_round(db, key, "phone_screen", jobs_db.GHOSTED_AFTER_DAYS + 60)
    _age_round(db, key, "technical", jobs_db.GHOSTED_AFTER_DAYS + 40)

    outcomes = {r["interview_type"]: r["outcome"] for r in db.classify_interviews()}
    assert outcomes["phone_screen"] == "advanced"
    assert outcomes["technical"] == "ghosted"
