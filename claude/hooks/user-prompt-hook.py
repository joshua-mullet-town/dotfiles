#!/usr/bin/env python3
"""
🎯 Holler User Prompt Submit Hook
Updates session status to 'loading' when user submits a prompt
Called by Claude Code's UserPromptSubmit hook system
"""

import json
import sys
import requests
import os
from datetime import datetime

def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)
        
        # For UserPromptSubmit hooks, Claude session ID should be available
        session_id = (
            input_data.get('session_id') or 
            input_data.get('sessionId') or
            os.environ.get('CLAUDE_SESSION_ID') or
            ''
        )
        
        if not session_id:
            print(json.dumps({
                "decision": "allow",
                "reason": "No session ID available for UserPromptSubmit"
            }))
            return
        
        # Send status update to Holler backend
        try:
            payload = {
                'claudeSessionId': session_id,
                'status': 'loading',
                'hookType': 'UserPromptSubmit',
                'timestamp': input_data.get('timestamp', '')
            }
            
            response = requests.post(
                'http://localhost:3002/api/session-status-update',
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ Session loading: {session_id}", file=sys.stderr)
            else:
                print(f"⚠️ Status update failed: {response.status_code}", file=sys.stderr)
                
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Status update request failed: {e}", file=sys.stderr)
        
        # Always allow the operation
        print(json.dumps({
            "decision": "allow",
            "reason": "Session status updated to loading"
        }))
        
    except Exception as e:
        # If anything goes wrong, allow the operation and log the error
        print(f"UserPromptSubmit hook error: {e}", file=sys.stderr)
        print(json.dumps({
            "decision": "allow",
            "reason": f"Hook failed: {e}"
        }))

if __name__ == "__main__":
    main()