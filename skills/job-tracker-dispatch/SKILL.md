---
name: job-tracker-dispatch
description: Track a job posting — fetch a job URL, extract job details (title, company, location, summary), research the company, look up contacts via Hunter.io, and log it to the Google Sheets job tracker using the Claude-in-Chrome extension. Use when the user provides a job posting URL and wants to save it to their tracker. Does NOT require a Google Sheets MCP connector — uses the browser directly.
argument-hint: [job-posting-url]
---

Track the job posting at `$ARGUMENTS` by following this tight 7-step playbook.

> **Requirements:** `mcp__Claude_in_Chrome__*` tools available, Chrome open, `mcp__workspace__bash` available for curl. All tools are assumed available — no discovery steps needed.

## Spreadsheet
- **ID:** `1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q`
- **URL:** `https://docs.google.com/spreadsheets/d/1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q/edit#gid=0`
- **Columns (A–G):** Company | Job Title | Job Summary | Link | Date Added | Contacts | Notes

---

## Step 1 — Fetch the job posting

If no URL was given, ask for one before continuing.

**LinkedIn URLs:** Automated fetching is blocked. Ask the user to provide the job title, company, location, and full job description manually. Skip to Step 2 with that data.

**Greenhouse** (`greenhouse.io/{company}/jobs/{id}`): fetch via bash API:
```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}" | python3 -c "
import sys, json, re
d = json.load(sys.stdin)
print('Title:', d.get('title'))
print('Location:', d.get('location', {}).get('name'))
print('Updated:', d.get('updated_at', '')[:10])
print('Description:', re.sub('<[^>]+>', '', d.get('content', '')))
"
```
Derive company name from the URL slug (e.g. `justworks` → `Justworks`).

**Lever** (`jobs.lever.co/{company}/{uuid}`): fetch via bash API:
```bash
curl -s "https://api.lever.co/v0/postings/{company}/{uuid}" | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin)
print('Title:', d.get('text'))
print('Location:', d.get('categories', {}).get('location'))
print('Date:', datetime.datetime.fromtimestamp(d.get('createdAt',0)/1000).strftime('%Y-%m-%d'))
print('Description:', d.get('descriptionPlain') or d.get('description', ''))
"
```

**All other URLs:** Fetch with `mcp__Claude_in_Chrome__get_page_text` (navigate first if needed). Extract from JSON-LD `application/ld+json` structured data (`description`, `hiringOrganization.name`, `jobLocation.address`, `datePosted`). Fall back to `<h1>` and main content.

If extracted content is under 100 chars, ask the user to paste the job description.

---

## Step 2 — Extract job details

From the fetched content, produce these exact fields:

- **Company** — from structured data, headings, or URL slug
- **Job Title** — main heading or page title
- **Location** — city/state/remote, or "(unknown location)"
- **Summary** — organized sections (skip sections with no content):
  - **Company Context**: mission, scale, stage, culture; specific metrics, customer counts, growth stats
  - **Role & Responsibilities**: full bullet list of day-to-day duties — do not condense or merge
  - **Required Skills & Experience**: must-have qualifications, full tech stack with versions/frameworks, years of experience, degree requirements
  - **Bonus** *(optional)*: nice-to-haves, preferred qualifications
  - **Compensation**: salary range, equity, every listed benefit and perk
  - Remove: legal disclaimers, DEI/EEO boilerplate, E-Verify notices, recruitment fraud warnings, interview process info, generic filler
  - Use bullet points. Preserve numbers, names, and technical terms exactly.
  - Target up to **20,000 characters** — do not truncate content that fits.

---

## Step 3 — Research the company (max 2 searches)

Run exactly **2 WebSearch calls** — no more:

1. **Search 1:** `"{Company}" company overview funding stage` — capture what the company does, funding stage/amount, investors, founding year, headcount.
2. **Search 2:** `"{Company}" news 2024 2025 OR Glassdoor reviews` — capture recent news/launches/controversies and Glassdoor rating + top pros/cons.

Produce a structured **Notes** block:
```
Recent News: [2–3 bullets on notable events, launches, or controversies in last 12 months]
Glassdoor: [X/5 rating] — [2–3 bullets on top pros and cons]
Funding: [Stage, amount, date, lead investors]
Sources: [URL1], [URL2]
```
Omit any section where no reliable data was found.

---

## Step 4 — Look up contacts via Hunter.io

**Domain selection rule:** If the job URL is from a known job board (greenhouse.io, lever.co, ashbyhq.com, gem.com, builtin.com, builtinnyc.com, workday.com, myworkdayjobs.com, icims.com, jobvite.com, smartrecruiters.com, taleo.net, indeed.com, glassdoor.com), search by company name. Otherwise, use the domain from the job URL (strip `www.`).

```bash
# By domain:
curl -s "https://api.hunter.io/v2/domain-search?domain={DOMAIN}&api_key=$HUNTER_API_KEY&limit=10&seniority=senior,executive&department=engineering,executive,management" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for e in d.get('data', {}).get('emails', [])[:5]:
    print(f\"{e.get('first_name','')} {e.get('last_name','')}\".strip(), '—', e.get('position','Unknown'), '—', e.get('value',''), f\"({e.get('confidence','?')}% confidence)\")
"

# By company name (job board URLs):
curl -s "https://api.hunter.io/v2/domain-search?company={COMPANY_NAME}&api_key=$HUNTER_API_KEY&limit=10&seniority=senior,executive&department=engineering,executive,management" | python3 -c "..."
```

