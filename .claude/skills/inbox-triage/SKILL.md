---
name: inbox-triage
description: Reconcile new Gmail against the job tracker and turn only the things that need a human into Google Tasks. Reads mail since a stored watermark, updates tracked rows, and records interviews and follow-ups. Runs daily on a schedule, or on demand.
argument-hint: "(no arguments required)"
---

Reconcile everything that arrived in Gmail since the last run into the local job tracker, and create Google Tasks **only** for items that need Joel personally.

This is the single scheduled owner of Gmail→tracker reconciliation. It does not send email.

## Operating principles

- **Silence is the default.** Roughly 90% of inbound mail is auto-acknowledgment or rejection. Those update the tracker and are never surfaced as tasks. Joel receives ~40 such emails a day; adding them to a task list recreates the problem this skill exists to solve.
- **Never guess a row.** A wrong silent write is worse than an unanswered question. When an email cannot be tied to exactly one tracked role, ask via a task.
- **Never downgrade a status.** `Phone Screen` outranks `Applied`. Only move a job forward, except for `Rejected`, which may always be set.
- **Idempotent.** Running twice in a row must produce zero new tasks and zero new writes.

---

## Step 1 — Read the watermark

```bash
python3 -c "from src import jobs_db; print(jobs_db.get_meta('inbox_triage.last_seen','0'))"
```

`0` means this has never run. In that case use the last 24 hours rather than all history:

```bash
python3 -c "import time; print(int(time.time()) - 86400)"
```

Capture the current time **before** searching — that becomes the new watermark at the end:

```bash
python3 -c "import time; print(int(time.time()))"
```

---

## Step 2 — Fetch new mail

`mcp__gmail_personal__search_emails` with `after:<watermark>` (Gmail accepts epoch seconds), `maxResults: 100`.

If more than 100 come back, process in batches by narrowing the window — never silently drop the overflow.

Read full bodies with `mcp__gmail_personal__read_email` **only** for messages that Step 3 classifies as anything other than `noise`. Subject and sender are enough to discard noise, and bodies are expensive.

---

## Step 3 — Classify

Assign each message exactly one category.

| Category | Test | Outcome |
|---|---|---|
| `human_action` | A real person wrote and wants something from Joel | Task |
| `deadline` | Something has a clock: assessment expiry, incomplete application, scheduled interview | Task |
| `rejection` | "not moving forward", "other candidates", "regret to inform", "decided not to" | Tracker write, silent |
| `auto_ack` | "Thank you for applying", "we've received your application", Indeed/Workday/Greenhouse receipts | Tracker write if untracked, else nothing |
| `noise` | Job alerts, marketing, newsletters, Glassdoor/Dice/LinkedIn digests, security codes | Ignore entirely |

**Identifying a human:** a named sender at a company domain, writing prose addressed to Joel, expecting a reply. Not `no-reply@`, `noreply@`, `notifications@`, `donotreply@`, and not an ATS template even when it carries a person's name in the signature. When genuinely unsure, treat as `human_action` — a spurious task costs seconds, a missed interview request costs an opportunity.

A rejection sent by a real person is still a `rejection` (silent). It needs no reply.

---

## Step 4 — Update the tracker

For every `rejection` and every status-advancing `human_action`/`deadline`:

1. Extract the company and the role title as quoted in the email.
2. Call `mcp__job_tracker__find_job_for_email` with `company` and `title_hint`.
3. Act on the result:

| `match` | Action |
|---|---|
| `exact` | `mcp__job_tracker__update_job_status` with the returned `position_title`. Silent. |
| `ambiguous` | **No write.** One task: "Which <company> role does this refer to?" listing candidates. |
| `none` + it is a rejection | **No write.** No task — a rejection for an untracked role needs nothing. |
| `none` + it is human/deadline | `mcp__job_tracker__add_job` to create the row, then proceed. Auto-apply submits roles that never reach the tracker; an interview request for an unknown company is exactly the case worth capturing. |

Status mapping: interview scheduled/requested → `Phone Screen`; rejection → `Rejected`; receipt for an untracked role → `Applied`.

---

## Step 5 — Create tasks

Only `human_action` and `deadline`. Task list: `My Tasks`.

**Check for duplicates first.** Call `mcp__gtasks__list` and skip creation if an existing task already names the same company and refers to the same request. This is what keeps re-runs clean — do not skip it.

Write each task as:

- **Title** — the action and who it concerns: `Reply to <Person> (<Company>) — <what they want>`. Never a bare subject line.
- **Due** — the deadline if one exists; the day before an interview for prep; otherwise tomorrow.
- **Notes** — sender name and address, a verbatim quote of what they asked, any link or portal URL, the tracker status, and whether the company is tracked at all.

The notes are the point: Joel should be able to act without going back to the inbox.

---

## Step 6 — Record what happened

- **An interview occurred** (a screen took place, a thank-you or outcome references it): `jobs_db.add_interview` with `occurred_date`. Only rounds that actually happened — never a scheduled-but-not-yet-held invite, and never a cancelled one. This table feeds the funnel stats and cannot be rebuilt from anywhere else.
- **A row was acted on**: `jobs_db.update_followup_log` with today's date, so "have I dealt with this" stops being invisible.

---

## Step 7 — Advance the watermark

Only after Steps 4–6 succeeded:

```bash
python3 -c "from src import jobs_db; jobs_db.set_meta('inbox_triage.last_seen','<captured_time>')"
```

If anything failed, leave the watermark alone — the next run reprocesses, and Step 5's duplicate check makes that safe.

---

## Step 8 — Report

Print a short summary to stdout (the log). Do **not** send email:

```
inbox-triage <date>: <N> messages since <watermark>.
  human: <n>  deadline: <n>  rejection: <n>  auto_ack: <n>  noise: <n>
  tracker: <n> updated, <n> created, <n> ambiguous (asked)
  tasks: <n> created, <n> skipped as duplicates
  interviews recorded: <n>
```
