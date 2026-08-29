#!/usr/bin/env bash
# PreToolUse/Bash hook: refuse a shell command that grants itself permission to
# write to the live job tracker.
#
# src/jobs_db.py already refuses remote INSERT/UPDATE/DELETE unless
# JOBS_DB_ALLOW_REMOTE_WRITES is set. That stops the accident. It does not stop
# the shortcut -- prefixing the same throwaway script with the variable and
# running it again, which turns a guard into a speed bump.
#
# Entry points declare themselves in Python, in __main__, in a reviewed file.
# None of them need this variable on a shell command line, so a command that
# sets it is a human or an agent working around the guard rather than a program
# doing its job. That is a narrow, near-zero-false-positive signal.
#
# Reads the hook payload on stdin; prints a deny decision or nothing.
set -euo pipefail

command_text=$(jq -r '.tool_input.command // ""' 2>/dev/null || echo "")

# Assignment on a command line or via export, with an affirmative value.
if printf '%s' "$command_text" \
   | grep -qE '(^|[[:space:];&|(]|export[[:space:]]+)JOBS_DB_ALLOW_REMOTE_WRITES[[:space:]]*=[[:space:]]*["'"'"']?(1|true|yes|on)'; then
  cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "This command sets JOBS_DB_ALLOW_REMOTE_WRITES, which lifts the guard on the LIVE job tracker. Ad-hoc scripts must never write to production -- that has already put invented rows into the tracker twice. Take a copy instead:\n\n    python scripts/clone_remote_db.py\n    JOBS_DB_PATH=data/snapshots/<stamp>.db python your_script.py\n\nOnly a real entry point may write, and it declares that by calling jobs_db.allow_remote_writes() in its __main__ -- not by setting this variable in a shell. If you are certain you need it, ask the user first."
  }
}
JSON
fi

exit 0
