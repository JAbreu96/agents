"""
Resolving an inbound email to one tracked row.

Every case here is drawn from real mail that arrived in August 2026, where a
company-only match would have closed out roles that were still live.
"""

import pytest

from src import jobs_db
from mcp_servers.job_tracker import server


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    return jobs_db


def _job(db, company, title, link, status="Applied", added="2026-08-01"):
    db.upsert_job({
        "company": company, "position_title": title, "job_summary": "", "location": "",
        "link": link, "date_added": added, "contacts": "", "notes": "",
        "outreach_date": "", "date_applied": "", "status": status, "followup_log": "",
    })


def _status(db, company, title):
    return next(r["status"] for r in db.get_all_jobs()
                if r["company"] == company and r["position_title"] == title)


def test_abbvie_rejection_closes_only_the_quoted_role(db):
    """One Scientist-I rejection must not close the five other AbbVie roles."""
    for t in ["Engineer, Validation Commissioning", "Engineer, Technology II",
              "Scientist I, Multi-Specifics Expression", "Associate Backend Software Engineer II"]:
        _job(db, "AbbVie", t, f"http://abbvie/{t}")

    server.update_job_status("AbbVie", "Rejected",
                             position_title="Scientist I, Multi-Specifics Expression")

    assert _status(db, "AbbVie", "Scientist I, Multi-Specifics Expression") == "Rejected"
    assert _status(db, "AbbVie", "Engineer, Technology II") == "Applied"
    assert sum(1 for r in db.get_all_jobs() if r["status"] == "Rejected") == 1


def test_company_only_update_refuses_when_several_roles_exist(db):
    _job(db, "AbbVie", "Engineer, Technology II", "http://abbvie/1")
    _job(db, "AbbVie", "Associate Backend Software Engineer II", "http://abbvie/2")

    with pytest.raises(ValueError, match="Ambiguous"):
        server.update_job_status("AbbVie", "Rejected")


def test_crowe_rejection_for_an_untracked_role_matches_nothing(db):
    """Crowe rejected Dynamics 365 roles; the tracked row was a different job."""
    _job(db, "Crowe LLP", "AI Functional Consultant", "http://crowe/1")

    got = server.find_job_for_email("Crowe", "Microsoft Dynamics 365 Finance Consulting Lead")

    assert got["match"] == "none"


def test_northmarq_exact_title_resolves(db):
    _job(db, "Northmarq", "IT Business Analyst – Intelligence & AI", "http://nm/1")

    got = server.find_job_for_email("Northmarq", "IT Business Analyst – Intelligence & AI")

    assert got["match"] == "exact"
    assert got["candidates"][0]["title"] == "IT Business Analyst – Intelligence & AI"


def test_padded_ats_title_still_resolves(db):
    """Rejection mail pads titles; a tracked 'Software Engineer II' should match."""
    _job(db, "Rippling", "Software Engineer II", "http://rip/1")

    got = server.find_job_for_email("Rippling", "Software Engineer II, Backend - Platform Team")

    assert got["match"] == "exact"


def test_duplicate_rows_report_ambiguous_rather_than_guessing(db):
    """Mindrift has six identical Full-Stack rows; triage must ask, not pick."""
    for i in range(6):
        _job(db, "Mindrift", "Freelance Full-Stack Web App Developer", f"http://mindrift/{i}")

    got = server.find_job_for_email("Mindrift", "Freelance Full-Stack Web App Developer")

    assert got["match"] == "ambiguous"
    assert len(got["candidates"]) == 6


def test_link_beats_title_for_identity(db):
    _job(db, "Mindrift", "Freelance Full-Stack Web App Developer", "http://mindrift/a")
    _job(db, "Mindrift", "Freelance Full-Stack Web App Developer", "http://mindrift/b")

    server.update_job_status("Mindrift", "Rejected", link="http://mindrift/b")

    rows = {r["link"]: r["status"] for r in db.get_all_jobs()}
    assert rows["http://mindrift/b"] == "Rejected"
    assert rows["http://mindrift/a"] == "Applied"


def test_unknown_company_is_none(db):
    _job(db, "Northmarq", "IT Business Analyst", "http://nm/1")
    assert server.find_job_for_email("Triangle Manufacturing", "Software Engineer")["match"] == "none"


def test_substring_company_without_title_is_not_exact(db):
    """'Citi' must not silently resolve to '08763 Citi Canada Technology Services ULC'."""
    _job(db, "08763 Citi Canada Technology Services ULC",
         "Java Full Stack Developer - Assistant Vice President", "http://citi/ca")

    got = server.find_job_for_email("Citi", "")

    assert got["match"] == "ambiguous"


def test_exact_company_name_without_title_still_resolves(db):
    """An unambiguous, exactly-named company with one role stays writable."""
    _job(db, "Northmarq", "IT Business Analyst", "http://nm/1")

    assert server.find_job_for_email("Northmarq", "")["match"] == "exact"
