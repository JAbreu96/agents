---
name: archive-jobs
description: Archive job tracker entries older than 60 days by moving them to the Archive sheet. Runs on the 1st of every month. Sends a summary email after archiving.
argument-hint: "(no arguments required)"
---

Move jobs older than 60 days from the active job tracker to the Archive sheet, then send a summary email to ajoelcrist@gmail.com.

## User info
- **Email:** ajoelcrist@gmail.com

---

## Step 1 — Archive old jobs

Call `mcp__job_tracker__archive_old_jobs` with default settings (days=60).

The tool will:
- Find all jobs in Sheet1 where Date Added is more than 60 days ago
- Copy them to the Archive sheet
- Delete them from Sheet1
- Return the count and list of archived companies

---

## Step 2 — Send summary email

Use `mcp__gmail_personal__send_email` with:
- `to`: `ajoelcrist@gmail.com`
- `subject`: `Job Tracker — Monthly Archive Complete ([Month Year])`
- `body`: the summary below

```
Hi Joel,

The monthly job tracker cleanup ran on [today's date].

──────────────────────────────
ARCHIVE SUMMARY
──────────────────────────────

Jobs archived: [count]
Threshold: 60 days old

Companies moved to Archive:
[bulleted list of company names, or "None — no jobs met the threshold." if count is 0]

──────────────────────────────

These jobs are still accessible in the Archive tab of the Job Funnel spreadsheet.

Claude
```

---

## Step 3 — Confirm

Report back:
- How many jobs were archived
- Which companies were moved
- Whether the summary email was sent
