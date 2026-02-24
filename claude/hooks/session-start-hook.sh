#!/bin/bash
# 🎯 Holler Session Start Hook
# Updates session status to 'connected' when Claude session starts
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
    echo '{"decision": "approve", "reason": "No session ID available for SessionStart"}'
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

# Send status update to Holler backend using curl
payload=$(cat <<EOF
{
  "claudeSessionId": "$session_id",
  "status": "connected",
  "hookType": "SessionStart",
  "timestamp": "$timestamp"
}
EOF
)

curl -X POST \
  -H "Content-Type: application/json" \
  -d "$payload" \
  -m 5 \
  --silent \
  http://localhost:3002/api/session-status-update >/dev/null 2>&1

if [[ $? -eq 0 ]]; then
    echo "✅ Session connected: $session_id" >&2
else
    echo "⚠️ Status update failed" >&2
fi

# Always approve the operation
echo '{"decision": "approve", "reason": "Session status updated to connected"}'