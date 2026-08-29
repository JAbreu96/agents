"""
Put the LinkedIn recruiters on record, and link the roles they sourced.

The Insights card lists 3 recruiters and reports "4 captured · 9 suspected
uncaptured". All nine of those rows are genuine third-party outreach and every
one already names its recruiter -- in free-text `contacts`, where no query can
reach it. Roughly 35 recruiters have sent InMail; none is in the recruiters
table.

Why none: SKILL.md told triage to key a LinkedIn recruiter on "the profile slug
from their message or profile link", and an InMail body carries no profile slug.
The only LinkedIn URL in one is the messaging thread. The rule was never
followable, so the capture step was never taken and the identity ended up as
prose in `contacts` instead.

Identity here is the normalised sender display name. It identifies the person,
which is what the rest of the schema assumes; the thread id would identify the
conversation, and the same recruiter opening a second thread would become a
second recruiter with one role each -- exactly the number the card exists to
disprove.

**This links rows. It never creates them.** record_recruiter_outreach() is the
wrong tool here: it mints its own synthetic `recruiter:...` link and calls
upsert_job, so using it would leave nine duplicates beside the rows that already
exist. link_recruiter_job() takes the job key explicitly, so it can point at the
row that is already there.

Input is data/backfill/recruiters.json, written by the agent from Gmail: Gmail is
reachable only over MCP, which a script cannot call.

Usage:
    python scripts/backfill_recruiters.py                 # dry run (default)
    python scripts/backfill_recruiters.py --write
"""

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import jobs_db  # noqa: E402

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INPUT_PATH = os.path.join(_DATA_DIR, "backfill", "recruiters.json")
LOG_DIR = os.path.join(_DATA_DIR, "backfill")

# InMail always arrives from the shared relay inmail-hit-reply@linkedin.com, so
# the envelope address identifies LinkedIn rather than the person.
ACCOUNT = "alt"
SOURCE = "linkedin"


def slugify(name: str) -> str:
    """'Manish K.' -> 'manish-k'. The dedup key, so it must be stable."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(name or "").lower())).strip("-")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def match_row(name: str, rows: list[dict]) -> dict | None:
    """
    Find the tracked row this recruiter sourced, by looking for their name in
    `contacts` -- which is where triage wrote it.

    Matching on the name rather than the thread id in the InMail body: the body
    is a second Gmail round trip for every message, and `contacts` already names
    the recruiter on all nine rows. GTE names two people, and both match, which
    is the point -- two agencies pitched that one role.
    """
    needle = _norm(name)
    if not needle:
        return None
    for row in rows:
        if needle and needle in _norm(row.get("contacts")):
            return row
    return None


def load_input() -> list[dict]:
    if not os.path.exists(INPUT_PATH):
        print(f"Missing {os.path.relpath(INPUT_PATH)} — the agent writes it by reading "
              f"the InMail senders out of Gmail.")
        return []
    return json.load(open(INPUT_PATH))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="apply the changes (default is a dry run that writes nothing)")
    args = ap.parse_args()

    messages = load_input()
    if not messages:
        return 1

    # Every job row that looks recruiter-sourced and is linked to nobody. These
    # are the only rows this script will ever touch.
    unlinked = jobs_db.unlinked_recruiter_rows()
    conn = jobs_db._connect()
    contacts = {}
    if conn:
        try:
            for r in conn.execute(
                    "SELECT company, date_added, position_title, link, contacts "
                    "FROM jobs WHERE archived = 0").fetchall():
                row = dict(r)
                contacts[(row["company"], row["date_added"],
                          row["position_title"], row["link"])] = row.get("contacts")
        finally:
            conn.close()
    for row in unlinked:
        row["contacts"] = contacts.get(
            (row["company"], row["date_added"], row["position_title"], row["link"]), "")

    target = "Turso" if jobs_db._use_libsql() else "data/jobs.db"
    print(f"{len(messages)} InMail(s) | {len(unlinked)} unlinked row(s) | target: {target}")
    print()

    # Group by person: the same recruiter sending three InMails is one recruiter
    # with three messages, not three recruiters.
    people: dict[str, dict] = {}
    for msg in messages:
        ident = slugify(msg.get("name"))
        if not ident:
            continue
        person = people.setdefault(ident, {"name": msg.get("name"), "messages": []})
        person["messages"].append(msg)

    log = [f"backfill_recruiters {'--write' if args.write else 'DRY RUN'} "
           f"{datetime.datetime.now().isoformat(timespec='seconds')}",
           f"target: {target}"]
    linked = 0

    jobs_before = len(jobs_db.get_all_jobs(include_archived=True))

    scope = jobs_db.shared_connection(create=True) if args.write else None
    if scope is not None:
        scope.__enter__()
    try:
        for ident, person in sorted(people.items()):
            msgs = sorted(person["messages"], key=lambda m: m.get("date") or "")
            first, last = msgs[0].get("date", ""), msgs[-1].get("date", "")
            row = match_row(person["name"], unlinked)
            mark = f"-> {row['company']}" if row else "(no tracked role)"
            print(f"  {person['name']:<26} {len(msgs)} msg(s)  {first}..{last}  {mark}")
            log.append(f"{ident} | {person['name']} | {len(msgs)} msgs | {mark}")

            if not args.write:
                continue

            rid = jobs_db.upsert_recruiter(source=SOURCE, identity=ident,
                                           name=person["name"], seen_date=last)
            for m in msgs:
                jobs_db.record_recruiter_message(
                    rid, "inbound", m.get("date", ""), subject=m.get("subject", ""),
                    account=ACCOUNT, message_id=m.get("message_id", ""))
            if row:
                jobs_db.link_recruiter_job(
                    rid, company=row["company"], date_added=row["date_added"],
                    position_title=row["position_title"], link=row["link"],
                    sourced_date=first, account=ACCOUNT,
                    message_id=msgs[0].get("message_id", ""))
                linked += 1
    finally:
        if scope is not None:
            scope.__exit__(None, None, None)

    matched = sum(1 for p in people.values() if match_row(p["name"], unlinked))
    print()
    print(f"recruiters: {len(people)} | roles matched: {matched} | linked: {linked}")

    if args.write:
        jobs_after = len(jobs_db.get_all_jobs(include_archived=True))
        # The one check that matters. This script links; if the row count moved,
        # something inserted, and nine duplicates is the failure it exists to
        # avoid.
        print(f"job rows: {jobs_before} -> {jobs_after} "
              f"({'unchanged, as expected' if jobs_after == jobs_before else 'CHANGED — investigate'})")
        cov = jobs_db.recruiter_coverage()
        print(f"coverage: {cov['captured']} captured, "
              f"{cov['suspected_uncaptured']} suspected uncaptured")
        log.append(f"job rows {jobs_before} -> {jobs_after}")
    else:
        print("Dry run — nothing written. Re-run with --write to apply.")

    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, "recruiters_%s.log"
                        % datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S"))
    open(path, "w").write("\n".join(log) + "\n")
    print(f"Log: {os.path.relpath(path)}")
    return 0


if __name__ == "__main__":
    # A backfill exists to change the tracker, so it declares itself.
    # Every one of these defaults to a dry run; the guard is the second lock.
    jobs_db.allow_remote_writes()
    raise SystemExit(main())
