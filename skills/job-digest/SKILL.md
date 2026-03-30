---
name: job-digest
description: Generate a digest of the job tracker Google Sheet — shows all tracked jobs with status (applied/stale/not_applied) and summary stats. Uses the gsheets MCP server to read the sheet directly.
---

Generate a job tracker digest by following these steps:

## Spreadsheet info
- Spreadsheet ID: `1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q`
- Worksheet: `Sheet1`
- Column layout (1-based): A=Job Title, B=Summary, C=Link, D=Date Added, E=Contacts, F=Notes, G=Date Applied

## Step 1 — Read the sheet

Use the `gsheets` MCP tool to read all rows from the spreadsheet. Read the full range (e.g. `Sheet1!A1:G` or equivalent) to get the header and all data rows.

Skip the header row (row 1) and skip any completely empty rows.

## Step 2 — Classify each job

For each row, assign a status using today's date (`$CURRENT_DATE`):
- **applied** — column G (Date Applied) is non-empty
- **stale** — column G is empty AND column D (Date Added) is more than 14 days ago
- **not_applied** — column G is empty AND column D is within the last 14 days

## Step 3 — Compute stats

Calculate:
- `total` — total non-empty rows
- `applied` — count with status = applied
- `not_applied` — count with status = not_applied
- `stale` — count with status = stale
- `added_last_7_days` — rows where Date Added is within the last 7 days
- `applied_last_7_days` — rows where Date Applied is within the last 7 days

## Step 4 — Display the digest

Output a clean, readable digest in this format:

```
## Job Tracker Digest — <today's date>

### Stats
- Total tracked: <total>
- Applied: <applied>
- Not yet applied: <not_applied>
- Stale (>14 days, not applied): <stale>
- Added in last 7 days: <added_last_7_days>
- Applied in last 7 days: <applied_last_7_days>

### Jobs

**[applied]** <Job Title> @ <Company (infer from title if needed)>
  Added: <date> | Applied: <date>
  Link: <url>

**[not_applied]** <Job Title>
  Added: <date>
  Link: <url>

**[stale]** <Job Title>
  Added: <date> (X days ago)
  Link: <url>
```

Group jobs by status: not_applied first, then applied, then stale. Within each group sort by Date Added descending (newest first).

Do not include the full summary or notes — keep the digest scannable.
