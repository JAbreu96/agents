#!/bin/bash

export PATH="/Users/joelchristabreu/.nvm/versions/node/v18.20.4/bin:/Users/joelchristabreu/.local/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/Users/joelchristabreu"

cd /Users/joelchristabreu/Documents/projects/agents

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
