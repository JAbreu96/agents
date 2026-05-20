from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

import sheet

mcp = FastMCP("job-tracker")


def _compact(row: dict) -> dict:
    return {
        "row": row["row_index"],
        "company": row["company"],
        "title": row["title"],
        "link": row["link"],
        "date_added": row["date_added"],
        "outreach_date": row["outreach_date"],
    }


def _match_company(rows: list[dict], company: str) -> list[dict]:
    query = company.lower().strip()
    exact = [r for r in rows if r["company"].lower().strip() == query]
    if exact:
        return exact
    return [r for r in rows if query in r["company"].lower()]


@mcp.tool()
def list_jobs_missing_outreach() -> list[dict]:
    """List all tracked jobs that haven't had outreach yet (Outreach Date column is empty)."""
    rows = sheet.read_all_rows()
    return [_compact(r) for r in rows if not r["outreach_date"]]


@mcp.tool()
def list_all_jobs(include_outreached: bool = True) -> list[dict]:
    """List all tracked jobs in compact format. Set include_outreached=False to hide jobs that already have outreach."""
    rows = sheet.read_all_rows()
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
    rows = sheet.read_all_rows()

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
            d = sheet._parse_date(r["date_added"])
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
    rows = sheet.read_all_rows()
    matches = _match_company(rows, company)

    if not matches:
        raise ValueError(f"No job found matching company: '{company}'")
    if len(matches) > 1:
        names = ", ".join(r["company"] for r in matches)
        raise ValueError(f"Ambiguous match — {len(matches)} companies found: {names}. Be more specific.")

    return matches[0]


@mcp.tool()
def mark_outreached(company: str, outreach_date: str = "") -> dict:
    """
    Mark a job as outreached by writing today's date (or a provided date) to the Outreach Date column.
    - company: case-insensitive match
    - outreach_date: YYYY-MM-DD format; defaults to today if not provided
    """
    rows = sheet.read_all_rows()
    matches = _match_company(rows, company)

    if not matches:
        raise ValueError(f"No job found matching company: '{company}'")
    if len(matches) > 1:
        names = ", ".join(r["company"] for r in matches)
        raise ValueError(f"Ambiguous match — {len(matches)} companies found: {names}. Be more specific.")

    row = matches[0]
    date_str = outreach_date.strip() if outreach_date.strip() else str(date.today())
    sheet.mark_outreached(row["row_index"], date_str)

    return {
        "success": True,
        "company": row["company"],
        "row": row["row_index"],
        "outreach_date": date_str,
    }


VALID_STATUSES = {"Tracking", "Applied", "Phone Screen", "Technical", "System Design", "Behavioral", "Offer", "Rejected"}


@mcp.tool()
def update_job_status(company: str, status: str) -> dict:
    """
    Update the Status column for a job. Valid values:
    Tracking, Applied, Phone Screen, Technical, System Design, Behavioral, Offer, Rejected.
    - company: case-insensitive match
    - status: one of the valid status values above
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

    rows = sheet.read_all_rows()
    matches = _match_company(rows, company)

    if not matches:
        raise ValueError(f"No job found matching company: '{company}'")
    if len(matches) > 1:
        names = ", ".join(r["company"] for r in matches)
        raise ValueError(f"Ambiguous match — {len(matches)} companies found: {names}. Be more specific.")

    row = matches[0]
    sheet.update_status(row["row_index"], status)

    return {"success": True, "company": row["company"], "row": row["row_index"], "status": status}


@mcp.tool()
def list_jobs_added_recently(days: int = 7) -> list[dict]:
    """List jobs added within the last N days (default: 7), sorted newest first."""
    rows = sheet.read_all_rows()
    cutoff = date.today() - timedelta(days=days)
    recent = []
    for r in rows:
        d = sheet._parse_date(r["date_added"])
        if d and d >= cutoff:
            recent.append((d, r))
    recent.sort(key=lambda x: x[0], reverse=True)
    return [_compact(r) for _, r in recent]


@mcp.tool()
def archive_old_jobs(days: int = 60, dry_run: bool = False) -> dict:
    """
    Move jobs older than `days` days (default: 60) from the active tracker to the Archive sheet.
    Intended to run on the 1st of each month.
    - dry_run: if True, returns which jobs would be archived without making any changes.
    """
    if dry_run:
        rows = sheet.read_all_rows()
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=days)
        would_archive = [
            r for r in rows
            if sheet._parse_date(r["date_added"]) and sheet._parse_date(r["date_added"]) < cutoff
        ]
        return {
            "dry_run": True,
            "would_archive_count": len(would_archive),
            "days_threshold": days,
            "companies": [_compact(r) for r in would_archive],
        }

    archived = sheet.archive_old_jobs(days)
    return {
        "dry_run": False,
        "archived_count": len(archived),
        "days_threshold": days,
        "companies": [r["company"] for r in archived],
    }


if __name__ == "__main__":
    mcp.run()
