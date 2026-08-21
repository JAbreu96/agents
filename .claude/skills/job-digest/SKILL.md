---
name: job-digest
description: Generate a digest of the job tracker — shows all tracked jobs with status (applied/stale/not_applied) and summary stats. Uses the job_tracker MCP server (local DB) to read the tracker directly.
---

Generate a job tracker digest by following these steps:

## Step 1 — Read the tracker

Call `mcp__job_tracker__list_all_jobs` to get every tracked (non-archived) job in compact form (`company`, `title`, `link`, `date_added`, `date_applied`, `status`, `outreach_date`).

## Step 2 — Classify each job

For each job, assign a status using today's date (`$CURRENT_DATE`), based on `date_added`:
- **not_applied** — `date_added` is within the last 14 days
- **stale** — `date_added` is more than 14 days ago

## Step 3 — Compute stats

Calculate:
- `total` — total non-empty rows
- `not_applied` — count with status = not_applied
- `stale` — count with status = stale
- `added_last_7_days` — rows where Date Added is within the last 7 days

## Step 4 — Display the digest

Output a clean, readable digest in this format:

```
## Job Tracker Digest — <today's date>

### Stats
- Total tracked: <total>
- Not yet applied: <not_applied>
- Stale (>14 days): <stale>
- Added in last 7 days: <added_last_7_days>

### Jobs

**[not_applied]** <Position Title> @ <Company>
  Added: <date>
  Link: <url>

**[stale]** <Position Title> @ <Company>
  Added: <date> (X days ago)
  Link: <url>
```

Group jobs by status: not_applied first, then stale. Within each group sort by Date Added descending (newest first).

Do not include the full summary or notes — keep the digest scannable.
