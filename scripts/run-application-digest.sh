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
# pyenv's interpreter goes first because it is the only one with the `mcp`
# package. A bare `python3` under launchd's PATH resolves to
# /usr/local/opt/python@3.10/bin/python3.10, which does not have it, so the
# job_tracker server in .mcp.json dies on import and simply never registers.
# Interactive shells resolve python3 via pyenv shims and were always fine,
# which is exactly why this stayed invisible.
PYENV_BIN="$HOME/.pyenv/versions/3.10.3/bin"
export PATH="$PYENV_BIN:$HOME/.nvm/versions/node/v18.20.4/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LOG_DIR="$HOME/Library/Logs/application-digest"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

echo "=== application-digest run: $(date) ===" >> "$LOG_FILE"

# Fail loudly on a pyenv upgrade rather than silently degrading again.
if [ ! -x "$PYENV_BIN/python3" ]; then
  echo "=== FAILED: $PYENV_BIN/python3 is missing (pyenv version changed?) ===" >> "$LOG_FILE"
  exit 1
fi

# Pinned so an interactive /model change cannot alter what this scheduled job
# runs. Full name, not the `sonnet` alias, which would drift on its own.
claude -p "/application-digest" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --model claude-sonnet-5 \
  --allowedTools "mcp__gmail_personal__search_emails,mcp__gmail_personal__read_email,mcp__gmail_personal__send_email,mcp__gmail_personal__draft_email,mcp__job_tracker__list_all_jobs,mcp__job_tracker__find_job_for_email,mcp__job_tracker__update_job_status" \
  >> "$LOG_FILE" 2>&1

echo "=== done ===" >> "$LOG_FILE"
