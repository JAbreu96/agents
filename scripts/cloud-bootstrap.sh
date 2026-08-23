#!/bin/bash
#
# Rebuilds the credential files the MCP servers expect, from environment
# variables, then execs whatever command it is handed.
#
#   scripts/cloud-bootstrap.sh scripts/run-inbox-triage.sh
#
# A cloud Routine gets a fresh clone of this PUBLIC repo and nothing else --
# no ~/.gmail-mcp, no ~/.config/gtasks-mcp, no service account. Those files
# hold live credentials and can never be committed, so they are reconstructed
# here at run time from Routine secrets.
#
# Why a refresh token is enough: the Gmail MCP server was probed with a
# credentials file containing only a refresh token and expiry_date 0, and it
# minted a fresh access token against Google's token endpoint and completed a
# real API call. It also never wrote the new token back to disk -- it lives in
# memory for the life of the process. So these files are write-once and the
# container needs no persistent credential state.
#
# This script must never print a secret. Failures name the missing VARIABLE,
# never its value, because Routine logs are not a safe place for a token.

set -euo pipefail

# Public API identifiers, not secrets -- they must match the scopes the tokens
# were originally granted, or the refresh returns invalid_scope.
GMAIL_SCOPE="https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.settings.basic"

# gtasks needs no files. Unlike the Gmail server, @alvincrave/gtasks-mcp accepts
# GOOGLE_CLIENT_ID / _SECRET / _REFRESH_TOKEN directly, and .mcp.json maps the
# GTASKS_* variables below onto them. Verified against the real server with HOME
# pointed at an empty directory, so there was nothing on disk to fall back to.
#
# Those three are only read here to fail early if they are missing; the run
# script inherits them from the environment and never touches them.
REQUIRED=(
  GMAIL_OAUTH_KEYS
  GMAIL_REFRESH_TOKEN
  GMAIL_ALT_REFRESH_TOKEN
  GTASKS_CLIENT_ID
  GTASKS_CLIENT_SECRET
  GTASKS_REFRESH_TOKEN
  GCP_SERVICE_ACCOUNT
  TURSO_DATABASE_URL
  TURSO_AUTH_TOKEN
)

missing=()
for var in "${REQUIRED[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done

if (( ${#missing[@]} )); then
  echo "cloud-bootstrap: missing required environment variables:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  echo "Set these as secrets on the Routine." >&2
  exit 78  # EX_CONFIG
fi

umask 077
mkdir -p "$HOME/.gmail-mcp" "$HOME/.config/agents"

# Writes a Google OAuth token file from a refresh token alone. expiry_date 0
# marks the (absent) access token as long expired, which is what makes the
# client refresh on first use instead of trying to reuse nothing.
write_token_file() {
  local dest="$1" token_var="$2" scope="$3"
  TOKEN="${!token_var}" SCOPE="$scope" DEST="$dest" python3 - <<'PY'
import json, os
with open(os.environ["DEST"], "w") as f:
    json.dump({
        "refresh_token": os.environ["TOKEN"],
        "scope": os.environ["SCOPE"],
        "token_type": "Bearer",
        "expiry_date": 0,
    }, f)
PY
  chmod 600 "$dest"
}

# Writes a variable's contents out as JSON, validating it parses. Catches a
# secret that was pasted truncated -- which otherwise surfaces much later as an
# opaque MCP server startup failure.
write_json_var() {
  local dest="$1" var="$2"
  VALUE="${!var}" DEST="$dest" VAR="$var" python3 - <<'PY'
import json, os, sys
try:
    parsed = json.loads(os.environ["VALUE"])
except json.JSONDecodeError as e:
    sys.exit(f"cloud-bootstrap: {os.environ['VAR']} is not valid JSON ({e}). "
             f"Check the secret was stored whole.")
with open(os.environ["DEST"], "w") as f:
    json.dump(parsed, f)
PY
  chmod 600 "$dest"
}

write_json_var   "$HOME/.gmail-mcp/gcp-oauth.keys.json"          GMAIL_OAUTH_KEYS
write_token_file "$HOME/.gmail-mcp/credentials.json"             GMAIL_REFRESH_TOKEN     "$GMAIL_SCOPE"
write_token_file "$HOME/.gmail-mcp/credentials-alt.json"         GMAIL_ALT_REFRESH_TOKEN "$GMAIL_SCOPE"
write_json_var   "$HOME/.config/agents/gcp-service-account.json" GCP_SERVICE_ACCOUNT

# The MCP servers read this path from the environment; the run scripts and
# jobs_db read TURSO_* directly, which are already exported by the Routine.
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/agents/gcp-service-account.json"

echo "cloud-bootstrap: wrote 4 credential files (gtasks authenticates from the environment)"

if (( $# )); then
  exec "$@"
fi
