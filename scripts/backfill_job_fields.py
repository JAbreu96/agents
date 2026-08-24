"""
Fills blank job_summary / location on tracker rows that have a real posting URL,
and recovers the roles behind rows that only ever had an email.

Two phases, because they draw on different sources:

  Phase A (default)  -- re-fetch the posting URL. Covers rows the ApplyPass
                        export left blank: the export itself never carried the
                        value (0 of 116 blank locations are recoverable from the
                        archives), so the only place left to read it is the page.

  Phase B (--emails) -- rows created by inbox-triage carry no posting URL. Their
                        link is `email:<gmail-message-id>`, so the source mail is
                        retrievable and usually names the role. Gmail is only
                        reachable over MCP, which a plain script cannot call, so
                        the agent writes the recovered titles to a JSON map and
                        this consumes it.

Writes nothing without --write.

Usage:
    python scripts/backfill_job_fields.py                  # dry run, phase A
    python scripts/backfill_job_fields.py --write
    python scripts/backfill_job_fields.py --emails --write
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.job_agent import JobTrackerAgent  # noqa: E402
from src.jobs_db import (  # noqa: E402
    _connect,
    delete_job_by_key,
    status_rank,
    update_job_fields,
)

# parse_applied_jobs owns the summary shape that 580 rows already use; importing
# it keeps a backfilled summary indistinguishable from an imported one.
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location(
    "paj", os.path.join(os.path.dirname(__file__), "parse_applied_jobs.py"))
_paj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_paj)
_html_to_text = _paj._html_to_text

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOG_DIR = os.path.join(_DATA_DIR, "backfill")
EMAIL_TITLES = os.path.join(LOG_DIR, "email_titles.json")

# Same list jobs_gui.py:163 refuses: these serve a consent wall or a bot check
# rather than the posting, so a "successful" fetch yields banner text.
BLOCKED_DOMAINS = ("linkedin.com", "indeed.com", "glassdoor.com")

# parse_job_page reports failure with a sentinel string rather than "" (see
# src/job_agent.py:48-55). Writing one would replace a blank that reads as
# missing with a value that reads as known -- strictly worse than leaving it.
PLACEHOLDERS = {
    "(unknown location)", "(unknown title)", "(unknown company)", "(unknown date)",
}

# Mirrors merge_updates in parse_applied_jobs.py:188-190. A backfill is a strictly
# weaker operation than an import: it may only fill a blank, never overwrite.
FILL_IF_BLANK = ("job_summary", "location")
NEVER_TOUCH = ("contacts", "notes", "outreach_date", "followup_log", "status")

_LEGAL_SUFFIX = (r"\b(inc|llc|ltd|corp|corporation|co|company|plc|ulc|sa|nv|gmbh"
                 r"|holdings|group|services|technologies|technology|solutions|usa|us)\b")


def blank(value) -> bool:
    return not str(value or "").strip()


def clean(value) -> str:
    """A placeholder is a miss, not a value."""
    text = str(value or "").strip()
    return "" if text in PLACEHOLDERS else text


def norm_company(name: str) -> str:
    """
    'Bandwidth Inc.' and '0001 Applied Materials, Inc' both collapse to their
    plain name. ApplyPass prefixes some employers with a numeric requisition
    code, which is why the leading-digit strip comes first.
    """
    text = str(name or "").lower()
    text = re.sub(r"^\s*\d+\s+", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(_LEGAL_SUFFIX, " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(title or "").lower())).strip()


def load_rows() -> list[dict]:
    return [dict(r) for r in _connect().execute(
        "select * from jobs where archived = 0").fetchall()]


def is_blocked(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(d in host for d in BLOCKED_DOMAINS)


# --- Phase A ----------------------------------------------------------------

def fetch_record(url: str):
    """Board API when we recognise one, otherwise scrape the page."""
    board = JobTrackerAgent.detect_job_board(url)
    if board:
        kind, api_url = board
        if kind == "greenhouse":
            return JobTrackerAgent.fetch_greenhouse_job(api_url, url)
        return JobTrackerAgent.fetch_lever_job(api_url, url)
    # refine=False: no claude CLI per row, and the summary stays raw scraped text
    # so it matches what the ApplyPass import already writes.
    return JobTrackerAgent.parse_job_page(JobTrackerAgent.fetch_page(url), url, refine=False)


def phase_a_targets(rows: list[dict]) -> list[dict]:
    return [r for r in rows
            if str(r.get("link") or "").startswith("http")
            and not is_blocked(r["link"])
            and (blank(r.get("job_summary")) or blank(r.get("location")))]


def backfill_row(row: dict) -> tuple[dict, str]:
    """Returns (updates, error). Only ever proposes values for blank columns."""
    try:
        rec = fetch_record(row["link"])
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"

    proposed = {
        "job_summary": _html_to_text(clean(rec.summary)),
        "location": clean(rec.location),
    }
    updates = {c: proposed[c] for c in FILL_IF_BLANK
               if blank(row.get(c)) and not blank(proposed[c])}
    return updates, ""


# --- Phase B ----------------------------------------------------------------

def applypass_index(rows: list[dict]) -> dict:
    """Live rows that carry a real posting URL, indexed by normalised company."""
    index: dict[str, list[dict]] = {}
    for r in rows:
        if str(r.get("link") or "").startswith("http"):
            index.setdefault(norm_company(r["company"]), []).append(r)
    return index


def plan_email_rows(rows: list[dict], titles: dict) -> dict:
    """
    Sorts each email-created row into one of four outcomes. A row is only ever
    merged when the email and the export independently agree on the exact title;
    a company-only match is a different opening at the same employer as often as
    it is the same one, so it is reported rather than written.
    """
    index = applypass_index(rows)
    out = {"merge": [], "retitle": [], "no_title": [], "no_match": []}

    for row in rows:
        link = str(row.get("link") or "")
        if not link.startswith("email:"):
            continue
        recovered = (titles.get(link.split("email:", 1)[1]) or "").strip()
        if not recovered:
            out["no_title"].append(row)
            continue
        twins = [c for c in index.get(norm_company(row["company"]), [])
                 if norm_title(c["position_title"]) == norm_title(recovered)]
        if len(twins) == 1:
            out["merge"].append((row, twins[0], recovered))
        elif (row.get("position_title") or "").strip() != recovered:
            out["retitle"].append((row, recovered))
        else:
            out["no_match"].append(row)
    return out


def merge_pair(email_row: dict, twin: dict, write: bool) -> list[str]:
    """
    Folds the email row into the posting row and deletes it.

    Only status can move: the email row is what proves an application was
    acknowledged, so a further-along status has to survive. Everything else on
    the email row is blank by construction.

    Safe to delete outright because no interview round is attached to any
    email-created row -- rounds key off the full composite link, and none of
    these rows has one.
    """
    changed = []
    if status_rank(email_row.get("status")) > status_rank(twin.get("status")):
        changed.append(f"status {twin.get('status')!r} -> {email_row.get('status')!r}")
        if write:
            update_job_fields(twin["company"], twin.get("date_added") or "",
                              {"status": email_row["status"]},
                              position_title=twin.get("position_title"),
                              link=twin.get("link"))
    if write:
        delete_job_by_key(email_row["company"], email_row.get("date_added") or "",
                          position_title=email_row.get("position_title"),
                          link=email_row.get("link"))
    changed.append("deleted duplicate email row")
    return changed


# --- reporting --------------------------------------------------------------

def write_log(lines: list[str]) -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(
        LOG_DIR, "backfill_%s.log" % datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S"))
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def run_phase_a(rows, args, log):
    targets = phase_a_targets(rows)
    print(f"Phase A — {len(targets)} row(s) with a fetchable URL and a blank field")
    filled = failed = nothing = 0
    for i, row in enumerate(targets, 1):
        if args.limit and i > args.limit:
            print(f"  (stopping at --limit {args.limit})")
            break
        updates, err = backfill_row(row)
        label = f"{row['company'][:34]} — {str(row.get('position_title'))[:34]}"
        if err:
            failed += 1
            print(f"  FAIL {label}\n       {err}")
            log.append(f"FAIL {label} :: {err}")
        elif not updates:
            nothing += 1
            log.append(f"NONE {label} :: page gave nothing for the blank column(s)")
        else:
            filled += 1
            cols = ", ".join(f"{c}({len(v)})" for c, v in updates.items())
            print(f"  FILL {label}\n       {cols}")
            log.append(f"FILL {label} :: {cols}")
            if args.write:
                update_job_fields(row["company"], row.get("date_added") or "", updates,
                                  position_title=row.get("position_title"),
                                  link=row.get("link"))
        time.sleep(args.delay)
    print(f"\nPhase A: {filled} filled, {nothing} had nothing to give, {failed} failed")
    return filled


def run_phase_b(rows, args, log):
    if not os.path.exists(EMAIL_TITLES):
        print(f"Phase B needs {os.path.relpath(EMAIL_TITLES)} — the agent writes it "
              f"by reading each row's Gmail message. Skipping.")
        return 0
    titles = json.load(open(EMAIL_TITLES))
    plan = plan_email_rows(rows, titles)
    print(f"\nPhase B — {sum(len(v) for v in plan.values())} email-created row(s)")
    print(f"  merge into posting row : {len(plan['merge'])}")
    print(f"  retitle only           : {len(plan['retitle'])}")
    print(f"  no title in the email  : {len(plan['no_title'])}")
    print(f"  title found, no twin   : {len(plan['no_match'])}")

    for row, twin, recovered in plan["merge"]:
        changes = merge_pair(row, twin, args.write)
        print(f"  MERGE {row['company'][:30]} — {recovered[:36]}")
        for c in changes:
            print(f"        {c}")
        log.append(f"MERGE {row['company']} — {recovered} :: {'; '.join(changes)}")

    for row, recovered in plan["retitle"]:
        print(f"  TITLE {row['company'][:30]} — {row.get('position_title')!r} -> {recovered!r}")
        log.append(f"TITLE {row['company']} :: {row.get('position_title')!r} -> {recovered!r}")
        if args.write:
            update_job_fields(row["company"], row.get("date_added") or "",
                              {"position_title": recovered},
                              position_title=row.get("position_title"),
                              link=row.get("link"))

    for row in plan["no_title"]:
        log.append(f"SKIP  {row['company']} :: email never named the role")
    return len(plan["merge"]) + len(plan["retitle"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="apply changes (default is a dry run)")
    ap.add_argument("--emails", action="store_true", help="run Phase B instead of Phase A")
    ap.add_argument("--limit", type=int, default=0, help="stop after N rows (Phase A)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between fetches")
    args = ap.parse_args()

    rows = load_rows()
    print(f"{len(rows)} active row(s) in the tracker\n")
    log: list[str] = [f"backfill {'--write' if args.write else 'DRY RUN'} "
                      f"{datetime.datetime.now().isoformat(timespec='seconds')}"]

    touched = run_phase_b(rows, args, log) if args.emails else run_phase_a(rows, args, log)

    path = write_log(log)
    print(f"\nLog: {os.path.relpath(path)}")
    if not args.write:
        print("Dry run — nothing written. Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
