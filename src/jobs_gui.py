"""
Local web GUI for browsing and editing the job tracker.

Reads whichever database jobs_db is configured for -- Turso when
TURSO_DATABASE_URL is set, data/jobs.db otherwise.

Run:
    python src/jobs_gui.py

Then open http://127.0.0.1:5151 in your browser.
"""

import gzip
import io
import os
import sys
from datetime import date
from urllib.parse import urlparse

from flask import Flask, Response, g, jsonify, redirect, render_template, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.job_agent import JobTrackerAgent  # noqa: E402
from src.jobs_db import (  # noqa: E402
    INTERVIEW_TYPES,
    LIST_COLUMNS,
    STATUS_ORDER,
    _connect,
    _WRITE_EXC,
    shared_connection as _shared_connection,
    GHOSTED_AFTER_DAYS,
    RATE_MIN_DENOMINATOR,
    add_interview,
    delete_interview,
    delete_job_by_key,
    export_csv,
    find_job_by_link,
    funnel_stats,
    get_interviews,
    get_recruiter_jobs,
    get_recruiters,
    job_silence_stats,
    upcoming_interviews,
    recruiter_coverage,
    interview_stats,
    upsert_job,
)

EDITABLE_COLUMNS = {
    "company", "status", "notes", "contacts", "job_summary",
    "outreach_date", "date_applied", "followup_log",
}
# The order lives in jobs_db with the rest of the schema vocabulary; the name
# stays bound here because the templates use it.
STATUS_VALUES = STATUS_ORDER

app = Flask(__name__)
# Flask sorts JSON keys by default. On /api/jobs that is 1014 dicts of 11 keys
# reordered for nobody's benefit.
app.json.sort_keys = False


@app.before_request
def _open_scope():
    """
    Every request runs inside one shared_connection().

    It has to be here rather than inside get_db(), because the handlers that
    cost the most never call get_db() at all: insights_view goes straight to the
    jobs_db helpers, and each of those opened its own connection -- seven helpers,
    eleven connections, ~2.1s of the 4.6s that page took.

    Wrapping unconditionally is free because the scope connects lazily, so the
    routes that only render a template still pay nothing.
    """
    g.db_scope = _shared_connection(create=True)
    g.db = g.db_scope.__enter__()


def get_db():
    """
    One connection policy for the whole app: _connect() picks the driver from
    TURSO_DATABASE_URL and builds the schema itself.

    This used to open data/jobs.db directly while every jobs_db helper went to
    Turso, so a single page read two different databases -- the local file was
    153 jobs behind, and the table quietly showed the smaller set.
    """
    if "db" not in g:                      # outside a request (tests, shell)
        g.db_scope = _shared_connection(create=True)
        g.db = g.db_scope.__enter__()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    scope = g.pop("db_scope", None)
    g.pop("db", None)
    if scope is not None:
        scope.__exit__(None, None, None)   # closes the one real connection


# Level 1, not 9: /api/jobs shrinks 980KB -> 290KB either way, and the cheapest
# setting spends 14ms doing it. The database work behind that response is ~250ms,
# so the response itself was the larger half of the wait.
_GZIP_MIN_BYTES = 8192


@app.after_request
def _compress(response):
    if (response.direct_passthrough
            or response.status_code < 200 or response.status_code >= 300
            or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
            or "Content-Encoding" in response.headers
            or response.content_length is not None
            and response.content_length < _GZIP_MIN_BYTES):
        return response
    data = response.get_data()
    if len(data) < _GZIP_MIN_BYTES:
        return response
    response.set_data(gzip.compress(data, 1))
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = response.content_length
    response.headers.add("Vary", "Accept-Encoding")
    return response


@app.route("/")
def index():
    return render_template("jobs.html", status_values=STATUS_VALUES,
                           interview_types=INTERVIEW_TYPES)


@app.route("/kanban")
def kanban():
    return render_template("kanban.html", status_values=STATUS_VALUES)


