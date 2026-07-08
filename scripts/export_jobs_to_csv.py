"""
Exports the local SQLite job tracker (data/jobs.db) to a CSV file.

Usage:
    python scripts/export_jobs_to_csv.py [output_path]

Defaults to data/jobs_export.csv if no output path is given.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.jobs_db import get_all_jobs

COLUMNS = [
    "company", "position_title", "job_summary", "location", "link",
    "date_added", "contacts", "notes", "outreach_date", "date_applied",
    "status", "followup_log"
]

DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "data", "jobs_export.csv")


def export(output_path: str = DEFAULT_OUTPUT):
    jobs = get_all_jobs()

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for job in jobs:
            writer.writerow(job)

    print(f"Exported {len(jobs)} rows to {output_path}")


if __name__ == "__main__":
    output_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUTPUT
    export(output_path)
