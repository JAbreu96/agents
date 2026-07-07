---
name: source-jobs
description: Run Google X-ray searches across Ashby, Greenhouse, Lever, and Notion to find job postings, fetch each one, score them against the resume, and return a ranked list for review. Does NOT auto-track — user decides which jobs to send to /job-tracker.
argument-hint: "[role keywords] [location (optional)]"
---

Find and score job postings using Google X-ray search. Arguments: `$ARGUMENTS`

Parse the arguments:
- **role** — what to search for (e.g. "software engineer AI React", "frontend engineer TypeScript")
- **location** — optional filter (e.g. "New York", "remote", "San Francisco"). If omitted, search broadly.

## Candidate profile (for scoring)
- **Name:** Joelchrist Abreu
- **Stack:** React, TypeScript, JavaScript, GraphQL, Node.js, Python (exposure), Claude/LLMs, HTML/CSS, Tailwind, Jest
- **Experience:** ~2 years total (1 year at Meta + prior SWE roles); targets roles asking for 1–3 years
- **Strengths:** AI agent work, frontend/full-stack, cross-functional shipping
- **Location:** New York, NY

### Experience-level scoring rules
Apply these adjustments **before** finalizing any match score:

- **Ideal range:** roles asking for 0–3 years → no penalty
- **Slight stretch:** roles asking for 3–5 years → subtract 8 points and note "experience stretch"
- **Too senior:** roles explicitly titled Senior, Staff, Principal, Lead, or requiring 5+ years → subtract 15 points and flag `⚠️ senior role`
- **New grad / intern:** roles requiring current enrollment in a degree program → subtract 20 points and flag `⚠️ eligibility concern`

Do NOT filter out senior roles entirely — just score them honestly so the user can decide.

---

## Step 1 — Read the resume

Use `mcp__claude_ai_Google_Drive__read_file_content` with fileId `1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk` to get the full resume text.

Save this as `RESUME_TEXT` — used for scoring all jobs in Step 4.

---

## Step 2 — Run X-ray searches

Run the following searches using `WebSearch`. Construct the query from the parsed role and location arguments.

Run all four in parallel:

**Greenhouse:**
```
site:boards.greenhouse.io "{role}" {location}
```

**Ashby:**
```
site:jobs.ashbyhq.com "{role}" {location}
```

**Lever:**
```
site:jobs.lever.co "{role}" {location}
```

**Notion:**
```
site:notion.so "we're hiring" "{role}" {location}
```

From each search result, collect all URLs that match the ATS pattern:
- Greenhouse: `boards.greenhouse.io/{company}/jobs/{id}`
- Ashby: `jobs.ashbyhq.com/{company}/{uuid}`
- Lever: `jobs.lever.co/{company}/{uuid}`
- Notion: any notion.so URL with job content

Deduplicate across all four searches. Aim for up to **10 unique job URLs** total. Prioritize results where the URL + title snippet look most relevant to the role searched.

---

## Step 3 — Fetch each job description

For each URL collected, fetch the job description using the appropriate method:

**Greenhouse** (`boards.greenhouse.io/{company}/jobs/{id}`):
Call the Greenhouse API:
```
https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}
```
Extract: `title`, `location.name`, `content` (strip HTML tags).

**Lever** (`jobs.lever.co/{company}/{uuid}`):
Call the Lever API:
```
https://api.lever.co/v0/postings/{company}/{uuid}
```
Extract: `text` (title), `categories.location`, `descriptionPlain`.

**Ashby** (`jobs.ashbyhq.com/{company}/{uuid}`):
Use Playwright:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("{URL}", wait_until="networkidle", timeout=15000)
    try:
        page.wait_for_selector("h1", timeout=8000)
    except:
        pass
    text = page.inner_text("body")
    browser.close()
print(text)
```

**Notion:**
Use `WebFetch`. If it fails or returns fewer than 200 characters, skip this URL.

**If a fetch fails or returns under 100 characters of content:** skip that URL and note it in the final report as "could not fetch."

Derive the company name from the URL slug for each posting.

---

## Step 4 — Score each job against the resume

For each successfully fetched job, produce a **lightweight match assessment** using `RESUME_TEXT` from Step 1:

- **Match Score: X/100** — one sentence rationale
- **Top 3 Gaps** — the 3 most important missing skills or keywords

Keep scoring fast and consistent — this is a triage pass, not a deep analysis.

**Location flag:** If the role is in-person outside New York (e.g. SF, LA, Chicago) with no remote option, add `⚠️ relocation` to the result.

---

## Step 5 — Present ranked results

Sort all scored jobs by match score (highest first). Present as a clean digest:

```
SOURCE JOBS — "{role}" [{location}] — {Today's Date}
──────────────────────────────────────────────────────
Found {N} jobs across Greenhouse / Ashby / Lever / Notion.
Ranked by match score. Run /job-tracker {url} to track any of these.

 #  Score  Company                 Title                          Location
────────────────────────────────────────────────────────────────────────────
 1   88    Vercel                  Software Engineer (AI)         Remote
           Gaps: Go, infra-at-scale, SRE
           https://jobs.ashbyhq.com/vercel/...

 2   81    Letta                   AI Engineer                    SF ⚠️ relocation
           Gaps: LangChain, Python-primary, memory systems
           https://boards.greenhouse.io/letta/...

 3   76    Linear                  Frontend Engineer              Remote
           Gaps: Electron, desktop app experience, Rust
           https://jobs.lever.co/linear/...
...

──────────────────────────────────────────────────────
SKIPPED (could not fetch): {N} URLs
Run /job-tracker {url} on any job above to research, score fully, and add to your tracker.
```

If fewer than 3 jobs were found or scored, note that and suggest refining the search terms.