@app.route("/api/jobs")
def api_jobs():
    """
    Archived rows are hidden by default — this is the working table.

    ?include_archived=1 is what the Insights drill-through uses: the funnel counts
    archived rows on purpose (a finished outcome is its most useful input), so a
    click from a funnel stage has to land on the same population it just counted,
    or the number changes when you follow it.
    """
    include_archived = request.args.get("include_archived") in ("1", "true", "yes")
    db = get_db()
    # Named columns, not SELECT *: dropping job_summary here takes the payload
    # from 2.1MB to 0.68MB and the query from 230ms to 152ms. Trimming in Python
    # instead would still drag the column across the wire from Turso.
    query = f"SELECT {', '.join(LIST_COLUMNS)} FROM jobs"
    if not include_archived:
        query += " WHERE archived = 0"
    query += " ORDER BY date_added DESC"
    rows = db.execute(query).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/jobs/detail")
def api_job_detail():
    """
    Everything the list deliberately left out, for one row, on expand.

    job_summary and interview rounds are cached differently by the client and
    that is the point: job_summary has exactly one writer -- the edit box in the
    panel -- so once fetched it can be held for the life of the page, and
    ?summary=0 says the client already has it. Rounds have a second writer,
    inbox-triage on a daily cron, so they are re-read on every expand and never
    cached.
    """
    key = {
        "company": (request.args.get("company") or "").strip(),
        "date_added": (request.args.get("date_added") or "").strip(),
        "position_title": (request.args.get("position_title") or "").strip(),
        "link": (request.args.get("link") or "").strip(),
    }
    if not key["company"]:
        return jsonify({"error": "company is required"}), 400

    payload = {"interviews": get_interviews(**key)}
    if request.args.get("summary") not in ("0", "false", "no"):
        row = get_db().execute(
            "SELECT job_summary FROM jobs WHERE company = ? AND date_added = ? "
            "AND position_title = ? AND link = ?",
            (key["company"], key["date_added"], key["position_title"], key["link"]),
        ).fetchone()
        payload["job_summary"] = (row["job_summary"] if row else "") or ""
    return jsonify(payload)


@app.route("/api/jobs/export.csv")
def api_export_csv():
    db = get_db()
    rows = db.execute("SELECT * FROM jobs WHERE archived = 0 ORDER BY date_added DESC").fetchall()
    buf = io.StringIO()
    export_csv([dict(r) for r in rows], buf)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=jobs_export.csv"},
    )


@app.route("/api/jobs/fetch_url", methods=["POST"])
def api_fetch_url():
    payload = request.get_json(force=True)
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    host = urlparse(url).netloc.lower()
    if any(d in host for d in ("linkedin.com", "indeed.com", "glassdoor.com")):
        return jsonify({
            "error": "LinkedIn/Indeed/Glassdoor block automated fetching — paste the details manually."
        }), 400

    try:
        board_info = JobTrackerAgent.detect_job_board(url)
        if board_info:
            board_type, api_url = board_info
            if board_type == "greenhouse":
                record = JobTrackerAgent.fetch_greenhouse_job(api_url, url)
            else:
                record = JobTrackerAgent.fetch_lever_job(api_url, url)
            if record.summary:
                record.summary = JobTrackerAgent.refine_summary(record.summary)
        else:
            html = JobTrackerAgent.fetch_page(url)
            record = JobTrackerAgent.parse_job_page(html, url)

        if record.company and record.company != "(unknown company)":
            record.notes = JobTrackerAgent.research_company(record.company)
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch job posting: {exc}"}), 502

    return jsonify({
        "company": record.company if record.company != "(unknown company)" else "",
        "position_title": record.title if record.title != "(unknown title)" else "",
        "location": record.location if record.location != "(unknown location)" else "",
        "link": url,
        "job_summary": record.summary,
        "notes": record.notes,
    })


