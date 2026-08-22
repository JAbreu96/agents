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
| `recruiter_outreach` | A staffing/agency recruiter mass-pitching a role Joel never applied to | Tracker row, silent — no task |
| `noise` | Job alerts, marketing, newsletters, Glassdoor/Dice/LinkedIn digests, security codes | Ignore entirely |

**Identifying a human:** a named sender at a company domain, writing prose addressed to Joel, expecting a reply. Not `no-reply@`, `noreply@`, `notifications@`, `donotreply@`, and not an ATS template even when it carries a person's name in the signature. When genuinely unsure, treat as `human_action` — a spurious task costs seconds, a missed interview request costs an opportunity.

**`human_action` vs `recruiter_outreach`.** Both come from a real person, so the split is about whether Joel is already in a process. `human_action` refers to something Joel did — his application, his interview, a question he must answer — and reaching a human is the only way it moves. `recruiter_outreach` pitches a role he never applied to, and is usually blasted to a list.

The mechanical tells of a blast are an unsubscribe link, a tracking pixel, and a body that never references Joel's background. Any one of them, on mail pitching an unsolicited role, makes it `recruiter_outreach`. Record it and stay silent: these arrive most days, are rarely a fit, and a task for each rebuilds the inbox this skill exists to quiet.

Two things override that and make it `human_action` — a reply within a thread Joel started, and any request that names him specifically (an interview time, a document, a question only he can answer).

A rejection sent by a real person is still a `rejection` (silent). It needs no reply.

---

## Step 4 — Update the tracker

For every `rejection` and every status-advancing `human_action`/`deadline`:

1. Extract the company and the role title as quoted in the email.

   **Unescape HTML entities first.** Most of this mail is HTML, so an ampersand
   arrives as `&amp;` and quotes as `&quot;` / `&#39;`. Passing those through
   corrupts the tracker: `add_job` silently creates a row titled
   `Software Verification &amp; QA Specialist`, which then matches nothing and has
   to be repaired by hand. `update_job_status` at least fails loudly. Convert to
   the literal characters before any lookup or write — the stored title must read
   `Systems Integration & Validation Engineer`, never the escaped form.
2. Call `mcp__job_tracker__find_job_for_email` with `company` and `title_hint`.

   **Always pass the title.** Without one, a company with a single row returns
   `exact` for whatever that row happens to be — which is not necessarily the role
   the email is about. An ALTEN rejection for *IT/OT Engineer* resolved `exact`
   onto their *ADAS Performance Engineer* row purely because that was the only row
   filed under the sender's company string.

   If the title returns `none`, try a **shorter company string** before giving up.
   The ATS name and the tracked name often differ: that same IT/OT row was filed
   under `ALTEN SA` while the email said `ALTEN Technology USA`, and searching
   `ALTEN` with the title found it exactly.
3. Act on the result:

| `match` | Action |
|---|---|
| `exact` | `mcp__job_tracker__update_job_status` with the returned `position_title`. Silent. |
| `ambiguous` | **No write.** One task: "Which <company> role does this refer to?" listing candidates. |
| `none` + it is a rejection | **No write.** No task — a rejection for an untracked role needs nothing. |
| `none` + it is human/deadline | `mcp__job_tracker__add_job` to create the row, then proceed. Auto-apply submits roles that never reach the tracker; an interview request for an unknown company is exactly the case worth capturing. |

Status mapping: interview scheduled/requested → `Phone Screen`; rejection → `Rejected`; receipt for an untracked role → `Applied`.

**`recruiter_outreach`** always creates a row rather than updating one, since the role
is by definition untracked: status `Tracking` (Joel has not applied), the recruiter's
name and address in `contacts`, and a note saying it came from inbound outreach. If the
same firm pitches again, add a row for the new role — do not overwrite the old one.

Score the role before deciding whether it is worth Joel's attention, and put
`Match Score: X/100` plus a one-line rationale and the top gaps in the note:

- **Stack** — TypeScript, React, Node.js, GraphQL, JavaScript, Hack/PHP are the core;
  Python, SQL, AWS, Docker, Mongo, Postgres, Java are exposure only.
- **Seniority** — 2-5 years fits. A hard 5+ requirement is a real miss, not a stretch.
- **Shape** — AI and product engineering score high; infra, ML research, embedded and
  data-engineering score low.
