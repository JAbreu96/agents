import os
import sys
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src import jobs_db  # noqa: E402

mcp = FastMCP("job-tracker")


def _compact(row: dict) -> dict:
    return {
        "company": row["company"],
        "title": row["position_title"],
        "link": row["link"],
        "date_added": row["date_added"],
        "date_applied": row["date_applied"],
        "status": row["status"],
        "outreach_date": row["outreach_date"],
    }


def _match_company(rows: list[dict], company: str) -> list[dict]:
    query = company.lower().strip()
    exact = [r for r in rows if r["company"].lower().strip() == query]
    if exact:
        return exact
    return [r for r in rows if query in r["company"].lower()]


def _find_one_match(company: str) -> dict:
    rows = jobs_db.get_all_jobs()
    matches = _match_company(rows, company)
    if not matches:
        raise ValueError(f"No job found matching company: '{company}'")
    if len(matches) > 1:
        names = ", ".join(r["company"] for r in matches)
        raise ValueError(f"Ambiguous match — {len(matches)} companies found: {names}. Be more specific.")
    return matches[0]


@mcp.tool()
def list_jobs_missing_outreach() -> list[dict]:
    """List all tracked jobs that haven't had outreach yet (Outreach Date column is empty)."""
    rows = jobs_db.get_all_jobs()
    return [_compact(r) for r in rows if not r["outreach_date"]]


@mcp.tool()
def list_all_jobs(include_outreached: bool = True) -> list[dict]:
    """List all tracked jobs in compact format. Set include_outreached=False to hide jobs that already have outreach."""
    rows = jobs_db.get_all_jobs()
    if not include_outreached:
        rows = [r for r in rows if not r["outreach_date"]]
    return [_compact(r) for r in rows]


@mcp.tool()
def filter_jobs(
    company: str | None = None,
    has_outreach: bool | None = None,
    days_since_added: int | None = None,
) -> list[dict]:
    """
    Filter jobs by one or more criteria:
    - company: case-insensitive substring match on company name
    - has_outreach: True = only jobs with outreach sent, False = only jobs without
    - days_since_added: only jobs added within the last N days
    """
    rows = jobs_db.get_all_jobs()

    if company:
        rows = _match_company(rows, company)

    if has_outreach is not None:
        if has_outreach:
            rows = [r for r in rows if r["outreach_date"]]
        else:
            rows = [r for r in rows if not r["outreach_date"]]

    if days_since_added is not None:
        cutoff = date.today() - timedelta(days=days_since_added)
        filtered = []
        for r in rows:
            d = jobs_db._parse_date(r["date_added"])
            if d and d >= cutoff:
                filtered.append(r)
        rows = filtered

    return [_compact(r) for r in rows]


@mcp.tool()
def get_job_by_company(company: str) -> dict:
    """
    Get the full details of a job by company name (case-insensitive, substring match).
    Returns the complete record including summary, contacts, and notes.
    Raises an error if no match or multiple ambiguous matches are found.
    """
    return _find_one_match(company)


@mcp.tool()
def mark_outreached(company: str, outreach_date: str = "") -> dict:
    """
    Mark a job as outreached by writing today's date (or a provided date) to the Outreach Date field.
    - company: case-insensitive match
    - outreach_date: YYYY-MM-DD format; defaults to today if not provided
    """
    row = _find_one_match(company)
    date_str = outreach_date.strip() if outreach_date.strip() else str(date.today())
    jobs_db.mark_outreached(row["company"], row["date_added"], date_str,
                            row["position_title"], row["link"])

    return {
        "success": True,
        "company": row["company"],
        "outreach_date": date_str,
    }


VALID_STATUSES = {"Tracking", "Applied", "Phone Screen", "Technical", "System Design", "Behavioral", "Offer", "Rejected"}