@app.route("/api/jobs/add", methods=["POST"])
def api_add_job():
    payload = request.get_json(force=True)
    company = (payload.get("company") or "").strip()
    title = (payload.get("position_title") or "").strip()
    link = (payload.get("link") or "").strip()
    location = (payload.get("location") or "").strip()
    summary = (payload.get("job_summary") or "").strip()
    contacts = (payload.get("contacts") or "").strip()
    notes = (payload.get("notes") or "").strip()
    status = (payload.get("status") or "Tracking").strip()
    date_added = (payload.get("date_added") or "").strip()

    if not company or not title:
        return jsonify({"error": "company and position_title are required"}), 400
    if status and status not in STATUS_VALUES:
        return jsonify({"error": f"status '{status}' is not a recognized value"}), 400
    if link:
        existing = find_job_by_link(link)
        if existing:
            return jsonify({
                "error": f"This URL is already tracked ({existing['company']}, added {existing['date_added']})."
            }), 409

    job = {
        "company": company,
        "position_title": title,
        "job_summary": summary,
        "location": location,
        "link": link,
        "date_added": date_added or date.today().isoformat(),
        "contacts": contacts,
        "notes": notes,
        "outreach_date": "",
        "date_applied": date.today().isoformat() if (status or "Tracking") == "Applied" else "",
        "status": status or "Tracking",
        "followup_log": "",
    }
    upsert_job(job)
    return jsonify(job)


@app.route("/api/jobs/update", methods=["POST"])
def api_update_job():
    payload = request.get_json(force=True)
    company = payload.get("company")
    date_added = payload.get("date_added")
    position_title = payload.get("position_title")
    row_link = payload.get("link")
    field = payload.get("field")
    value = payload.get("value", "")

    if not company or date_added is None:
        return jsonify({"error": "company and date_added are required"}), 400
    if field not in EDITABLE_COLUMNS:
        return jsonify({"error": f"field '{field}' is not editable"}), 400
    if field == "company" and not value.strip():
        return jsonify({"error": "company cannot be blank"}), 400

    db = get_db()

    # Renaming a company moves the row to a new primary key, which can collide.
    # Checked with a SELECT rather than left to the UPDATE, because the driver
    # decides which exception a collision raises -- IntegrityError on SQLite, a
    # bare ValueError over Hrana -- and tests/conftest.py strips TURSO_* for the
    # whole session, so no test can ever exercise the remote path. A SELECT
    # behaves identically on both, so the local suite covers the real behaviour.
    if field == "company" and value != company:
        taken = db.execute(
            "SELECT 1 FROM jobs WHERE company = ? AND date_added = ? "
            "AND position_title = ? AND link = ?",
            (value, date_added, position_title or "", row_link or ""),
        ).fetchone()
        if taken:
            return jsonify({
                "error": f"A job for '{value}' on {date_added} already exists."
            }), 409

    date_applied_value = None
    if field == "status" and value == "Applied":
        row = db.execute(
            "SELECT date_applied FROM jobs WHERE company = ? AND date_added = ? "
            "AND position_title = ? AND link = ?",
            (company, date_added, position_title or "", row_link or ""),
        ).fetchone()
        if row and not (row["date_applied"] or "").strip():
            date_applied_value = date.today().isoformat()

    try:
        if date_applied_value is not None:
            db.execute(
                "UPDATE jobs SET status = ?, date_applied = ? WHERE company = ? "
                "AND date_added = ? AND position_title = ? AND link = ?",
                (value, date_applied_value, company, date_added,
                 position_title or "", row_link or ""),
            )
        else:
            db.execute(
                f"UPDATE jobs SET {field} = ? WHERE company = ? AND date_added = ? "
                f"AND position_title = ? AND link = ?",
                (value, company, date_added, position_title or "", row_link or ""),
            )
        db.commit()
    except _WRITE_EXC:
        # Backstop for a collision the SELECT above raced past.
        return jsonify({
            "error": f"A job for '{value}' on {date_added} already exists."
        }), 409

    result = {"ok": True}
    if date_applied_value is not None:
        result["date_applied"] = date_applied_value
    return jsonify(result)


# --- Interviews -------------------------------------------------------------
# The GUI is the only write path for interviews. Every other surface reads.
# A job is identified here by its full composite key, taken straight from the
# row the user clicked, so the "Ambiguous match" problem that company-keyed
# lookups hit on the 67 companies with multiple postings never arises.

