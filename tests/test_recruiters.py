"""
Recruiter capture.

The row that motivated this had two roles in one position_title, joined by a
slash, keyed on `mailto:laxmano@kastechssg.com` — because `jobs` had no concept
of a recruiter and a recruiter sends N roles.

The cases that matter are the ones that break silently: LinkedIn's shared relay
address, per-account Gmail id spaces, and a sheet sync rewriting every job row.
"""

import sqlite3

import pytest

from src import jobs_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_db, "DB_PATH", str(tmp_path / "jobs.db"))
    return jobs_db


def _job(db, company, title, link, added="2026-08-20", status="Tracking"):
    db.upsert_job({
        "company": company, "position_title": title, "job_summary": "", "location": "",
        "link": link, "date_added": added, "contacts": "", "notes": "",
        "outreach_date": "", "date_applied": "", "status": status, "followup_log": "",
    })
    return dict(company=company, date_added=added, position_title=title, link=link)


def _capture(db, recruiter_id, company, title, source="email",
             identity="laxmano@kastechssg.com", added="2026-08-20",
             account="primary", message_id=""):
    """One role, captured the way the skill captures it."""
    link = db.recruiter_link(source, identity, title)
    key = _job(db, company, title, link, added=added)
    db.link_recruiter_job(recruiter_id, sourced_date=added, account=account,
                          message_id=message_id, **key)
    return key


# --- the motivating case ----------------------------------------------------

def test_one_recruiter_n_roles_produces_n_rows(db):
    """Laxman sent two roles fourteen minutes apart. That is two rows."""
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com",
                              name="Laxman Ottem", agency="Kastech SSG")
    _capture(db, rid, "Kastech SSG", "Frontend Engineer")
    _capture(db, rid, "Kastech SSG", "Cloud Backend Engineer")

    roles = db.get_recruiter_jobs(rid)
    assert len(roles) == 2
    assert {r["position_title"] for r in roles} == {
        "Frontend Engineer", "Cloud Backend Engineer"}
    # Distinct rows in `jobs`, so they can carry independent statuses.
    assert len({r["link"] for r in roles}) == 2


def test_two_roles_same_title_same_recruiter_do_not_collide(db):
    """
    Same recruiter, same title, different day. The synthetic link is identical,
    so date_added is what has to keep them apart.
    """
    rid = db.upsert_recruiter("email", "gautamk@acestackllc.com", agency="AceStack LLC")
    _capture(db, rid, "AceStack LLC", "Cloud Engineer", identity="gautamk@acestackllc.com",
             added="2026-08-20")
    _capture(db, rid, "AceStack LLC", "Cloud Engineer", identity="gautamk@acestackllc.com",
             added="2026-08-21")
    assert len(db.get_recruiter_jobs(rid)) == 2


# --- identity ---------------------------------------------------------------

def test_linkedin_recruiters_sharing_a_relay_address_stay_distinct(db):
    """
    THE regression this schema exists for. InMail arrives from the shared relay
    inmail-hit-reply@linkedin.com. Keying recruiters on the raw sender address
    would collapse every LinkedIn recruiter into one row.
    """
    a = db.upsert_recruiter("linkedin", "sarah-chen-42", name="Sarah Chen",
                            email="inmail-hit-reply@linkedin.com")
    b = db.upsert_recruiter("linkedin", "marcus-webb-7", name="Marcus Webb",
                            email="inmail-hit-reply@linkedin.com")
    assert a != b
    assert len(db.get_recruiters()) == 2


def test_same_identity_across_sources_stays_distinct(db):
    """'email' and 'linkedin' are separate namespaces."""
    a = db.upsert_recruiter("email", "jane@agency.com")
    b = db.upsert_recruiter("linkedin", "jane@agency.com")
    assert a != b


def test_upsert_recruiter_is_idempotent_and_only_widens(db):
    """A later message with less detail must not erase what was learned."""
    first = db.upsert_recruiter("email", "laxmano@kastechssg.com",
                                name="Laxman Ottem", agency="Kastech SSG")
    again = db.upsert_recruiter("email", "laxmano@kastechssg.com")
    assert first == again

    row = db.get_recruiters()[0]
    assert row["name"] == "Laxman Ottem"
    assert row["agency"] == "Kastech SSG"


def test_two_recruiters_at_one_agency(db):
    """AceStack pitched twice under two different addresses."""
    db.upsert_recruiter("email", "gautamk@acestackllc.com", name="Gautam Kumar",
                        agency="AceStack LLC")
    db.upsert_recruiter("email", "dhruvr@acestackllc.com", name="Dhruv Rajput",
                        agency="AceStack LLC")
    assert len(db.get_recruiters()) == 2


