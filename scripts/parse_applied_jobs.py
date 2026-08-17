#!/usr/bin/env python3
"""
Parse an auto-apply service export (records with `_api_c2_*` keys) into rows
shaped for the local job tracker DB (src/jobs_db.COLUMNS).

Paste each export into the inbox file (data/applied_inbox.json), then:

    python scripts/parse_applied_jobs.py                  # preview (dry run)
    python scripts/parse_applied_jobs.py --write --clear   # import, archive, empty the inbox
    python scripts/parse_applied_jobs.py other.json        # or parse any other file
    python scripts/parse_applied_jobs.py --all             # include not-yet-submitted
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.jobs_db import COLUMNS, find_job_by_link, get_all_jobs, upsert_job  # noqa: E402

P = "_api_c2_"
SUMMARY_MAX_CHARS = 2500
STATUS_APPLIED = "Applied"
STATUS_TRACKING = "Tracking"

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
# Scratch file to paste each export into; emptied after a successful --write --clear.
INBOX_PATH = os.path.join(_DATA_DIR, "applied_inbox.json")
ARCHIVE_DIR = os.path.join(_DATA_DIR, "applied_inbox_archive")


def _get(rec: dict, field: str, default=None):
    """Read a field with the `_api_c2_` prefix stripped from the caller's view."""
    return rec.get(P + field, default)


def _iso_to_date(value: str) -> str:
    """'2026-08-16T23:49:34.987Z' -> '2026-08-16' (local date). '' if unparseable."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)[:10]
    if dt.tzinfo:
        dt = dt.astimezone()
    return dt.date().isoformat()


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + " …"
    return text


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v]


def _location(rec: dict) -> str:
    """['California'] + ['On-site'] -> 'California (On-site)'."""
    names = _as_list(_get(rec, "location_name"))
    types = _as_list(_get(rec, "location_type"))
    base = ", ".join(names)
    if types:
        suffix = "/".join(types)
        return f"{base} ({suffix})" if base else suffix
    return base


def _notes(rec: dict) -> str:
    """Provenance + the export's own scoring, so an imported row is recognizable."""
    lines = ["Imported from auto-apply export (auto-submitted application)."]

    score = _get(rec, "match_score_combined")
    if isinstance(score, (int, float)):
        lines.append(f"Match Score: {round(score * 100)}/100 (source-provided, not resume-reviewed)")

    meta = []
    for label, field in (("Seniority", "seniority_level"), ("Board", "job_source")):
        val = _get(rec, field)
        if val:
            meta.append(f"{label}: {val}")
    site = _get(rec, "company_website")
    if site:
        meta.append(f"Website: {site}")
    if meta:
        lines.append(" | ".join(meta))

    if _get(rec, "application_submission_error"):
        lines.append("⚠️ Export flagged a submission error — verify the application went through.")
    if _get(rec, "user_marked_match_bad"):
        lines.append("Marked as a bad match in the source tool.")

    note = (_get(rec, "notes") or "").strip()
    if note:
        lines.append(f"Source notes: {note}")

    ids = [f"match_id={_get(rec, 'match_id')}", f"job_id={_get(rec, 'job_id')}"]
    lines.append("Source IDs: " + ", ".join(i for i in ids if not i.endswith("=None")))
    return "\n".join(lines)


def parse_record(rec: dict) -> dict:
    """Map one export record onto the tracker's column shape."""
    submitted = bool(_get(rec, "application_submitted_bool"))
    applied_date = _iso_to_date(_get(rec, "application_submitted_date", "")) if submitted else ""
    return {
        "company": (_get(rec, "company_name") or "").strip(),
        "position_title": (_get(rec, "job_title") or "").strip(),
        "job_summary": _html_to_text(_get(rec, "job_description") or ""),
        "location": _location(rec),
        "link": (_get(rec, "job_url") or "").strip(),
        "date_added": _iso_to_date(_get(rec, "datetime_matched", "")),
        "contacts": "",
        "notes": _notes(rec),
        "outreach_date": "",
        "date_applied": applied_date,
        "status": STATUS_APPLIED if submitted else STATUS_TRACKING,
        "followup_log": "",
    }


def _skip_reason(rec: dict, include_unsubmitted: bool) -> str | None:
    if not (_get(rec, "company_name") or "").strip():
        return "no company name"
    if _get(rec, "is_invalid"):
        return "flagged invalid by source"
    if not include_unsubmitted and not _get(rec, "application_submitted_bool"):
        return "application not submitted"
    return None


def _norm_link(link: str) -> str:
    return (link or "").strip().rstrip("/").lower()


def parse_export(records: list[dict], include_unsubmitted: bool = False) -> dict:
    """
    Returns {"rows": [...], "skipped": [(company, reason)], "dupes_in_file": [...]}.
    Within-file duplicates keep the most recently applied record.
    """
    rows: dict[str, dict] = {}
    order: list[str] = []
    skipped, dupes = [], []

    for rec in records:
        reason = _skip_reason(rec, include_unsubmitted)
        if reason:
            skipped.append(((_get(rec, "company_name") or "?"), reason))
            continue

        row = parse_record(rec)
        key = _norm_link(row["link"]) or f"{row['company'].lower()}|{row['position_title'].lower()}"
        prev = rows.get(key)
        if prev:
            dupes.append(f"{row['company']} — {row['position_title']}")
            if row["date_applied"] <= prev["date_applied"]:
                continue
        else:
            order.append(key)
        rows[key] = row

    return {"rows": [rows[k] for k in order], "skipped": skipped, "dupes_in_file": dupes}