- **Location** — NYC or remote preferred; onsite anywhere else is a flag.

**60 or above earns a task**; below that the row is written and nothing is surfaced. This
is what keeps the flood quiet without discarding it: an Alibaba Cloud DevOps or embedded
firmware pitch scores in the teens and stays silent, while a genuinely matched inbound
role still reaches Joel. Anything already tracked is not re-scored.

**Never advance a status on a message you cannot read.** Indeed and some ATS portals
send "you have a new message" with the body behind a login. That is a `human_action`
worth a task, but the row stays where it is: the hidden text may be an interview
request or a rejection, and guessing either way is a silent wrong write.

---

## Step 5 — Create tasks

Only `human_action` and `deadline`. Task list: `My Tasks`.

**A thread only earns a task when the ball is actually in Joel's court.** Conversation
threads — LinkedIn InMail, recruiter email chains — are where spurious tasks come from,
because every new message looks like activity. Three tests, in order:

1. **Who spoke last?** If Joel did, he is waiting on them, not the other way round. No
   task. Chasing a recruiter who owes *him* a reply belongs to the follow-up skills, not
   here.
2. **Did they actually ask for something?** A real ask names a thing only Joel can supply:
   a time, a document, an answer, a decision. *"Let me know which would be your favorite
   one"*, *"could you please share a few times?"*, *"do you want to reschedule?"* and
   *"Have you managed to answer the screening questions"* all qualify.
3. **Is it a closing statement?** Recruiters sign off constantly, and a sign-off is not a
   request. *"Thanks!"*, *"Perfect - thanks!"*, *"Sounds good!"*, *"Okay cool, I will keep
   you updated :)"*, *"Will keep you posted regarding your application"* — the exchange is
   complete and the next move is theirs. No task. The same goes for logistics that have
   already expired (*"I'll be 3 minutes"*) and for bare attachments (*"Job spec"*).

A thread that fails any test is still worth a tracker note if it moved the process — it
just does not interrupt.

**Read for a rejection before making a task to read it.** A thread can go quiet because it
ended badly, and "go and read this" is a wasted errand when the answer is no. Scan the
message body — LinkedIn's `hit-reply@` and `inmail-hit-reply@` notifications carry the full
text — for the usual endings: *not moving forward*, *other candidates*, *decided not to
proceed*, *we've filled the role*, *unfortunately*. If it is a rejection, classify it as
one: set the row to `Rejected` and stay silent. Only when the text genuinely is not
available — Indeed's login-gated messages — does the "cannot read" rule apply, and then the
task must say plainly that the outcome is unknown.

**Check for duplicates first.** Call `mcp__gtasks__list` and skip creation if an existing task already names the same company and refers to the same request. This is what keeps re-runs clean — do not skip it.

Write each task as:

- **Title** — the action and who it concerns: `Reply to <Person> (<Company>) — <what they want>`. Never a bare subject line.
- **Due** — the deadline if one exists; the day before an interview for prep; otherwise tomorrow.
- **Notes** — sender name and address, a verbatim quote of what they asked, any link or portal URL, the tracker status, and whether the company is tracked at all.

The notes are the point: Joel should be able to act without going back to the inbox.

---

## Step 5b — Draft the reply, where a draft is worth having

A task that says "reply to this" still leaves the writing to Joel. Where the reply is
predictable, leave a Gmail draft beside it with `mcp__gmail_personal__draft_email`, and say
in the task notes that a draft is waiting.

Draft only for:

- **`recruiter_outreach` scoring 60 or above** — a cold pitch worth answering.
- **`human_action` where a recruiter asked something answerable from what is already
  known** — availability from the calendar, a role preference, confirmation of interest.

Do **not** draft when the answer is Joel's alone to give: salary expectations, why he left
a job, which of three roles he prefers, anything needing judgement about his own history. A
confident draft of something only he can answer is worse than no draft, because it invites
sending without thinking.

Follow the `outreach-email` skill's format and constraints — that skill owns the voice, and
this one should not grow a second copy of it. Lead with the Meta experience, keep it to
roughly 120-150 words, and never name an employer in a subject line.

Drafts are never sent. Triage does not send email; it leaves work ready for Joel to review.

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
