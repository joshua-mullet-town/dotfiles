#!/bin/bash
# 🎯 Holler Stop Hook
# Updates session status to 'ready' when Claude finishes responding
# Called by Claude Code's Stop hook system

# Log that hook was called
echo "[$(date)] 🎯 STOP HOOK FIRED - Starting execution" >> ~/stop-hook.log

# Read JSON input from stdin
input_data=$(cat)

# Log the raw input data
echo "[$(date)] 📦 Raw input data: $input_data" >> ~/stop-hook.log

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
    echo "[$(date)] ❌ No session ID found in input data" >> ~/stop-hook.log
    echo '{"decision": "approve", "reason": "No session ID available for Stop"}'
    exit 0
fi

echo "[$(date)] ✅ Extracted session ID: $session_id" >> ~/stop-hook.log

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
  "status": "ready",
  "hookType": "Stop",
  "timestamp": "$timestamp"
}
EOF
)

echo "[$(date)] 📤 Sending payload to server: $payload" >> ~/stop-hook.log

# Send to server and capture response
response=$(curl -X POST \
  -H "Content-Type: application/json" \
  -d "$payload" \
  -m 5 \
  -w "HTTP_CODE:%{http_code}" \
  http://localhost:3002/api/session-status-update 2>/dev/null)

curl_exit_code=$?

echo "[$(date)] 📥 Curl exit code: $curl_exit_code" >> ~/stop-hook.log
echo "[$(date)] 📥 Server response: $response" >> ~/stop-hook.log

if [[ $curl_exit_code -eq 0 ]]; then
    echo "[$(date)] ✅ Successfully sent to server" >> ~/stop-hook.log
    echo "✅ Session ready: $session_id" >&2
else
    echo "[$(date)] ❌ Curl failed with exit code: $curl_exit_code" >> ~/stop-hook.log
    echo "⚠️ Status update failed" >&2
fi

# Always approve the operation
echo '{"decision": "approve", "reason": "Session status updated to ready"}'