#!/usr/bin/env python3
"""
🎯 Holler Session Start Hook
Updates session status to 'connected' when Claude session starts
Called by Claude Code's SessionStart hook system
"""

import json
import sys
import requests
import os
from datetime import datetime

def main():
    try:
        # Create detailed log entry with timestamp
        timestamp = datetime.now().isoformat()
        
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)
        
        # Log the full hook trigger for debugging
        print(f"🚀 [HOLLER-HOOK] {timestamp} - SessionStart hook triggered", file=sys.stderr)
        print(f"🔍 [HOLLER-HOOK] Input data keys: {list(input_data.keys())}", file=sys.stderr)
        
        # For SessionStart hooks, Claude session ID should be available
        # Try multiple ways to get the session ID
        session_id = (
            input_data.get('session_id') or 
            input_data.get('sessionId') or
            os.environ.get('CLAUDE_SESSION_ID') or
            ''
        )
        
        print(f"🆔 [HOLLER-HOOK] Session ID detected: {session_id}", file=sys.stderr)
        
        if not session_id:
            print(f"❌ [HOLLER-HOOK] No session ID available for SessionStart at {timestamp}", file=sys.stderr)
            print(json.dumps({
                "decision": "allow",
                "reason": "No session ID available for SessionStart"
            }))
            return
        
        # Send status update to Holler backend
        try:
            payload = {
                'claudeSessionId': session_id,
                'status': 'connected',
                'hookType': 'SessionStart',
                'timestamp': input_data.get('timestamp', timestamp)
            }
            
            print(f"📡 [HOLLER-HOOK] Sending status update to Holler backend: {payload}", file=sys.stderr)
            
            response = requests.post(
                'http://localhost:3002/api/session-status-update',
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ [HOLLER-HOOK] {timestamp} - Session connected successfully: {session_id}", file=sys.stderr)
                print(f"🎯 [HOLLER-HOOK] Holler backend confirmed session connection", file=sys.stderr)
            else:
                print(f"⚠️ [HOLLER-HOOK] Status update failed with code: {response.status_code}", file=sys.stderr)
                
        except requests.exceptions.RequestException as e:
            print(f"⚠️ [HOLLER-HOOK] Status update request failed: {e}", file=sys.stderr)
        
        # Always allow the operation
        print(json.dumps({
            "decision": "allow",
            "reason": "Session status updated to connected"
        }))
        
    except Exception as e:
        # If anything goes wrong, allow the operation and log the error
        print(f"SessionStart hook error: {e}", file=sys.stderr)
        print(json.dumps({
            "decision": "allow",
            "reason": f"Hook failed: {e}"
        }))

if __name__ == "__main__":
    main()