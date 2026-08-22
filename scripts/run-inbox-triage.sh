#!/bin/bash

# launchd starts jobs with a minimal environment, so PATH is rebuilt here.
# Derive HOME and the repo root rather than hard-coding them, so this runs for
# any user and survives the repo being relocated (e.g. out of ~/Documents,
# which macOS TCC blocks launchd from reading).
: "${HOME:=$(cd ~ && pwd)}"
export HOME
export PATH="$HOME/.nvm/versions/node/v18.20.4/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LOG_DIR="$HOME/Library/Logs/inbox-triage"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "=== inbox-triage run: $(date) ===" >> "$LOG_FILE"

# No send_email on purpose: triage reports to this log, never to the inbox
# it exists to keep quiet. Bash is needed for the watermark read/write and for
# the predicates in src/triage_rules.py.
#
# gmail_alt is ajoelcrist@ (LinkedIn). Read tools only -- no draft_email --
# until Joel decides which address should reply to those threads.
# gtasks__update is for appending [SUPERSEDED ...] notes; there is deliberately
# no gtasks__delete or completion path, so triage can never destroy work.
claude -p "/inbox-triage" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --allowedTools "mcp__gmail_personal__search_emails,mcp__gmail_personal__read_email,mcp__gmail_personal__draft_email,mcp__gmail_alt__search_emails,mcp__gmail_alt__read_email,mcp__job_tracker__find_job_for_email,mcp__job_tracker__update_job_status,mcp__job_tracker__update_notes,mcp__job_tracker__add_job,mcp__job_tracker__list_all_jobs,mcp__gtasks__list,mcp__gtasks__list_task_lists,mcp__gtasks__create,mcp__gtasks__update,Bash" \
  >> "$LOG_FILE" 2>&1

echo "=== done ===" >> "$LOG_FILE"
