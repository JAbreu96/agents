---
name: outreach-email
description: Draft a referral/networking outreach email to a contact at a target company and save it as a Gmail draft. Use when the user provides a contact name, email address, and company — and wants to send a cold outreach or referral request. Lead with Joelchrist's Meta experience.
argument-hint: "[contact_name] [contact_email] [company] [role (optional)] [job_url (optional)]"
---

Draft a personalized outreach email and save it as a Gmail draft using the arguments: `$ARGUMENTS`

Parse the arguments:
- **contact_name** — first argument (or ask if missing)
- **contact_email** — second argument (or ask if missing)
- **company** — third argument (or ask if missing)
- **role** — fourth argument (optional; the specific role being targeted at that company)
- **job_url** — fifth argument (optional; link to the job posting)

## Sender background

**Name:** Joelchrist Abreu  
**Email:** joelchristabreu4044@gmail.com  
**Current/recent role:** Software Engineer at Meta (NYC), Apr 2025 – Apr 2026

**Meta highlights (lead with these):**
- Shipped a full-stack GraphQL API + React widget for on-demand data exports on Meta's Rights Management platform — drove 5,969 report downloads across 393 accounts and 16 report types
- Built an internal AI agent tool that auto-traverses the Asset Data Model graph and returns LLM-friendly structured summaries across copyrights, conflicts, and misuses — integrated across five production AI agents
- Built an interactive asset-relationship graph visualization tool to replace manual ID lookups, improving debuggability for ops and engineers
- Developed a multi-category dashboard component adopted by 545 accounts; resolved production out-of-memory issues via backend query optimization
- Drove cross-functional work via 10+ design docs, stakeholder alignment, and structured feedback loops
- Stack: React, TypeScript, GraphQL, Hack (PHP), Node.js

**Additional background:**
- Razortooth Communications (Apr 2023–Apr 2024): BLE firmware + mobile QA
- Strategio (Apr 2022–Jul 2022): AWS EC2 automation, Docker, CI/CD

---

## Step 1 — Compose the email

Write the email in three sections. Keep the total length to ~150 words — punchy, not a wall of text.

### Intro
- One sentence: who you are and why you're reaching out to this specific person/company.
- If a role was provided, reference it. Otherwise keep it general ("exploring opportunities at [company]").
- Warm but professional — not sycophantic.

### Experience
- 2–3 sentences max. **Always lead with Meta.**
- Pick the 1–2 Meta highlights most relevant to the company or role. For example:
  - For an AI/ML-focused company: lead with the AI agent tool.
  - For a product/platform company: lead with the GraphQL API + data export work and dashboard adoption metrics.
  - If the role or company domain is unclear, default to the GraphQL/data export work (has the strongest concrete numbers).
- End with a brief mention of the stack (React, TypeScript, GraphQL) if it seems relevant.

### Outro
- Tie the Meta experience back to why this company/role is compelling.
- Make the ask clear and low-friction: ask if they'd be open to a quick chat or if they'd be willing to refer you internally.
- If a job_url was provided, include it as a plain line at the end of the email: `Job posting: <url>`
- Close politely — no pressure, just genuine interest.

**Subject line:** Keep it short and specific. Do NOT use "Referral interest —" as a prefix. Use something like "Quick intro — Software Engineer from Meta" or "[Role] at [Company] — Software Engineer from Meta".

---

## Step 2 — Create the Gmail draft

Use `mcp__gmail_personal__draft_email` with:
- `to`: the contact's email address
- `subject`: the subject line from Step 1
- `body`: the plain-text email body from Step 1

---

## Step 3 — Confirm

Report back:
- Contact name and email the draft was sent to
- Subject line used
- A preview of the email body (full text)
- Confirm the draft was saved successfully
