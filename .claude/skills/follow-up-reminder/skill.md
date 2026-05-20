---
name: follow-up-reminder
description: Scan the job tracker for applications with no status progression in 7+ days and send a follow-up nudge email. Run on a schedule or on-demand.
argument-hint: "[days=7]"
---

Scan the job tracker for stale applications and send a follow-up reminder email to ajoelcrist@gmail.com.

## User info
- **Email:** ajoelcrist@gmail.com

---

## Step 1 — Find jobs needing follow-up

Call `mcp__job_tracker__list_jobs_needing_followup` with `days=7` (or the value passed as an argument).

This returns jobs where:
- `date_applied` is set
- `status` is still `Applied` (no progression)
- `date_applied` was more than `days` days ago

---

## Step 2 — Check outreach date for context

For each job returned, note whether `outreach_date` is set. If outreach was sent, include that date in the email row so you know a contact was already reached.

---

## Step 3 — Compose the reminder email

```
Subject: Follow-Up Reminder — [X] Applications Need Attention ([Today's Date])

Hi Joel,

You have [X] application(s) with no status update in the last [days] days.

──────────────────────────────
APPLICATIONS NEEDING FOLLOW-UP
──────────────────────────────

[For each job, one line:]
• [Company] — [Title] | Applied: [date_applied] ([N] days ago) | Outreach: [outreach_date or "None"]

──────────────────────────────

Consider sending a follow-up note to your contact or checking the company's applicant portal.

[If no jobs found:]
No stale applications found — you're all caught up.
──────────────────────────────

Claude
```

---

## Step 4 — Send the email

Use `mcp__gmail_personal__send_email` with:
- `to`: `ajoelcrist@gmail.com`
- `subject`: `Follow-Up Reminder — [X] Applications Need Attention ([Today's Date])`
- `body`: the email from Step 3

Skip sending if no stale jobs were found — just report back that everything is current.

---

## Step 5 — Confirm

Report back:
- How many stale applications were found
- Which companies were listed
- Whether the reminder email was sent