def split_new_and_existing(rows: list[dict]) -> tuple[list[dict], list[tuple[dict, dict]]]:
    """
    Partition parsed rows against the tracker DB. A link identifies a posting, so
    a row that has one is matched on link alone — a company posting several
    requisitions under one title yields distinct URLs, and falling back to
    company+title there would discard them as false duplicates. Only linkless
    rows fall back to company+title.
    """
    by_pair = {
        (j["company"].strip().lower(), (j.get("position_title") or "").strip().lower()): j
        for j in get_all_jobs(include_archived=True)
    }
    new, existing = [], []
    for row in rows:
        if row["link"]:
            match = find_job_by_link(row["link"])
        else:
            match = by_pair.get((row["company"].lower(), row["position_title"].lower()))
        (existing.append((row, match)) if match else new.append(row))
    return new, existing


def _print_report(result: dict, new: list[dict], existing: list[tuple[dict, dict]]) -> None:
    rows = result["rows"]
    print(f"Parsed {len(rows)} record(s) → {len(new)} new, {len(existing)} already in tracker\n")

    for row in rows:
        dup = next((m for r, m in existing if r is row), None)
        flag = "DUP " if dup else "NEW "
        print(f"{flag}{row['company']} — {row['position_title']}")
        print(f"    applied {row['date_applied'] or '—'} | {row['location'] or 'location n/a'} "
              f"| {row['status']}")
        print(f"    {row['link'] or '(no link)'}")
        if dup:
            print(f"    ↳ matches existing row: {dup['company']} / {dup.get('date_added')} "
                  f"(status: {dup.get('status') or '—'})")
        print()

    if result["dupes_in_file"]:
        print("Duplicates collapsed within the file (kept latest applied):")
        for d in result["dupes_in_file"]:
            print(f"  - {d}")
        print()
    if result["skipped"]:
        print("Skipped records:")
        for company, reason in result["skipped"]:
            print(f"  - {company}: {reason}")
        print()


def archive_and_clear(path: str) -> str:
    """Copy the inbox to a timestamped archive file, then reset it to an empty array."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    dest = os.path.join(ARCHIVE_DIR, f"applied_inbox_{stamp}.json")
    shutil.copy2(path, dest)
    with open(path, "w", encoding="utf-8") as f:
        f.write("[]\n")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json_file", nargs="?", default=INBOX_PATH,
                    help=f"Export JSON to parse (default: {os.path.relpath(INBOX_PATH)})")
    ap.add_argument("--write", action="store_true",
                    help="Upsert parsed rows into data/jobs.db (default is a dry-run preview)")
    ap.add_argument("--all", action="store_true", dest="include_unsubmitted",
                    help="Include records where the application was not submitted")
    ap.add_argument("--include-dupes", action="store_true",
                    help="With --write, also write rows that already exist in the tracker")
    ap.add_argument("--json", dest="json_out", metavar="PATH",
                    help="Write the parsed tracker rows to PATH as JSON")
    ap.add_argument("--clear", action="store_true",
                    help="After a successful --write, archive the input file and empty it")
    args = ap.parse_args()

    if not os.path.exists(args.json_file):
        print(f"No such file: {args.json_file}", file=sys.stderr)
        if args.json_file == INBOX_PATH:
            print("Paste the export into that file first (create it with '[]' if missing).",
                  file=sys.stderr)
        return 1

    with open(args.json_file, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"{args.json_file} is not valid JSON: {e}", file=sys.stderr)
            return 1
    if isinstance(data, dict):
        data = data.get("data") or data.get("results") or data.get("matches") or [data]
    if not isinstance(data, list):
        print("Expected a JSON array of records.", file=sys.stderr)
        return 1

    if not data:
        print(f"{os.path.relpath(args.json_file)} is empty — nothing to parse.")
        return 0

    result = parse_export(data, include_unsubmitted=args.include_unsubmitted)
    new, existing = split_new_and_existing(result["rows"])
    _print_report(result, new, existing)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump([{c: r[c] for c in COLUMNS} for r in result["rows"]], f, indent=2)
        print(f"Wrote {len(result['rows'])} row(s) to {args.json_out}")

    if not args.write:
        print("Dry run — nothing written. Re-run with --write to add these to the tracker.")
        if args.clear:
            print("(--clear only takes effect alongside --write; the input file is untouched.)")
        return 0

    to_write = result["rows"] if args.include_dupes else new
    for row in to_write:
        upsert_job(row)
    print(f"Wrote {len(to_write)} row(s) to data/jobs.db"
          f"{'' if args.include_dupes else f' ({len(existing)} duplicate(s) skipped)'}")

    if args.clear:
        dest = archive_and_clear(args.json_file)
        print(f"Archived input to {os.path.relpath(dest)} and emptied "
              f"{os.path.relpath(args.json_file)} — ready for the next export.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
