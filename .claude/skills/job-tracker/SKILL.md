---
name: job-tracker
description: Track a job posting — fetch a job URL, extract job details (title, company, location, summary), and log it to the Google Sheets job tracker. Use when the user provides a job posting URL and wants to save it to their tracker.
argument-hint: [job-posting-url]
---

Track the job posting at `$ARGUMENTS` by following these steps:

## Spreadsheet info
- Spreadsheet ID: `1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q`
- Worksheet: `Sheet1`
- Column layout (1-based): A=Company, B=Job Title, C=Summary, D=Link, E=Date Added, F=Contacts, G=Notes, H=Outreach Date

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
  - Target up to **20,000 characters** — do not truncate content that fits within this limit.

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

## Step 5 — Resume match score

Read the base resume from the Google Docs API, then score it against this job description.

```python
import warnings
warnings.filterwarnings("ignore")

from googleapiclient.discovery import build
from google.oauth2 import service_account

DOC_ID = "1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk"
SERVICE_ACCOUNT_FILE = "/Users/joelchristabreu/Documents/agents-491602-service-account.json"

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/documents.readonly"]
)
docs = build("docs", "v1", credentials=creds)
doc = docs.documents().get(documentId=DOC_ID).execute()

lines = []
for el in doc.get("body", {}).get("content", []):
    if "paragraph" in el:
        text = "".join(
            r.get("textRun", {}).get("content", "")
            for r in el["paragraph"].get("elements", [])
        ).strip()
        if text:
            lines.append(text)

resume_text = "\n".join(lines)
print(resume_text)
```

If the script fails, fall back to `mcp__claude_ai_Google_Drive__read_file_content` with fileId `1WJRx42io40tkv38KS2dO1MharN5T7wh1ZFNDftjCVtk`.

Using the resume text and the job description from Step 2, produce a **lightweight match assessment**:

- **Match Score: X/100** — one sentence rationale
- **Top 3 Gaps** — the 3 most important missing keywords or skills

Format this as a 3-line block that will be prepended to the Notes column:
```
Match Score: X/100 — [one-sentence rationale]
Gaps: [gap1], [gap2], [gap3]

```
(Leave a blank line after the gaps so the research notes from Step 3 are visually separated.)

Save this as `MATCH_BLOCK` — it will be written to column G in Step 8.

### Threshold gate

**If the match score is below 65/100**, stop here and do NOT proceed to Steps 6–9.

Instead, report:

> ⚠️ **Match score too low to track ({score}/100)**
> **{Job Title} — {Company}**
> Gaps: {gap1}, {gap2}, {gap3}
>
> This job fell below the 65/100 tracking threshold. Add it anyway?

Wait for the user to confirm before continuing. If they confirm, proceed to Step 6. If they decline or don't respond, stop.

**Exception — always flag, never auto-skip:**
If a hard location mismatch is detected (role requires relocation to another country, or is international with no remote option), add a 🌍 flag to the report above regardless of score:
> 🌍 **Location note:** This role is based in {city/country} — outside the US or requires relocation.

---

## Step 6 — Check for duplicates and find next empty row

Use the `gsheets` MCP tool to read the full sheet (`Sheet1!A:H`) to:

1. **Check for duplicates** — scan column D for the job URL.
   - **If found at row N**: update columns A–D and F–G at that row. **Never touch column E (Date Added) or H (Outreach Date).** Report that the job was updated, not added. Stop here.

2. **Find the next empty row** — scan column A from row 2 downward and find the first row where column A is empty. Call this row N.

---

## Step 7 — Write to the sheet

Use `sheets_update_values` to write to row N (the first empty row found in Step 6):

| A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|
| Company | Job Title | Summary | Link | Today's date (YYYY-MM-DD) | Contacts | Notes | _(leave blank)_ |

For column G (Notes), combine `MATCH_BLOCK` with the research notes from Step 3:
```
Match Score: X/100 — [rationale]
Gaps: [gap1], [gap2], [gap3]

[Research notes from Step 3]
```

Use range `Sheet1!A{N}:H{N}`.

**If no empty row exists within the current range** (the sheet is full): use `sheets_append_values` with `insertDataOption: INSERT_ROWS` to add a new row beyond the current range.

---

## Step 8 — Set row height

After writing, cap the new row's height to 21px using the Google Sheets API via Python/Bash:

```python
import json, urllib.request
from google.oauth2 import service_account
import google.auth.transport.requests

SERVICE_ACCOUNT_FILE = "/Users/joelchristabreu/Documents/agents-491602-service-account.json"
SPREADSHEET_ID = "1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q"
SHEET_ID = 138342806  # Sheet1
ROW_N = {N}  # replace with the actual 1-based row number written in Step 7

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
creds.refresh(google.auth.transport.requests.Request())

body = {"requests": [{"updateDimensionProperties": {
    "range": {"sheetId": SHEET_ID, "dimension": "ROWS",
              "startIndex": ROW_N - 1, "endIndex": ROW_N},
    "properties": {"pixelSize": 21},
    "fields": "pixelSize"
}}]}

req = urllib.request.Request(
    f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}:batchUpdate",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
    method="POST"
)
urllib.request.urlopen(req)
```

---

## Step 9 — Report result

State:
- Job title and company
- Whether it was **newly added** or **updated** (duplicate URL)
- Row it was written to (if available)
- Match score and top 3 gaps from Step 5
