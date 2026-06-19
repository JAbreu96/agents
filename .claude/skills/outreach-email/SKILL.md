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
- **mode** — detect from arguments or context: `email` (default) or `linkedin`
  - If the user mentions "LinkedIn", "connection request", "connect note", or "LinkedIn note", set mode to `linkedin`
  - Otherwise default to `email`

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

### Step 1 — Research the company

Before writing, use `WebSearch` to gather 2–3 specific, recent facts about the company:
- A recent product launch, engineering blog post, initiative, or public announcement
- Something about their technical direction, scale challenges, or mission
- If a role was provided, look for signals of what they're actively working on or hiring for

The goal is to open the email with something that proves you actually looked — not generic praise. Aim for a specific detail (a feature, a blog post title, a stated goal) the contact will recognize immediately.

### Step 2 — Compose the email

Write the email in four sections. Keep the total length to ~160 words — punchy, not a wall of text.

#### Greeting
- Always open with: `Hi [first name],`

#### Quick intro (1–2 sentences)
- Open with who you are. **Always lead with Meta.** Use past tense — "recently wrapped up a year at Meta."
- Keep it tight — name, role, and one grounding fact. This is not the place for highlights yet.
- **Do NOT imply you're job hunting or signal urgency about what's next.** The goal is to open a conversation, not signal need.
- Example: "My name is Joelchrist — I'm a software engineer who recently wrapped up a year at Meta."

#### Company hook (1–2 sentences)
- Transition into what you found about the company: reference the specific thing you researched.
- Frame it as genuine interest, not flattery. Example: "I came across [Company]'s work on [specific thing] — [one authentic reaction to it]."

#### Who I am / Value anchor (2–3 sentences)
- Pick the 1–2 Meta highlights most relevant to the company or role:
  - For AI/ML, automation, or data-heavy companies: lead with the AI agent tool (integrated across five production AI agents).
  - For pure product/platform or frontend-focused roles with no AI angle: lead with the GraphQL API + data export work and dashboard adoption metrics.
  - When in doubt, lead with AI — it's the most differentiating work.
- Keep it factual and specific — one metric beats three vague claims.
- Then draw the line to what they need: connect your experience directly to what the company is working on or looking for. Do NOT just restate your resume.
- Example: "Given that you're [expanding X / building Y / dealing with Z], I think the [AI agent work / platform work] I did at Meta maps well to that problem."

#### Call to connect (1–2 sentences)
- Make the ask low-friction and curiosity-driven — ask if they'd be open to a quick chat about the work, not about a job.
- Do NOT frame this as a job search. The ask is to connect and learn, not to get a referral or be considered.
- Close with warmth — no pressure, just genuine interest.
- Always end with this exact signature block:
  ```
  Thanks,
  Joelchrist Abreu
  joelchristabreu4044@gmail.com
  linkedin.com/in/jc-abreu
  ```

**Subject line:** Keep it short and specific. Do NOT mention Meta or any employer in the subject line. Do NOT use "Referral interest —" as a prefix. Use something like "Quick intro — Software Engineer" or "[Role] at [Company]".

### Step 3 — Preview and confirm

Display the full email for review before saving anything:

```
Subject: [subject line]

[full email body]
```

Ask: **"Save as draft?"** — wait for the user to confirm before proceeding.

### Step 4 — Create the Gmail draft

Only after the user confirms. Use `mcp__gmail_personal__draft_email` with:
- `to`: the contact's email address
- `subject`: the subject line from Step 2
- `body`: the plain-text email body from Step 2

### Step 5 — Confirm

Report back:
- Contact name and email the draft was saved to
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
