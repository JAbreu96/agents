---
name: outreach-scanner
description: Scan joelchristabreu4044@gmail.com for incoming recruiter and job outreach emails from the last 24 hours. For each opportunity, either track the job and draft a reply, or flag it for review. Runs daily.
argument-hint: "(no arguments required)"
---

Scan `joelchristabreu4044@gmail.com` for recruiter outreach and job opportunity emails from the last 24 hours, then take action on each one.

## User info
- **Scan inbox:** joelchristabreu4044@gmail.com
- **Summary sent to:** ajoelcrist@gmail.com
- **Spreadsheet ID:** `1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q`
- **Resume Doc ID:** `1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk`

---

## Step 1 — Search Gmail for recruiter/job outreach

Use `mcp__gmail_personal__search_emails` with this query to find relevant emails from the last 24 hours:

```
(subject:(opportunity OR role OR "we're hiring" OR "open role" OR "job opportunity" OR "I came across your profile" OR "your background" OR "reaching out" OR "referral" OR "software engineer" OR "full stack" OR "frontend" OR "engineering role") newer_than:1d) OR (from:(recruiter OR talent OR recruiting OR hiring OR careers OR people) newer_than:1d)
```

For each result, use `mcp__gmail_personal__read_email` to get the full thread content.

---

## Step 2 — Extract details from each email

For each email found, extract:
- **Company name** — from signature, domain, or body
- **Role/title** — the position being discussed or offered
- **Contact name** — the person who sent the email
- **Contact email** — sender's email address
- **Job URL** — any link to a job posting (if present)
- **Type** — classify as one of:
  - `Recruiter Outreach` — cold or warm reach-out about a role
  - `Referral Lead` — someone offering to refer or connect
  - `Application Follow-up` — follow-up on something already applied to
  - `Inbound Interest` — company reaching out after seeing profile/portfolio
  - `Other` — anything else job-related

Skip any email that is clearly spam, a newsletter, or unrelated to a specific job opportunity.

---

## Step 3 — Cross-reference the job tracker

Use `mcp__job_tracker__get_job_by_company` (or `mcp__gsheets__sheets_get_values` with range `Sheet1!A:K`) to check if the company is already tracked.

For each email:
- **If already tracked:** note the current status and whether column I (Outreach Date) is filled
- **If not tracked:** mark as `New`

---

## Step 4 — Score each opportunity against the resume

For each **new** opportunity (not yet tracked), assess fit using Joelchrist's resume:

**Resume summary for scoring:**
- Proficient: TypeScript, React, Node.js, GraphQL, JavaScript, Hack (PHP), Redux, Webpack, MaterialUI
- Exposure: Python, SQL, AWS, Docker, MongoDB, PostgreSQL, Java
- Meta (Apr 2025–Apr 2026): full-stack GraphQL API + React widget; AI agent tooling on SAMI platform; graph visualization; dashboard component with 545-account adoption
- Razortooth (Apr 2023–Apr 2024): BLE firmware (C++/ESP32), mobile QA
- Strategio (Apr 2022–Jul 2022): AWS EC2 automation, Docker, CI/CD

Score each on:
- Stack alignment (TypeScript/React/Node.js roles score higher)
- Role seniority fit (2–5 years experience level)
- AI/product-focused vs. infra/ML-heavy (AI product roles score higher)
- Location fit (NYC or remote preferred; SF in-person is a flag)

Assign **Match Score: X/100** with a one-line rationale and top 3 gaps.

---

## Step 5 — Scan the tracker for stale outreach (2-day follow-up check)