def test_unknown_source_is_rejected(db):
    with pytest.raises(ValueError):
        db.upsert_recruiter("carrier-pigeon", "someone")


# --- the synthetic link -----------------------------------------------------

def test_recruiter_link_is_stable_across_runs(db):
    """Re-processing the same email must update, not duplicate."""
    a = db.recruiter_link("email", "laxmano@kastechssg.com", "Frontend Engineer")
    b = db.recruiter_link("email", "laxmano@kastechssg.com", "Frontend Engineer")
    assert a == b == "recruiter:email:laxmano@kastechssg.com/frontend-engineer"


def test_recruiter_link_separates_linkedin_recruiters(db):
    """The link carries identity, not the relay address."""
    a = db.recruiter_link("linkedin", "sarah-chen-42", "Staff Engineer")
    b = db.recruiter_link("linkedin", "marcus-webb-7", "Staff Engineer")
    assert a != b


def test_recruiter_link_survives_html_titles(db):
    """Titles arrive as HTML; '&amp;' in a primary key is a known repair job."""
    link = db.recruiter_link("email", "x@y.com", "Software Verification & QA")
    assert "&" not in link
    assert link.endswith("/software-verification-qa")


# --- durability -------------------------------------------------------------

def test_sheet_sync_does_not_orphan_recruiter_links(db):
    """
    Reproduces what sync_jobs_to_sqlite.py does to every job row on every run.

    INSERT OR REPLACE is delete-then-insert, so every rowid is reassigned. The
    recruiter tables copy the job key rather than referencing a rowid precisely
    so this is survivable; a foreign key with ON DELETE CASCADE would empty them
    here, silently, on a routine sync.
    """
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com", agency="Kastech SSG")
    key = _capture(db, rid, "Kastech SSG", "Frontend Engineer")

    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        f"INSERT OR REPLACE INTO jobs ({', '.join(db.COLUMNS)}) "
        f"VALUES ({', '.join(['?'] * len(db.COLUMNS))})",
        [key["company"], key["position_title"], "", "", key["link"],
         key["date_added"], "", "", "", "", "Tracking", ""],
    )
    conn.commit()
    conn.close()

    roles = db.get_recruiter_jobs(rid)
    assert len(roles) == 1
    assert roles[0]["job_status"] == "Tracking", "link no longer resolves to its job row"


def test_deleted_job_row_still_lists_the_role(db):
    """A LEFT JOIN, so breakage is visible rather than silently dropped."""
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com")
    key = _capture(db, rid, "Kastech SSG", "Frontend Engineer")
    db.delete_job_by_key(key["company"], key["date_added"],
                         key["position_title"], key["link"])

    roles = db.get_recruiter_jobs(rid)
    assert len(roles) == 1
    assert roles[0]["job_status"] is None


# --- messages ---------------------------------------------------------------

def test_reprocessing_the_same_message_records_once(db):
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com")
    for _ in range(2):
        db.record_recruiter_message(rid, "inbound", "2026-08-20", subject="Two roles",
                                    account="primary", message_id="abc123")
    assert len(db.get_recruiter_messages(rid)) == 1


def test_same_message_id_in_each_inbox_does_not_collide(db):
    """
    Gmail ids are per-account. A bare `message_id UNIQUE` would reject a real
    alt-inbox message that happened to share an id with a primary one.
    """
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com")
    db.record_recruiter_message(rid, "inbound", "2026-08-20",
                                account="primary", message_id="dup")
    db.record_recruiter_message(rid, "inbound", "2026-08-20",
                                account="alt", message_id="dup")
    assert len(db.get_recruiter_messages(rid)) == 2


def test_relinking_the_same_role_is_idempotent(db):
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com")
    key = _capture(db, rid, "Kastech SSG", "Frontend Engineer")
    db.link_recruiter_job(rid, sourced_date="2026-08-20", **key)
    assert len(db.get_recruiter_jobs(rid)) == 1


def test_reply_is_recorded_and_counted(db):
    rid = db.upsert_recruiter("email", "laxmano@kastechssg.com")
    db.record_recruiter_message(rid, "inbound", "2026-08-20", message_id="m1")
    db.record_recruiter_message(rid, "reply", "2026-08-21", message_id="m2")
    assert db.get_recruiters()[0]["reply_count"] == 1


def test_unknown_direction_is_rejected(db):
    rid = db.upsert_recruiter("email", "x@y.com")
    with pytest.raises(ValueError):
        db.record_recruiter_message(rid, "forwarded", "2026-08-20")


def test_message_advances_last_seen(db):
    rid = db.upsert_recruiter("email", "x@y.com", seen_date="2026-08-20")
    db.record_recruiter_message(rid, "inbound", "2026-08-25", message_id="m1")
    assert db.get_recruiters()[0]["last_seen"] == "2026-08-25"


