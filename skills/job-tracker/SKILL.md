---
name: job-tracker
description: Track a job posting — fetch a job URL, extract job details (title, company, location, summary), and log it to the Google Sheets job tracker. Use when the user provides a job posting URL and wants to save it to their tracker.
argument-hint: [job-posting-url]
---

Track the job posting at `$ARGUMENTS` by following these steps:

## Spreadsheet info
- Spreadsheet ID: `1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q`
- Worksheet: `Sheet1`
- Column layout (1-based): A=Job Title, B=Summary, C=Link, D=Date Added, E=Contacts, F=Notes, G=Date Applied

---

## Step 1 — Fetch the job posting

If no URL was given, ask for one before continuing.

**If the URL contains `linkedin.com`:** LinkedIn blocks automated fetching. Ask the user to provide manually:
- Job title
- Company name
- Location
- Job description (full text)

Wait for their response, then skip to Step 2 with that data.

**If the URL matches Greenhouse** (`greenhouse.io/{company}/jobs/{id}`):
Fetch from the Greenhouse API instead of the page:
```
https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}
```
Extract `title`, `location.name`, `updated_at` (date), and `content` (HTML — strip tags for summary). Derive the company name from the URL slug (e.g. `justworks` → `Justworks`).

**If the URL matches Lever** (`jobs.lever.co/{company}/{uuid}`):
Fetch from the Lever API:
```
https://api.lever.co/v0/postings/{company}/{uuid}
```
Extract `text` (title), `categories.location`, `createdAt` (ms timestamp → YYYY-MM-DD), and `descriptionPlain` (or `description` stripped of HTML).

**Otherwise:** Fetch the page using WebFetch. Extract the job description from JSON-LD `application/ld+json` structured data if present (`description`, `hiringOrganization.name`, `jobLocation.address`, `datePosted`). Fall back to `<h1>` for title and main content areas for description.

---

## Step 2 — Extract and refine job details

From the fetched content, extract:
- **Job title** — main heading or page title
- **Company** — from structured data, headings, or URL slug
- **Location** — city/state/remote, or "(unknown location)"
- **Summary** — preserve as much meaningful content as possible from the raw description, organized into these sections (skip any with no content):
  - **Company Context**: what the company does, mission, scale, stage, culture — include specific metrics, customer counts, growth stats, or notable customers if mentioned
  - **Role & Responsibilities**: full list of day-to-day responsibilities — do not condense or merge bullets, keep all specifics
  - **Required Skills & Experience**: all must-have qualifications, full tech stack with versions/frameworks, years of experience, degree requirements
  - **Bonus** (optional): all nice-to-haves, preferred qualifications
  - **Compensation**: salary range, equity details, every listed benefit and perk
  - **What to remove**: legal disclaimers, DEI/EEO boilerplate, E-Verify notices, recruitment fraud warnings, interview process descriptions, and generic filler phrases ("we are an equal opportunity employer", "join our team", etc.)
  - Use bullet points. Preserve specific numbers, names, and technical terms exactly as written.

If the extracted content is too short (under 100 chars), ask the user to paste the job description before continuing.

---

## Step 3 — Research the company

Use WebSearch to find current information on the company. Return a structured notes block with:

**Recent News** (last 12 months): 2–3 bullet points on notable events, launches, or controversies
**Glassdoor**: Overall rating (X/5), 2–3 bullet points on top pros and cons
**Funding**: Latest round — stage, amount, date, lead investors

Omit any section where no reliable data is found. Be factual and concise. End the block with a **Sources** list of URLs used.

---

## Step 4 — Look up contacts via Hunter.io

Determine the domain to search:
- If the URL is from a known job board domain (greenhouse.io, lever.co, ashbyhq.com, gem.com, builtin.com, builtinnyc.com, workday.com, myworkdayjobs.com, icims.com, jobvite.com, smartrecruiters.com, taleo.net, indeed.com, glassdoor.com), search by **company name** instead of domain.
- Otherwise, use the domain from the job URL (strip `www.`).

Fetch (using WebFetch):
```
https://api.hunter.io/v2/domain-search?domain={domain}&api_key=776bd4e0680a27079ab151d0da7cc920d1c06994&limit=10&seniority=senior,executive&department=engineering,executive,management
```
Or if searching by company name:
```
https://api.hunter.io/v2/domain-search?company={company}&api_key=776bd4e0680a27079ab151d0da7cc920d1c06994&limit=10&seniority=senior,executive&department=engineering,executive,management
```

From the response, format up to 5 contacts as:
```
Full Name — Job Title — email@company.com (XX% confidence)
```
One per line. If no contacts are found, leave this field blank.

---

## Step 5 — Check for duplicates and find next empty row

Use the `gsheets` MCP tool to read the full sheet (`Sheet1!A:G`) to:

1. **Check for duplicates** — scan column C for the job URL.
   - **If found at row N**: update columns A–C and E–F at that row. **Never touch column D (Date Added) or G (Date Applied).** Report that the job was updated, not added. Stop here.

2. **Find the next empty row** — scan column A from row 2 downward and find the first row where column A is empty. Call this row N.

---

## Step 6 — Write to the sheet

Use `sheets_update_values` to write to row N (the first empty row found in Step 5):

| A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|
| Job Title | Summary | Link | Today's date (YYYY-MM-DD) | Contacts | Notes | _(leave blank)_ |

Use range `Sheet1!A{N}:G{N}`.

**If no empty row exists within the current range** (the sheet is full): use `sheets_append_values` with `insertDataOption: INSERT_ROWS` to add a new row beyond the current range.

---

## Step 7 — Report result

State:
- Job title and company
- Whether it was **newly added** or **updated** (duplicate URL)
- Row it was written to (if available)
