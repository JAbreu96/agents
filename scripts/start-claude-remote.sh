#!/bin/bash
osascript <<'EOF'
tell application "Terminal"
    activate
    do script "cd /Users/joelchristabreu/Documents/projects/agents && claude --remote-control"
end tell
EOF