def test_lookup_does_not_advance_last_seen(db):
    """
    `last_seen` means "last heard from", not "last touched". The capture step
    calls upsert_recruiter to resolve an id on every message, so if a bare
    lookup bumped the date, every recruiter would read as contacted today.
    """
    rid = db.upsert_recruiter("email", "x@y.com", seen_date="2026-08-20")
    db.upsert_recruiter("email", "x@y.com")  # resolve id only
    assert db.get_recruiters()[0]["last_seen"] == "2026-08-20"


# --- the MCP write path -----------------------------------------------------
# record_recruiter_outreach is the single entry point inbox-triage calls, so it
# is worth testing directly rather than only its parts.

@pytest.fixture
def srv(db, monkeypatch):
    import importlib
    import mcp_servers.job_tracker.server as server
    importlib.reload(server)
    monkeypatch.setattr(server.jobs_db, "DB_PATH", db.DB_PATH)
    return server


def _call(tool, **kw):
    """FastMCP wraps tools; reach the underlying function."""
    return (getattr(tool, "fn", None) or tool)(**kw)


def test_one_email_two_roles_becomes_two_rows(srv):
    """Called once per role, sharing a message_id — the Kastech case, end to end."""
    for title in ("Frontend Engineer", "Cloud Backend Engineer"):
        out = _call(srv.record_recruiter_outreach,
                    source="email", identity="laxmano@kastechssg.com",
                    company="Kastech SSG", position_title=title,
                    occurred_date="2026-08-20", name="Laxman Ottem",
                    agency="Kastech SSG", message_id="msg-1")
        assert "error" not in out

    roles = _call(srv.recruiter_roles, identity="laxmano@kastechssg.com")
    assert len(roles) == 2
    assert all(r["job_status"] == "Tracking" for r in roles)
    # One email, one message — not one per role.
    assert len(srv.jobs_db.get_recruiter_messages()) == 1


def test_reprocessing_an_email_does_not_duplicate(srv):
    for _ in range(2):
        _call(srv.record_recruiter_outreach,
              source="email", identity="laxmano@kastechssg.com",
              company="Kastech SSG", position_title="Frontend Engineer",
              occurred_date="2026-08-20", message_id="msg-1")
    assert len(_call(srv.recruiter_roles)) == 1
    assert len(srv.jobs_db.get_recruiters()) == 1


def test_reprocessing_preserves_an_advanced_status(srv):
    """
    A re-run must not drag a role back to 'Tracking' after Joel replied and it
    moved to Phone Screen — inbox-triage's never-downgrade rule.
    """
    _call(srv.record_recruiter_outreach,
          source="email", identity="laxmano@kastechssg.com",
          company="Kastech SSG", position_title="Frontend Engineer",
          occurred_date="2026-08-20", message_id="msg-1")
    link = srv.jobs_db.recruiter_link("email", "laxmano@kastechssg.com",
                                      "Frontend Engineer")
    row = srv.jobs_db.find_job_by_link(link)
    srv.jobs_db.upsert_job({**row, "status": "Phone Screen"})

    _call(srv.record_recruiter_outreach,
          source="email", identity="laxmano@kastechssg.com",
          company="Kastech SSG", position_title="Frontend Engineer",
          occurred_date="2026-08-22", message_id="msg-2")
    assert srv.jobs_db.find_job_by_link(link)["status"] == "Phone Screen"


def test_linkedin_outreach_uses_the_profile_slug(srv):
    """Two InMails, one relay address, two recruiters."""
    for slug, name in (("sarah-chen-42", "Sarah Chen"), ("marcus-webb-7", "Marcus Webb")):
        _call(srv.record_recruiter_outreach,
              source="linkedin", identity=slug, company="Unnamed client",
              position_title="Staff Engineer", occurred_date="2026-08-22",
              name=name, email="inmail-hit-reply@linkedin.com",
              account="alt", message_id=f"li-{slug}")
    assert len(_call(srv.list_recruiters)) == 2
    assert len(_call(srv.recruiter_roles)) == 2


def test_bad_source_is_rejected_not_raised(srv):
    out = _call(srv.record_recruiter_outreach, source="pigeon", identity="x",
                company="C", position_title="T")
    assert "error" in out


def test_reply_is_recorded_through_the_tool(srv):
    _call(srv.record_recruiter_outreach,
          source="email", identity="laxmano@kastechssg.com",
          company="Kastech SSG", position_title="Frontend Engineer",
          occurred_date="2026-08-20", message_id="msg-1")
    _call(srv.record_recruiter_reply, identity="laxmano@kastechssg.com",
          occurred_date="2026-08-21", message_id="msg-2")
    assert _call(srv.list_recruiters)[0]["replies"] == 1
