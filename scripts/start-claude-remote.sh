#!/bin/bash
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$REPO_DIR' && claude --remote-control"
end tell
EOF
