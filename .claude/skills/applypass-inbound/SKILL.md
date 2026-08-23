---
name: applypass-inbound
description: Import an auto-apply service export (ApplyPass-style JSON with `_api_c2_*` fields) into the local job tracker DB. Use when the user has pasted an export into the inbox file, says the inbox is ready to parse, or asks to import auto-submitted applications.
---

Import the export sitting in the inbox into the job tracker.

The **inbox** is `data/applied_inbox.json` — a scratch file the user pastes each export into. Everything here runs from the repo root.

---

## Step 1 — Read the inbox

```bash
python -c "
import json; d=json.load(open('data/applied_inbox.json'))
print(f'{len(d)} records, {sum(1 for r in d if r.get(\"_api_c2_application_submitted_bool\"))} submitted')"
```

An empty inbox (`[]`) means the user has not pasted yet — say so and stop. Offer to open it: `code data/applied_inbox.json`.

The inbox has a second source: the **ApplyPass Capture** DevTools panel
(`browser_extension/applypass_capture/`) writes a merged export to `~/Downloads`. If the
user captured with it rather than pasting, move it into place first — the panel prints
this command with the real filename:

```bash
mv ~/Downloads/applied_inbox_<timestamp>.json data/applied_inbox.json
```

Use the filename the panel showed, not a glob: Chrome appends ` (1)` to repeat downloads,
so a glob can pick up a stale file. Everything below is unchanged either way.

---

## Step 2 — Preview

```bash
python scripts/parse_applied_jobs.py
```

Dry run — writes nothing. It prints every row as NEW or DUP, plus within-file duplicates collapsed and records skipped.

Read the output before writing. Report to the user:
- the NEW / DUP counts
- every DUP and what existing row it matched
- every skipped record and why

Records skipped for **no company name** are unrecoverable by the parser — the source itself left `_api_c2_company_name` blank. Surface their job title and URL so the user can decide whether to add them by hand.

---

## Step 3 — Back up the DB

```bash
cp data/jobs.db "data/jobs.db.bak-$(date +%Y%m%d-%H%M%S)"
sqlite3 data/jobs.db "select count(*) from jobs;"
```

Keep that row count — Step 5 checks against it.

---

## Step 4 — Import

```bash
python scripts/parse_applied_jobs.py --write --clear
```

`--write` inserts new rows into `data/jobs.db` and **merges** into rows already there. `--clear` copies the inbox to `data/applied_inbox_archive/applied_inbox_<timestamp>.json`, then resets the inbox to `[]` for the next export.

A merge only ever fills blanks, refreshes `location`, and moves a status *forward*. It never touches `contacts`, `notes`, `outreach_date` or `followup_log`, and never downgrades a status, so re-running the same export is safe. Rows matching an **archived** job are reported and skipped — nothing is resurrected. Every run writes `data/applied_inbox_archive/merge_<timestamp>.log` recording exactly which columns changed.

---

## Step 5 — Verify the row delta

```bash
sqlite3 data/jobs.db "select count(*) from jobs;"
```

**The row count must rise by exactly the number of rows the parser reported as new.** Updated rows must not move it at all — a merge edits a row in place, so a rise larger than the new count means a merge inserted instead of updating, which is the duplicate-row bug this path was built to end. A rise *smaller* than the new count means rows overwrote each other on the primary key `(company, date_added, position_title, link)` and data was silently lost. Either way, find the collisions before reporting success:

```bash
python - <<'EOF'
import json, collections, importlib.util, sys, glob
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("paj", "scripts/parse_applied_jobs.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
archive = max(glob.glob("data/applied_inbox_archive/*.json"))
rows = m.parse_export(json.load(open(archive)))["rows"]
c = collections.Counter(
    (r["company"], r["date_added"], r["position_title"], r["link"]) for r in rows)
for k, v in c.items():
    if v > 1:
        print(f"{v}x  {k}")
EOF
```

Identical keys mean the same posting URL twice — a true duplicate in the source, which collapses correctly. Anything else is a bug in the parser's field mapping — report it rather than papering over it.

To confirm coverage, every row the preview marked `NEW ` should now exist in the DB. Rows marked `UPDT`/`SAME` keep their **original** `date_added`, so they will not match the incoming record's key — that is the merge working, not a miss:

```bash
python - <<'EOF'
import json, sqlite3, importlib.util, sys, glob
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("paj", "scripts/parse_applied_jobs.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
archive = max(glob.glob("data/applied_inbox_archive/*.json"))
rows = m.parse_export(json.load(open(archive)))["rows"]
have = set(sqlite3.connect("data/jobs.db").execute(
    "select company, date_added, position_title, link from jobs"))
groups = m.classify_rows(rows)
for r in groups["new"]:
    if (r["company"], r["date_added"], r["position_title"], r["link"]) not in have:
        print("MISSING:", r["company"], "|", r["position_title"])
EOF
```

---

## Step 6 — Report

State:
- rows imported, and the tracker's before → after count
- rows **updated**, and which columns changed on each (the merge log has this)
- rows matching an archived job, which were skipped
- any ambiguous matches the parser refused to guess at
- records skipped for a blank company, with title and URL
- true duplicate postings that collapsed
- where the backup and the archived export live

---

## Field mapping

`scripts/parse_applied_jobs.py` owns this; it is recorded here only where the choice is not obvious from the code.

| Tracker column | Export field | Note |
|---|---|---|
| `date_added` | `datetime_matched` | when the service matched the job, not when it applied |
| `date_applied` | `application_submitted_date` | |
| `status` | — | `Applied` when submitted, else `Tracking` |
| `job_summary` | `job_description` | HTML stripped to text, capped at 2500 chars |
| `location` | `location_name` + `location_type` | `California (On-site)` |
| `notes` | — | provenance, the export's own match score, seniority, board, source IDs |

The export's `match_score_combined` is the service's number, not a resume review. Notes label it as source-provided so it is never confused with a `/resume-review` score.

Records are dropped when `_api_c2_is_invalid` is set, when `company_name` is blank, or — absent `--all` — when the application was never submitted.

---

## Flags

| Flag | Effect |
|---|---|
| *(none)* | dry-run preview |
| `--write` | upsert new rows into `data/jobs.db` |
| `--clear` | with `--write`: archive the inbox, then empty it |
| `--all` | include records whose application was never submitted (they land as `Tracking`) |
| `--skip-existing` | do not merge into rows already in the tracker; report and ignore them |
| `--json PATH` | dump the parsed tracker rows for inspection |
| `PATH` | parse a file other than the inbox — use the archive path to re-run a past export |
