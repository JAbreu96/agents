"""
The recruiter backfill: identity, matching, and the one thing it must never do.

It links job rows that already exist. record_recruiter_outreach() would have been
the obvious tool and is the wrong one -- it mints its own synthetic link and calls
upsert_job, so it would leave nine duplicates beside the nine real rows. The row
count is therefore the assertion that matters most here, not the recruiter count.
"""

import importlib.util
import json
import os
import sys

import pytest

from src import jobs_db

_spec = importlib.util.spec_from_file_location(
    "bfr", os.path.join(os.path.dirname(__file__), "..", "scripts", "backfill_recruiters.py"))
bfr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bfr)


# --- identity ---------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Jack Dahler", "jack-dahler"),
    ("Manish K.", "manish-k"),
    ("Samir B", "samir-b"),
    ("M Chaitanya Mohan", "m-chaitanya-mohan"),
    ("Muhammad Umar Rafique", "muhammad-umar-rafique"),
])
def test_identity_is_the_normalised_name(name, expected):
    assert bfr.slugify(name) == expected


def test_the_same_person_slugs_the_same_way():
    """
    Suryakant Pandey sent three InMails. Identity keys on the person, so those
    are one recruiter with three messages -- not three recruiters with one role
    each, which is the number the Insights card exists to report.
    """
    assert bfr.slugify("Suryakant Pandey") == bfr.slugify("suryakant  pandey")


# --- matching a recruiter to the row they sourced ---------------------------

ROWS = [
    {"company": "GTE", "date_added": "2026-08-19", "position_title": "Product Engineer",
     "link": "thread-gte",
     "contacts": "TWO competing agency recruiters: 1) Maddison Jonas — Senior Consultant "
                 "2) Jack Dahler"},
    {"company": "Goodlane Logistics", "date_added": "2026-08-17", "position_title": "Founding Engineer",
     "link": "thread-good",
     "contacts": "Kim Hanson <khanson@brycepoynt.com> (BrycePoynt, agency)"},
]


def test_a_recruiter_matches_the_row_naming_them():
    assert bfr.match_row("Kim Hanson", ROWS)["company"] == "Goodlane Logistics"


def test_both_recruiters_on_one_row_match_it():
    """GTE is one role pitched by two agencies. Both must find it."""
    assert bfr.match_row("Jack Dahler", ROWS)["company"] == "GTE"
    assert bfr.match_row("Maddison Jonas", ROWS)["company"] == "GTE"


def test_an_unmatched_recruiter_returns_nothing():
    """Most InMails are cold blasts with no tracked role, and that is fine."""
    assert bfr.match_row("Nobody Here", ROWS) is None


def test_a_blank_name_never_matches():
    """A falsy needle must not substring-match every row."""
    assert bfr.match_row("", ROWS) is None


# --- end to end, against a temp database ------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    jobs_db._reset_schema_cache()
    jobs_db.upsert_job({
        "company": "GTE", "position_title": "Product Engineer",
        "link": "https://www.linkedin.com/messaging/thread/gte",
        "date_added": "2026-08-19", "status": "Phone Screen",
        "contacts": "Maddison Jonas and Jack Dahler, competing agencies",
    })
    return jobs_db


def _apply(db, messages):
    """Runs what --write does, without shelling out to the CLI."""
    unlinked = db.unlinked_recruiter_rows()
    for row in unlinked:
        row["contacts"] = "Maddison Jonas and Jack Dahler, competing agencies"
    for msg in messages:
        ident = bfr.slugify(msg["name"])
        rid = db.upsert_recruiter(source="linkedin", identity=ident,
                                  name=msg["name"], seen_date=msg["date"])
        db.record_recruiter_message(rid, "inbound", msg["date"], subject=msg["subject"],
                                    account="alt", message_id=msg["message_id"])
        row = bfr.match_row(msg["name"], unlinked)
        if row:
            db.link_recruiter_job(rid, company=row["company"], date_added=row["date_added"],
                                  position_title=row["position_title"], link=row["link"],
                                  sourced_date=msg["date"], account="alt",
                                  message_id=msg["message_id"])


MSGS = [
    {"message_id": "m1", "name": "Jack Dahler", "date": "2026-08-19", "subject": "Product Engineer - GTE"},
    {"message_id": "m2", "name": "Maddison Jonas", "date": "2026-08-18", "subject": "Quick question?"},
    {"message_id": "m3", "name": "Nobody Here", "date": "2026-08-01", "subject": "Cold blast"},
]


def test_the_backfill_creates_no_job_rows(db):
    """
    The failure this script exists to avoid. If it ever inserts, the nine tracked
    rows gain nine duplicates and the audit that prompted all this is undone.
    """
    before = len(db.get_all_jobs(include_archived=True))
    _apply(db, MSGS)
    assert len(db.get_all_jobs(include_archived=True)) == before


def test_every_sender_becomes_a_recruiter_even_without_a_role(db):
    """Cold blasts are recruiter history; that is the point of capturing them."""
    _apply(db, MSGS)
    assert len(db.get_recruiters()) == 3


def test_two_recruiters_link_to_the_one_role(db):
    _apply(db, MSGS)
    assert len(db.get_recruiter_jobs()) == 2          # two links
    assert db.recruiter_coverage()["captured"] == 1   # one role


def test_the_row_stops_being_suspected(db):
    assert len(db.unlinked_recruiter_rows()) == 1
    _apply(db, MSGS)
    assert db.unlinked_recruiter_rows() == []


def test_running_it_twice_changes_nothing(db):
    _apply(db, MSGS)
    snapshot = (len(db.get_all_jobs(include_archived=True)), len(db.get_recruiters()),
                len(db.get_recruiter_jobs()), db.recruiter_coverage()["captured"])
    _apply(db, MSGS)
    assert (len(db.get_all_jobs(include_archived=True)), len(db.get_recruiters()),
            len(db.get_recruiter_jobs()), db.recruiter_coverage()["captured"]) == snapshot


def test_the_shipped_input_file_parses(db):
    """The map the agent wrote from Gmail, checked for shape rather than content."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "backfill", "recruiters.json")
    if not os.path.exists(path):
        pytest.skip("input map not present")
    msgs = json.load(open(path))
    assert msgs and all(m.get("name") and m.get("message_id") and m.get("date") for m in msgs)
    assert all(bfr.slugify(m["name"]) for m in msgs)
