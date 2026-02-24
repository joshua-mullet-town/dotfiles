#!/usr/bin/env python3
"""
🔗 Holler Session Link Hook
Automatically links new Claude session to most recent Holler session
Called by Claude Code's SessionStart hook system
"""

import json
import sys
import requests
import os

def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)
        
        # For SessionStart hooks, Claude session ID should be available
        session_id = (
            input_data.get('session_id') or 
            input_data.get('sessionId') or
            os.environ.get('CLAUDE_SESSION_ID') or
            ''
        )
        
        if not session_id:
            print(json.dumps({
                "decision": "allow",
                "reason": "No session ID available for linking"
            }))
            return
        
        # Send session link event to Holler backend (existing endpoint)
        try:
            payload = {
                'sessionId': session_id,
                'timestamp': input_data.get('timestamp', ''),
                'hookType': 'SessionStart'
            }
            
            response = requests.post(
                'http://localhost:3002/api/claude-session-event',
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ Session linked: {session_id}", file=sys.stderr)
            else:
                print(f"⚠️ Session linking failed: {response.status_code}", file=sys.stderr)
                
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Session linking request failed: {e}", file=sys.stderr)
        
        # Always allow the operation
        print(json.dumps({
            "decision": "allow",
            "reason": "Session linking attempted"
        }))
        
    except Exception as e:
        # If anything goes wrong, allow the operation and log the error
        print(f"Session link hook error: {e}", file=sys.stderr)
        print(json.dumps({
            "decision": "allow",
            "reason": f"Hook failed: {e}"
        }))

if __name__ == "__main__":
    main()