Read the full sheet with `mcp__gsheets__sheets_get_values` using range `Sheet1!A:K`. Scan every row where:
- Column I (Outreach Date) is **filled** (outreach was sent), AND
- Column J (Date Applied) is **blank** (not yet applied), AND
- The outreach date is **2 or more days ago** (compare to today's date)

For each row that matches:
- Note the company (col A), role (col B), contact info (col G), and job link (col E)
- Classify the action needed:
  - **Apply** — if the job link is present and the match score in col H is ≥ 65
  - **More outreach** — if there's a contact in col G but no application yet (draft a follow-up email)
  - **Flag** — if no contact and no job link; include in digest for manual review

This step runs independently of the email scan — it catches opportunities that went quiet after initial outreach.

---

## Step 6 — Decide action for each opportunity

Apply this decision tree across both the email scan (Steps 1–4) and the stale outreach list (Step 5):

### Already tracked + outreach date is blank:
→ **Draft a reply/outreach email** to the contact using the outreach-email skill format. Save as Gmail draft in joelchristabreu4044@gmail.com.

### Already tracked + outreach date filled + applied date filled:
→ **No action needed.** Note it in the digest as "already applied."

### Already tracked + outreach sent 2+ days ago + NOT yet applied:
→ **Two actions:**
1. If a job link exists: draft a follow-up outreach email nudging for a response or referral. Subject: `Following up — [Role] at [Company]`.
2. If the match score is ≥ 65 and a job link exists: note in the digest that Joelchrist should apply directly if no response comes.

### New opportunity + Match Score ≥ 65:
→ **Two actions:**
1. If a job URL is present, add to the job tracker (columns A–H of Sheet1) — company, role, summary from email, location, URL, today's date, contact info, match score + notes.
2. Draft a reply email to the contact. Save as Gmail draft in joelchristabreu4044@gmail.com.

### New opportunity + Match Score < 65:
→ **Flag only.** Include in the digest summary but take no automatic action. Note the score and top gaps so Joelchrist can decide.

---

## Step 7 — Draft reply emails (for all action cases above)

For each email requiring a reply, compose a short outreach/reply using this format (adapted from the outreach-email skill):

**Tone:** warm, specific, not a wall of text. ~120–150 words.

**Structure:**
- **Intro:** Thank them for reaching out / acknowledge the specific role they mentioned.
- **Experience:** 2–3 sentences. Always lead with Meta. Pick highlights most relevant to their company or role:
  - AI/product/platform companies → lead with the AI agent tool (5 SAMI agents, LLM-friendly structured summaries)
  - Frontend/full-stack/data export focus → lead with GraphQL API + 5,969 report downloads / 393 accounts
  - When in doubt, lead with AI
- **Outro:** Express genuine interest and ask for next steps or a quick call. Keep the ask low-friction.
- **Signature:**
  ```
  Thanks,
  Joelchrist Abreu
  joelchristabreu4044@gmail.com
  linkedin.com/in/jc-abreu
  ```

**Subject line:** `Re: [original subject]` (for replies) or a fresh subject for cold follow-ups.

Save each as a draft using `mcp__gmail_personal__draft_email` in joelchristabreu4044@gmail.com.

---

## Step 8 — Send the daily digest

Compose and send a summary email using `mcp__gmail_personal__send_email`:

- **To:** ajoelcrist@gmail.com
- **Subject:** `Outreach Scanner — [Today's Date]`
- **Body:**

```
Subject: Outreach Scanner — [Today's Date]

Hi Joel,

Here's your outreach scan for today.

──────────────────────────────
SUMMARY
──────────────────────────────
Emails scanned: X
New opportunities found: X
Stale outreach (2+ days, not applied): X
Drafts created: X
Jobs added to tracker: X
Flagged (review needed): X

──────────────────────────────
NEW INBOUND — ACTION TAKEN
──────────────────────────────

[For each new email where a draft was created or a job was tracked:]

Company: [Name]
Role: [Title]
Contact: [Name] <[email]>
Match Score: [X/100]
Action: [Draft created / Added to tracker + draft created]
Draft subject: [subject line used]

──────────────────────────────
STALE OUTREACH — FOLLOW-UP NEEDED
──────────────────────────────

[For each tracker row where outreach was sent 2+ days ago and no application logged:]

Company: [Name]
Role: [Title]
Outreach sent: [date] ([N] days ago)
Contact: [from col G, if present]
Action: [Follow-up draft created / Apply now — link below / Flagged for review]
Job link: [col E URL if present]

──────────────────────────────
FLAGGED — REVIEW NEEDED
──────────────────────────────

[For each low-match or ambiguous opportunity:]

Company: [Name]
Role: [Title]
Match Score: [X/100]
Gaps: [gap1], [gap2], [gap3]
Reason flagged: [score too low / no contact info / etc.]

──────────────────────────────

[If nothing found in any section:]
Nothing to act on today — inbox clear, all outreach up to date.
──────────────────────────────

Stay on it,
Claude
```

---

## Step 9 — Confirm

Report back:
- Total emails scanned
- How many opportunities found and categorized
- How many Gmail drafts were created (and for which companies)
- How many jobs were added to the tracker
- How many were flagged for manual review
- Whether the digest was sent successfully
