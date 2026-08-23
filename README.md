# Agents Project

Claude Code skills and MCP servers for job search automation — tracking postings, reviewing resumes, drafting outreach emails, and sending digests.

> **Works alongside [`career-ops`](https://github.com/JAbreu96/career-ops)** (cloned at `../career-ops`).
> career-ops is the **front of the funnel** — job discovery/scan, A–F evaluation, ATS CV tailoring, company research, and interview prep — and its `data/applications.md` is the **source of truth** for tracking.
> This repo is the **cloud comms layer**: use it only for **job tracking** (`job-tracker`), **Gmail draft outreach** (`outreach-email`), and **Gmail inbound scanning** (`application-digest`). The full division of labor lives in `career-ops/modes/_custom.md`.
> Note: `job-tracker` writes contacts to the Google Sheet, so copy them into the matching `applications.md` row. Sheet-centric skills (`follow-up-reminder`, `job-digest`, `archive-jobs`) are secondary here — prefer career-ops's `followup`/`tracker`/`patterns` to avoid drift.

---

## Skills

| Skill | What it does |
|---|---|
| `job-tracker` | Fetch a job URL, extract details, and log to the local job tracker DB |
| `job-tracker-dispatch` | Same as above but uses Claude-in-Chrome instead of the gsheets MCP |
| `outreach-email` | Draft a referral/networking email and save it as a Gmail draft |
| `resume-review` | Score a resume against a job description, rewrite bullets, run ATS scan, export to Google Docs |
| `application-digest` | Check Gmail for application updates in the last 24 hours and send a summary email |
| `follow-up-reminder` | Scan the job tracker for stale applications and send a follow-up nudge |
| `archive-jobs` | Move jobs older than 60 days to the Archive sheet and send a summary email |
| `job-digest` | Print a summary of all tracked jobs with applied/stale/not-applied status |

Invoke any skill in Claude Code with `/skill-name [args]`.

---

## Setup

### 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

Copy `.env.example` to `.env` (or create `.env`) and fill in the values:

```bash
# .env
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

- **`GOOGLE_APPLICATION_CREDENTIALS`** — path to your Google Cloud service account JSON file (see step 3)

### 3. Google Cloud service account

All skills that read/write Google Sheets, Docs, or Drive use a service account.

1. Go to [Google Cloud Console](https://console.cloud.google.com) and create a project.
2. Enable these APIs:
   - Google Sheets API
   - Google Docs API
   - Google Drive API
3. Create a service account and download the JSON key file. Store it somewhere safe (e.g. `~/Documents/service-account.json`).
4. Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to the path of that file.

### 4. Google Sheet — job tracker

The skills read and write to a single Google Sheet.

1. Create a Google Sheet with a tab named `Sheet1`.
2. Add a second tab named `Archive` (used by `archive-jobs`).
3. Row 1 should be a header row with these columns in order:

   | A | B | C | D | E | F | G | H |
   |---|---|---|---|---|---|---|---|
   | Company | Job Title | Summary | Link | Date Added | Contacts | Notes | Outreach Date |

4. Share the sheet with the service account email (found in your JSON key file under `client_email`). Give it **Editor** access.
5. Copy the spreadsheet ID from the URL (`https://docs.google.com/spreadsheets/d/<ID>/edit`) and update it in:
   - `.claude/skills/job-tracker/SKILL.md`
   - `.claude/skills/job-tracker-dispatch/SKILL.md`
   - `.claude/skills/outreach-email/SKILL.md`
   - `.claude/skills/application-digest/SKILL.md`
   - `.claude/skills/job-digest/SKILL.md`
   - `mcp_servers/job_tracker/sheet.py` (`SPREADSHEET_ID` constant)

### 5. Google Doc — resume (resume-review skill)

The `resume-review` skill reads your base resume from a Google Doc and creates a tailored copy per application.

1. Create a Google Doc with your resume.
2. Share it with the service account email (Editor access).
3. Create a Google Drive folder for exported resumes and share it with the service account (Editor access).
4. Update these values in `.claude/skills/resume-review/SKILL.md`:
   - `Google Doc ID` — the ID from your resume doc URL
   - `Google Drive Resumes Folder ID` — the ID from your folder URL
   - `Service Account` — path to your service account JSON file

### 6. MCP servers

Skills use three MCP servers defined in `.mcp.json`:

#### `job_tracker` (custom Python server)

Reads and writes the job tracker sheet via the Google Sheets API.

```json
{
  "job_tracker": {
    "command": "python3",
    "args": ["mcp_servers/job_tracker/server.py"],
    "env": {
      "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json"
    }
  }
}
```

#### `gmail_personal` (npm package)

Reads and sends Gmail via OAuth. On first run it will open a browser to authorize your Google account.

```json
{
  "gmail_personal": {
    "command": "npx",
    "args": ["-y", "@gongrzhe/server-gmail-autoauth-mcp"]
  }
}
```

#### `gsheets` (npm package)

Reads and writes Google Sheets using the service account.

```json
{
  "gsheets": {
    "command": "npx",
    "args": ["-y", "mcp-gsheets@latest"],
    "env": {
      "GOOGLE_PROJECT_ID": "your-gcp-project-id",
      "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json"
    }
  }
}
```

Update `.mcp.json` with your actual paths and project ID, then enable the servers in `.claude/settings.local.json`:

```json
{
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["gsheets", "gmail_personal", "job_tracker"]
}
```

### 7. Outreach email — sender details

The `outreach-email` skill uses hardcoded sender info. Update these fields in `.claude/skills/outreach-email/SKILL.md` to match your own profile:

- `Name`
- `Email`
- `Current/recent role`
- `LinkedIn URL`

---

## Skill dependencies at a glance

| Skill | gsheets MCP | gmail MCP | job_tracker MCP | Google Docs API |
|---|:---:|:---:|:---:|:---:|
| job-tracker | ✓ | | | |
| job-tracker-dispatch | | | | |
| outreach-email | ✓ | ✓ | | |
| resume-review | | | | ✓ |
| application-digest | ✓ | ✓ | | |
| follow-up-reminder | | ✓ | ✓ | |
| archive-jobs | | ✓ | ✓ | |
| job-digest | ✓ | | | |

---

## Browser extension — ApplyPass Capture

`browser_extension/applypass_capture/` is a Chrome DevTools panel that captures ApplyPass
export responses and merges the paginated pages into one JSON file for the
`applypass-inbound` skill, replacing the per-page copy-paste into `data/applied_inbox.json`.
It makes no Python changes and never writes to the database. Load-unpacked instructions and
its `node --test` command are in that directory's README.

## Running tests

```bash
pytest -q
```
