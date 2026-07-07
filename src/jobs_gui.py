"""
Local web GUI for browsing and editing the jobs.db SQLite cache.

Run:
    python src/jobs_gui.py

Then open http://127.0.0.1:5151 in your browser.
"""

import os
import sqlite3

from flask import Flask, g, jsonify, render_template, request

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")

EDITABLE_COLUMNS = {"status", "notes", "contacts", "outreach_date", "date_applied", "followup_log"}
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
    rows = db.execute("SELECT * FROM jobs ORDER BY date_added DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/jobs/update", methods=["POST"])
def api_update_job():
    payload = request.get_json(force=True)
    company = payload.get("company")
    date_added = payload.get("date_added")
    field = payload.get("field")
    value = payload.get("value", "")

    if not company or date_added is None:
        return jsonify({"error": "company and date_added are required"}), 400
    if field not in EDITABLE_COLUMNS:
        return jsonify({"error": f"field '{field}' is not editable"}), 400

    db = get_db()
    db.execute(
        f"UPDATE jobs SET {field} = ? WHERE company = ? AND date_added = ?",
        (value, company, date_added),
    )
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(port=5151, debug=True)