Format up to 5 contacts as `Full Name — Job Title — email@company.com (XX% confidence)`, one per line. Leave blank if no contacts found.

---

## Step 5 — Duplicate check + find target row (1 JS call)

Navigate to the sheet, then run a single JavaScript call to read column D and determine the target row:

```javascript
// mcp__Claude_in_Chrome__javascript_tool
(async () => {
  const token = gapi.auth.getToken().access_token;
  const id = '1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q';
  const jobUrl = 'JOB_URL_HERE'; // ← substitute actual URL
  const r = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${id}/values/Sheet1!D:D`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const d = await r.json();
  const rows = d.values || [];
  const existingIdx = rows.findIndex(row => row[0] === jobUrl);
  return {
    existingRow: existingIdx >= 0 ? existingIdx + 1 : null,  // 1-based row if duplicate found
    nextEmpty: rows.length + 1                                 // next empty row if adding new
  };
})()
```

- If `existingRow` is not null → **update mode**: write to that row (skip columns D and E).
- If `existingRow` is null → **add mode**: write to `nextEmpty`.

> If `gapi.auth.getToken()` throws, the Sheets page may not be loaded. Navigate to the sheet URL first, wait ~3s, then retry.

---

## Step 6 — Write all 7 columns (1 JS call)

With the target row determined, write all fields in a single fetch call:

```javascript
// mcp__Claude_in_Chrome__javascript_tool
(async () => {
  const token = gapi.auth.getToken().access_token;
  const id = '1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q';
  const row = TARGET_ROW; // ← substitute row number from Step 5

  // Substitute all values below — use \n for newlines within cells
  const company   = 'COMPANY';
  const title     = 'JOB_TITLE';
  const summary   = 'JOB_SUMMARY';  // multi-line ok: use \n
  const link      = 'JOB_URL';
  const dateAdded = 'YYYY-MM-DD';   // today's date
  const contacts  = 'CONTACTS';     // multi-line ok: use \n
  const notes     = 'NOTES';        // multi-line ok: use \n

  const range = `Sheet1!A${row}:G${row}`;
  const resp = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${id}/values/${encodeURIComponent(range)}?valueInputOption=RAW`,
    {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        range,
        majorDimension: 'ROWS',
        values: [[company, title, summary, link, dateAdded, contacts, notes]]
      })
    }
  );
  return await resp.json();
})()
```

**Update mode only:** To avoid overwriting the original Link and Date Added, use a BATCH_UPDATE instead — write A–C and F–G as separate ranges, skipping D and E:

```javascript
// mcp__Claude_in_Chrome__javascript_tool  — UPDATE MODE
(async () => {
  const token = gapi.auth.getToken().access_token;
  const id = '1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q';
  const row = EXISTING_ROW; // ← row number from Step 5

  const company = 'COMPANY';
  const title   = 'JOB_TITLE';
  const summary = 'JOB_SUMMARY';
  const contacts = 'CONTACTS';
  const notes   = 'NOTES';

  const resp = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${id}/values:batchUpdate`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        valueInputOption: 'RAW',
        data: [
          { range: `Sheet1!A${row}:C${row}`, majorDimension: 'ROWS', values: [[company, title, summary]] },
          { range: `Sheet1!F${row}:G${row}`, majorDimension: 'ROWS', values: [[contacts, notes]] }
        ]
      })
    }
  );
  return await resp.json();
})()
```

A successful response contains `"updatedRows": 1` (or `"totalUpdatedRows": 1` for batchUpdate). If you see an `"error"` key, check that the token is valid and the range is correct.

---

## Step 7 — Verify (1 JS call)

Read the row back to confirm the write:

```javascript
// mcp__Claude_in_Chrome__javascript_tool
(async () => {
  const token = gapi.auth.getToken().access_token;
  const id = '1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q';
  const row = TARGET_ROW; // ← same row used in Step 6
  const r = await fetch(
    `https://sheets.googleapis.com/v4/spreadsheets/${id}/values/${encodeURIComponent(`Sheet1!A${row}:G${row}`)}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const d = await r.json();
  const cells = (d.values || [[]])[0];
  return {
    A_Company:   cells[0] || '',
    B_Title:     cells[1] || '',
    C_Summary:   (cells[2] || '').slice(0, 80) + '…',
    D_Link:      cells[3] || '',
    E_Date:      cells[4] || '',
    F_Contacts:  (cells[5] || '').slice(0, 80) + '…',
    G_Notes:     (cells[6] || '').slice(0, 80) + '…'
  };
})()
```

Confirm Company, Title, Link, and Date match expectations. If any field is blank or wrong, re-run the Step 6 write for that range only.

---

## Final report

State:
- Job title and company
- **Added** (row N) or **Updated** (existing row N)
- Any fields that failed and why
