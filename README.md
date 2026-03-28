# Agents Project

This repository contains a minimal AI agent scaffold.

## Quick start

1. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the agent example:
   ```bash
   python -m src.agent
   ```
3. Run tests:
   ```bash
   pytest -q
   ```

## Job tracker agent

1. Create Google service account key and store JSON file locally.
2. Set environment variable:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
   ```
3. Create a Google Sheet and share with service account email.
4. Run:
   ```bash
   python -m src.job_agent
   ```

By default this runs against:
- URL: `https://example.com/job`
- Spreadsheet: `https://docs.google.com/spreadsheets/d/1CTqYgEFnOUySEIBpqFxeRdjBJxeImi40MZ_rhq9NE4Q/edit`
- Worksheet: `Sheet1`

Override as needed with CLI args or env vars.

You can provide:
- a spreadsheet URL (recommended),
- a spreadsheet ID, or
- a spreadsheet name.

Optional: use `--service-account-json` to pass path directly.

If your sheet is called "job tracker" use:
```bash
python -m src.job_agent --table-name "job tracker"
```
Or set env:
```bash
export JOB_TRACKER_TABLE="job tracker"
```
