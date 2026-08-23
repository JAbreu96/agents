#!/bin/bash

# launchd starts jobs with a minimal environment, so PATH is rebuilt here.
# Derive HOME and the repo root rather than hard-coding them, so this runs for
# any user and survives the repo being relocated (e.g. out of ~/Documents,
# which macOS TCC blocks launchd from reading).
: "${HOME:=$(cd ~ && pwd)}"
export HOME
# The Claude CLI resolves its stored credentials through USER. Strip it and the
# CLI reports "Not logged in - please run /login", which sends you hunting for
# an auth problem that does not exist. launchd does supply USER, so this is a
# guard rather than a fix -- but the failure it prevents is a badly misleading
# one, and the cost is two lines.
: "${USER:=$(id -un)}"
export USER
export PATH="$HOME/.nvm/versions/node/v18.20.4/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LOG_DIR="$HOME/Library/Logs/work-search-record"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "=== work-search-record run: $(date) ===" >> "$LOG_FILE"

claude -p "/work-search-record" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --allowedTools "mcp__gmail_personal__search_emails,mcp__gmail_personal__read_email,mcp__gmail_personal__send_email,Bash,Read,Edit,Write" \
  >> "$LOG_FILE" 2>&1

echo "=== done ===" >> "$LOG_FILE"