@app.route("/insights")
def insights_view():
    return render_template(
        "insights.html",
        stats=interview_stats(),
        funnel=funnel_stats(),
        rate_min=RATE_MIN_DENOMINATOR,
        ghost_days=GHOSTED_AFTER_DAYS,
        interview_types=INTERVIEW_TYPES,
        recruiters=get_recruiters(),
        recruiter_roles=get_recruiter_jobs(),
        coverage=recruiter_coverage(),
        silence=job_silence_stats(),
        upcoming=upcoming_interviews(include_past=True),
    )


@app.route("/interviews")
def interviews_view():
    """Kept so older bookmarks still land somewhere useful."""
    return redirect("/insights", code=302)


@app.route("/api/funnel")
def api_funnel():
    return jsonify(funnel_stats())


@app.route("/api/interviews/upcoming")
def api_upcoming_interviews():
    """Booked but not yet held. Never counted toward any rate."""
    return jsonify(upcoming_interviews(
        include_past=request.args.get("include_past") in ("1", "true", "yes")))


@app.route("/api/silence")
def api_silence():
    """Derived on read — no silence verdict is ever stored."""
    return jsonify(job_silence_stats())


@app.route("/api/recruiters")
def api_recruiters():
    """Read-only. Recruiter rows are written by inbox-triage, never by the GUI."""
    return jsonify({
        "recruiters": get_recruiters(),
        "roles": get_recruiter_jobs(),
        "coverage": recruiter_coverage(),
    })


@app.route("/api/interviews")
def api_interviews():
    return jsonify(get_interviews(
        company=(request.args.get("company") or "").strip(),
        date_added=(request.args.get("date_added") or "").strip(),
        position_title=(request.args.get("position_title") or "").strip(),
        link=(request.args.get("link") or "").strip(),
    ))


@app.route("/api/interviews/stats")
def api_interview_stats():
    return jsonify(interview_stats())


@app.route("/api/interviews/add", methods=["POST"])
def api_add_interview():
    payload = request.get_json(force=True)
    company = (payload.get("company") or "").strip()
    date_added = (payload.get("date_added") or "").strip()
    position_title = (payload.get("position_title") or "").strip()
    link = (payload.get("link") or "").strip()
    interview_type = (payload.get("interview_type") or "").strip()
    occurred_date = (payload.get("occurred_date") or "").strip()
    type_label = (payload.get("type_label") or "").strip()
    loop_id = (payload.get("loop_id") or "").strip()
    notes = (payload.get("notes") or "").strip()

    rating = payload.get("self_rating")
    if rating in ("", None):
        rating = None
    else:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "self_rating must be a whole number 1-5"}), 400

    if not company:
        return jsonify({"error": "company is required"}), 400
    if interview_type not in INTERVIEW_TYPES:
        return jsonify({"error": f"interview_type must be one of: {', '.join(INTERVIEW_TYPES)}"}), 400
    if interview_type == "other" and not type_label:
        return jsonify({"error": "type_label is required when interview_type is 'other'"}), 400
    if not occurred_date:
        return jsonify({"error": "occurred_date is required — log rounds that happened"}), 400

    try:
        new_id = add_interview(
            company=company, date_added=date_added, position_title=position_title,
            link=link, interview_type=interview_type, occurred_date=occurred_date,
            type_label=type_label, loop_id=loop_id, self_rating=rating, notes=notes,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"id": new_id})


@app.route("/api/interviews/delete", methods=["POST"])
def api_delete_interview():
    payload = request.get_json(force=True)
    try:
        interview_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "id is required"}), 400
    removed = delete_interview(interview_id)
    if not removed:
        return jsonify({"error": "no interview with that id"}), 404
    return jsonify({"deleted": removed})


@app.route("/api/jobs/delete", methods=["POST"])
def api_delete_job():
    payload = request.get_json(force=True)
    company = payload.get("company")
    date_added = payload.get("date_added")
    position_title = payload.get("position_title")
    row_link = payload.get("link")

    if not company or date_added is None:
        return jsonify({"error": "company and date_added are required"}), 400

    deleted = delete_job_by_key(company, date_added, position_title or "", row_link or "")
    if not deleted:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(port=5151, debug=True)
