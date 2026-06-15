---
name: outreach-email
description: Draft a referral/networking outreach email (Gmail draft) or LinkedIn connection note for a contact at a target company. Supports two modes: email (default) and linkedin. Lead with Joelchrist's Meta experience.
argument-hint: "[contact_name] [contact_email_or_linkedin] [company] [role (optional)] [job_url (optional)] [mode: email|linkedin (optional, default: email)]"
---

Draft a personalized outreach message and save it as a Gmail draft (or display as a LinkedIn note) using the arguments: `$ARGUMENTS`

Parse the arguments:
- **contact_name** — first argument (or ask if missing)
- **contact_email** — second argument (or ask if missing; for linkedin mode this can be omitted or set to "linkedin")
- **company** — third argument (or ask if missing)
- **role** — fourth argument (optional; the specific role being targeted at that company)
- **job_url** — fifth argument (optional; if not provided, look it up from the job tracker — see Step 0)
- **mode** — detect from arguments or context: `email` (default) or `linkedin`
  - If the user mentions "LinkedIn", "connection request", "connect note", or "LinkedIn note", set mode to `linkedin`
  - Otherwise default to `email`

## Step 0 — Look up job posting URL (if not provided)

If **job_url was not provided**, look it up from the job tracker:

Use `mcp__gsheets__sheets_get_values` with:
- `spreadsheetId`: `1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q`
- `range`: `Sheet1!A:D`

Scan column A for a row where the company name matches (case-insensitive). If a match is found, use the value in column D as `job_url`. If multiple rows match, use the last match (most recent). If no match is found in the sheet, ask the user for the URL before continuing.

**LinkedIn mode exception:** Skip the job URL lookup for linkedin mode — the note is too short to include a URL.

## Sender background

**Name:** Joelchrist Abreu  
**Email:** joelchristabreu4044@gmail.com  
**Current/recent role:** Software Engineer at Meta (NYC), Apr 2025 – Apr 2026 (recently wrapped up)

**Meta highlights (lead with these):**
- Shipped a full-stack GraphQL API + React widget for on-demand data exports on Meta's Rights Management platform — drove 5,969 report downloads across 393 accounts and 16 report types
- Built an internal AI agent tool that auto-traverses the Asset Data Model graph and returns LLM-friendly structured summaries across copyrights, conflicts, and misuses — integrated across five production AI agents
- Built an interactive asset-relationship graph visualization tool to replace manual ID lookups, improving debuggability for ops and engineers
- Developed a multi-category dashboard component adopted by 545 accounts; resolved production out-of-memory issues via backend query optimization
- Drove cross-functional work via 10+ design docs, stakeholder alignment, and structured feedback loops
- Stack: Hack (PHP), React, JavaScript, Flow (Meta's TypeScript-like type system), MySQL

**Additional background:**
- Razortooth Communications (Apr 2023–Apr 2024): BLE firmware + mobile QA
- Strategio (Apr 2022–Jul 2022): AWS EC2 automation, Docker, CI/CD

---

## Mode A — Email

*Use this mode when `mode` is `email` (the default).*

### Step 1 — Compose the email

Write the email in three sections. Keep the total length to ~150 words — punchy, not a wall of text.

#### Intro
- One sentence: who you are and why you're reaching out to this specific person/company.
- If a role was provided, reference it. Otherwise keep it general ("exploring opportunities at [company]").
- Warm but professional — not sycophantic.

#### Experience
- 2–3 sentences max. **Always lead with Meta.** Use past tense — "recently wrapped up a year at Meta" (not "wrapping up").
- Pick the 1–2 Meta highlights most relevant to the company or role. **Default to leading with the AI agent tool** unless the role is clearly non-AI (e.g., pure frontend, media/content platform). For example:
  - For AI/ML, automation, or data-heavy companies: lead with the AI agent tool (integrated across five production AI agents).
  - For pure product/platform or frontend-focused roles with no AI angle: lead with the GraphQL API + data export work and dashboard adoption metrics.
  - When in doubt, lead with AI — it's the most differentiating work.
- End with a brief mention of the stack (Hack/PHP, React, JavaScript, Flow, MySQL) if it seems relevant.

#### Outro
- Tie the Meta experience back to why this company/role is compelling.
- Make the ask clear and low-friction: ask if they'd be open to a quick chat or if they'd be willing to point you to the right person.
- If a job_url was provided, include it as a plain line at the end of the email: `Job posting: <url>`
- Close politely — no pressure, just genuine interest.
- Always end with this exact signature block:
  ```
  Thanks,
  Joelchrist Abreu
  joelchristabreu4044@gmail.com
  linkedin.com/in/jc-abreu
  ```

**Subject line:** Keep it short and specific. Do NOT mention Meta or any employer in the subject line. Do NOT use "Referral interest —" as a prefix. Use something like "Quick intro — Software Engineer" or "[Role] at [Company]".

### Step 2 — Create the Gmail draft

Use `mcp__gmail_personal__draft_email` with:
- `to`: the contact's email address
- `subject`: the subject line from Step 1
- `body`: the plain-text email body from Step 1

### Step 3 — Confirm

Report back:
- Contact name and email the draft was sent to
- Subject line used
- A preview of the email body (full text)
- Confirm the draft was saved successfully

---

## Mode B — LinkedIn

*Use this mode when `mode` is `linkedin`.*

### Step 1 — Compose the LinkedIn connection note

**Hard limit: 300 characters** (LinkedIn's maximum for connection request notes). Count carefully — every character counts including spaces and punctuation.

Write a single short note:
- Open with the contact's first name
- One line on who you are and why you're connecting (reference the company/role if provided)
- One line with the most relevant Meta highlight — compress it to the fewest words possible
- Close with a soft ask: "Would love to connect."
- No signature block, no URLs, no subject line

**Tone:** warm and direct — reads like a real person, not a template.

**After drafting, count the characters.** If over 300, trim until it fits. Display the final character count alongside the note.

### Step 2 — Display the note

Do NOT create a Gmail draft for LinkedIn mode. Instead, output the note in a clearly labeled block so the user can copy and paste it:

```
--- LinkedIn Connection Note (XXX/300 chars) ---
[note text here]
```

### Step 3 — Confirm

Report back:
- Contact name the note is addressed to
- Character count (must be ≤ 300)
- The full note text for copy-paste
