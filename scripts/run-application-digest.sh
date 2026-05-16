#!/bin/bash

export PATH="/Users/joelchristabreu/.nvm/versions/node/v18.20.4/bin:/Users/joelchristabreu/.local/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/Users/joelchristabreu"

cd /Users/joelchristabreu/Documents/projects/agents

LOG_DIR="$HOME/Library/Logs/application-digest"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "=== application-digest run: $(date) ===" >> "$LOG_FILE"

claude -p "/application-digest" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --allowedTools "mcp__gmail_personal__search_emails,mcp__gmail_personal__read_email,mcp__gmail_personal__send_email,mcp__gmail_personal__draft_email,mcp__gsheets__sheets_get_values" \
  >> "$LOG_FILE" 2>&1

echo "=== done ===" >> "$LOG_FILE"