@mcp.tool()
def add_job(
    company: str,
    title: str,
    link: str,
    summary: str = "",
    location: str = "",
    contacts: str = "",
    notes: str = "",
    status: str = "Tracking",
    date_added: str = "",
) -> dict:
    """
    Add a new job to the tracker, or update it in place if the link already matches
    an existing (non-archived) entry.
    - company, title, link: required
    - summary, location, contacts, notes: optional free-text fields
    - status: defaults to 'Tracking'; must be one of the valid status values
    - date_added: YYYY-MM-DD; defaults to today (ignored when updating an existing match)
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    existing = jobs_db.find_job_by_link(link)
    date_str = existing["date_added"] if existing else (date_added.strip() or str(date.today()))

    job = {
        "company": company.strip(),
        "position_title": title.strip(),
        "job_summary": summary.strip(),
        "location": location.strip(),
        "link": link.strip(),
        "date_added": date_str,
        "contacts": contacts.strip(),
        "notes": notes.strip(),
        "outreach_date": existing["outreach_date"] if existing else "",
        "date_applied": existing["date_applied"] if existing else "",
        "status": status.strip(),
        "followup_log": existing["followup_log"] if existing else "",
    }
    jobs_db.upsert_job(job)

    return {"success": True, "updated": existing is not None, **_compact(job)}


@mcp.tool()
def update_job_status(company: str, status: str) -> dict:
    """
    Update the Status field for a job. Valid values:
    Tracking, Applied, Phone Screen, Technical, System Design, Behavioral, Offer, Rejected.
    - company: case-insensitive match
    - status: one of the valid status values above
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    row = _find_one_match(company)
    jobs_db.update_status(row["company"], row["date_added"], status,
                          row["position_title"], row["link"])

    return {"success": True, "company": row["company"], "status": status}


@mcp.tool()
def update_notes(company: str, notes: str) -> dict:
    """
    Overwrite the Notes field for a job.
    - company: case-insensitive match
    - notes: new notes content (replaces existing value)
    """
    row = _find_one_match(company)
    jobs_db.update_notes(row["company"], row["date_added"], notes,
                         row["position_title"], row["link"])
    return {"success": True, "company": row["company"], "notes": notes}


@mcp.tool()
def update_contacts(company: str, contacts: str) -> dict:
    """
    Overwrite the Contacts field for a job.
    - company: case-insensitive match
    - contacts: new contacts content (replaces existing value)
    """
    row = _find_one_match(company)
    jobs_db.update_contacts(row["company"], row["date_added"], contacts,
                            row["position_title"], row["link"])
    return {"success": True, "company": row["company"], "contacts": contacts}


@mcp.tool()
def get_stats() -> dict:
    """
    Return a summary of the job tracker: total jobs, counts per status, and outreach coverage.
    Useful for digests and dashboards without pulling every row.
    """
    rows = jobs_db.get_all_jobs()
    status_counts: dict[str, int] = {}
    for r in rows:
        s = r["status"] or "Unknown"
        status_counts[s] = status_counts.get(s, 0) + 1

    outreached = sum(1 for r in rows if r["outreach_date"])
    return {
        "total": len(rows),
        "by_status": status_counts,
        "outreached": outreached,
        "not_outreached": len(rows) - outreached,
    }


@mcp.tool()
def list_jobs_needing_followup(days: int = 7) -> list[dict]:
    """
    Return jobs that are stale and may need a follow-up nudge. A job qualifies if status
    is still 'Applied' AND either:
    - date_applied is set and more than `days` days ago, OR
    - outreach_date is set and more than `days` days ago (and no date_applied yet)
    Sorted oldest activity first. Default threshold: 7 days.
    """
    rows = jobs_db.get_all_jobs()
    cutoff = date.today() - timedelta(days=days)
    stale = []
    for r in rows:
        if r["status"] != "Applied":
            continue
        anchor = jobs_db._parse_date(r["date_applied"]) or jobs_db._parse_date(r["outreach_date"])
        if anchor and anchor <= cutoff:
            stale.append((anchor, r))
    stale.sort(key=lambda x: x[0])
    return [_compact(r) for _, r in stale]


@mcp.tool()
def list_jobs_added_recently(days: int = 7) -> list[dict]:
    """List jobs added within the last N days (default: 7), sorted newest first."""
    rows = jobs_db.get_all_jobs()
    cutoff = date.today() - timedelta(days=days)
    recent = []
    for r in rows:
        d = jobs_db._parse_date(r["date_added"])
        if d and d >= cutoff:
            recent.append((d, r))
    recent.sort(key=lambda x: x[0], reverse=True)
    return [_compact(r) for _, r in recent]


@mcp.tool()
def archive_old_jobs(days: int = 60, dry_run: bool = False) -> dict:
    """
    Soft-archive jobs older than `days` days (default: 60) — sets them aside so they
    no longer show up in normal listings, but keeps them in the local DB.
    - dry_run: if True, returns which jobs would be archived without making any changes.
    """
    result = jobs_db.archive_jobs(days=days, dry_run=dry_run)
    return {
        "dry_run": result["dry_run"],
        ("would_archive_count" if dry_run else "archived_count"): result["count"],
        "days_threshold": days,
        "companies": result["companies"],
    }


if __name__ == "__main__":
    mcp.run()
