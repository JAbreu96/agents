"""
Local web GUI for browsing and editing the jobs.db SQLite cache.

Run:
    python src/jobs_gui.py

Then open http://127.0.0.1:5151 in your browser.
"""

import io
import os
import sqlite3
import sys
from datetime import date
from urllib.parse import urlparse

from flask import Flask, Response, g, jsonify, render_template, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.job_agent import JobTrackerAgent  # noqa: E402
from src.jobs_db import (  # noqa: E402
    _ensure_schema,
    delete_job_by_key,
    export_csv,
    find_job_by_link,
    upsert_job,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")

EDITABLE_COLUMNS = {
    "company", "status", "notes", "contacts", "job_summary",
    "outreach_date", "date_applied", "followup_log",
}
STATUS_VALUES = [
    "", "Tracking", "Applied", "Phone Screen", "Technical",
    "System Design", "Behavioral", "Offer", "Rejected",
]

app = Flask(__name__)


def get_db():
    if "db" not in g:
        path = os.path.abspath(DB_PATH)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        _ensure_schema(g.db)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.route("/")
def index():
    return render_template("jobs.html", status_values=STATUS_VALUES)


@app.route("/kanban")
def kanban():
    return render_template("kanban.html", status_values=STATUS_VALUES)


@app.route("/api/jobs")
def api_jobs():
    db = get_db()
    rows = db.execute("SELECT * FROM jobs WHERE archived = 0 ORDER BY date_added DESC").fetchall()
    return jsonify([dict(r) for r in rows])


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
    except sqlite3.IntegrityError:
        return jsonify({
            "error": f"A job for '{value}' on {date_added} already exists."
        }), 409

    result = {"ok": True}
    if date_applied_value is not None:
        result["date_applied"] = date_applied_value
    return jsonify(result)


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
