#!/bin/bash
# 🔗 Holler Session Link Hook
# Automatically links new Claude session to most recent Holler session
# Called by Claude Code's SessionStart hook system

# Read JSON input from stdin
input_data=$(cat)

# Extract Claude session ID from JSON input
session_id=$(echo "$input_data" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('session_id', data.get('sessionId', '')))
except:
    print('')
" 2>/dev/null)

if [[ -z "$session_id" ]]; then
    echo '{"decision": "approve", "reason": "No session ID available for linking"}'
    exit 0
fi

# Extract timestamp
timestamp=$(echo "$input_data" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('timestamp', ''))
except:
    print('')
" 2>/dev/null)

# Send session link event to Holler backend using curl
payload=$(cat <<EOF
{
  "sessionId": "$session_id",
  "timestamp": "$timestamp",
  "hookType": "SessionStart"
}
EOF
)

curl -X POST \
  -H "Content-Type: application/json" \
  -d "$payload" \
  -m 5 \
  --silent \
  http://localhost:3002/api/claude-session-event >/dev/null 2>&1

if [[ $? -eq 0 ]]; then
    echo "✅ Session linked: $session_id" >&2
else
    echo "⚠️ Session linking failed" >&2
fi

# Always approve the operation
echo '{"decision": "approve", "reason": "Session linking attempted"}'