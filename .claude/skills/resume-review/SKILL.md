---
name: resume-review
description: Analyze a resume against a job description like a senior recruiter. Gives a match score, top missing keywords, red flags, rewrites the experience section using the Google XYZ formula, then runs an ATS + hiring manager scan. Use when the user provides a job URL or pastes a job description.
argument-hint: "[job_url or company_name (optional)]"
---

Analyze Joelchrist's resume against a job description using the arguments: `$ARGUMENTS`

## Resume

Joelchrist Abreu — Software Engineer
joelchristabreu4044@gmail.com | linkedin.com/in/jc-abreu

**Experience**

Meta — Software Engineer (NYC) | Apr 2025 – Apr 2026
- Shipped a full-stack GraphQL API + React widget for on-demand data exports on Meta's Rights Management platform — drove 5,969 report downloads across 393 accounts and 16 report types
- Built an internal AI agent tool that auto-traverses the Asset Data Model graph and returns LLM-friendly structured summaries across copyrights, conflicts, and misuses — integrated across five production AI agents
- Built an interactive asset-relationship graph visualization tool to replace manual ID lookups, improving debuggability for ops and engineers
- Developed a multi-category dashboard component adopted by 545 accounts; resolved production out-of-memory issues via backend query optimization
- Drove cross-functional work via 10+ design docs, stakeholder alignment, and structured feedback loops
- Stack: React, TypeScript, GraphQL, Hack (PHP), Node.js

Razortooth Communications — Software Engineer | Apr 2023 – Apr 2024
- Developed BLE firmware and mobile QA tooling
- Improved Bluetooth connectivity reliability across iOS and Android

Strategio — Software Engineer | Apr 2022 – Jul 2022
- Automated AWS EC2 provisioning workflows; worked with Docker and CI/CD pipelines

**Education**
BS Computer Science

---

## Step 1 — Get the job description

If a job_url was provided:
- If it's a Greenhouse URL (`greenhouse.io/{company}/jobs/{id}`): fetch `https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}` and extract the `content` field (strip HTML).
- If it's a Lever URL (`jobs.lever.co/{company}/{uuid}`): fetch `https://api.lever.co/v0/postings/{company}/{uuid}` and extract `descriptionPlain`.
- If it's a LinkedIn URL or any URL that fails to fetch: ask the user to paste the job description.
- Otherwise: use WebFetch to retrieve the page content.

If no URL was provided and no description is available: ask the user to paste the job description before continuing.

---

## Step 2 — Recruiter analysis (match score + gaps)

Act as a **senior recruiter** for the exact company and role.

Analyze the resume against the job description and return:

**Match Score: X/100**

Brief 1–2 sentence rationale for the score.

**Top 5 Missing Keywords**
List the 5 most important keywords or skills from the job description that are absent or weak in the resume. For each, note where it could naturally be added.

**3 Red Flags a Hiring Manager Would Spot in Under 10 Seconds**
Be blunt. What would make a recruiter pause or skip this resume for this specific role?

---

## Step 3 — Rewrite the experience section

Rewrite Joelchrist's experience section to:
- Naturally incorporate the missing keywords from Step 2 where they genuinely apply — don't force keywords that don't fit
- Address the red flags identified in Step 2
- Apply the **Google XYZ formula** to every bullet: _Accomplished X as measured by Y by doing Z_
- Keep all existing metrics (5,969 downloads, 393 accounts, 545 accounts, 5 production agents, etc.)
- Maintain the same company names, titles, and date ranges
- Do not invent experience or fabricate metrics

Return the full rewritten experience section, formatted cleanly.

---

## Step 4 — ATS + hiring manager scan

Now act as both:
1. An **ATS filter** scanning for keyword density and formatting issues
2. A **hiring manager** reading 200 resumes in one sitting

Using the rewritten experience section from Step 3:

**Sections That Would Get Skipped**
List any bullets or sections that are weak, vague, or would get skimmed past — and why.

**Rewrites to Stop the Scroll**
For each flagged section, provide a sharper version that earns attention. Lead with impact, be specific, cut filler.

---

## Step 5 — Final summary

Wrap up with:
- Revised match score after the rewrites (X/100)
- 2–3 sentences on the strongest angle to emphasize when applying to this specific role
