#!/bin/bash

# launchd starts jobs with a minimal environment, so PATH is rebuilt here.
# Derive HOME and the repo root rather than hard-coding them, so this runs for
# any user and survives the repo being relocated (e.g. out of ~/Documents,
# which macOS TCC blocks launchd from reading).
: "${HOME:=$(cd ~ && pwd)}"
export HOME
export PATH="$HOME/.nvm/versions/node/v18.20.4/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LOG_DIR="$HOME/Library/Logs/archive-jobs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "=== archive-jobs run: $(date) ===" >> "$LOG_FILE"

claude -p "/archive-jobs" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --allowedTools "mcp__job_tracker__archive_old_jobs,mcp__gmail_personal__send_email" \
  >> "$LOG_FILE" 2>&1

echo "=== done ===" >> "$LOG_FILE"
