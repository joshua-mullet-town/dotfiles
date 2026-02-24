#!/usr/bin/env python3
"""
🎯 Holler Session Status Hook
Updates session status in real-time via Socket.IO
Called by Claude Code's hook system (SessionStart, UserPromptSubmit, Stop)
"""

import json
import sys
import requests
import os

def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)
        
        # Get Claude session ID from environment or input
        session_id = os.environ.get('CLAUDE_SESSION_ID', '')
        if not session_id:
            # Try to extract from input data - different hooks provide different data
            session_id = input_data.get('session_id', input_data.get('sessionId', ''))
        
        # Determine hook type from script arguments or environment
        hook_type = os.environ.get('CLAUDE_HOOK_TYPE', 'Unknown')
        
        # Map hook types to status
        status_mapping = {
            'SessionStart': 'connected',
            'UserPromptSubmit': 'loading', 
            'Stop': 'ready'
        }
        
        status = status_mapping.get(hook_type, 'unknown')
        
        if not session_id:
            print(json.dumps({
                "decision": "allow",
                "reason": f"No session ID available"
            }))
            return
        
        # Send status update to Holler backend
        try:
            payload = {
                'claudeSessionId': session_id,
                'status': status,
                'hookType': hook_type,
                'timestamp': input_data.get('timestamp', '')
            }
            
            response = requests.post(
                'http://localhost:3002/api/session-status-update',
                json=payload,
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"✅ Status updated: {session_id} → {status}", file=sys.stderr)
            else:
                print(f"⚠️ Status update failed: {response.status_code}", file=sys.stderr)
                
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Status update request failed: {e}", file=sys.stderr)
        
        # Always allow the operation
        print(json.dumps({
            "decision": "allow",
            "reason": f"Status updated: {status}"
        }))
        
    except Exception as e:
        # If anything goes wrong, allow the operation and log the error
        print(f"Hook error: {e}", file=sys.stderr)
        print(json.dumps({
            "decision": "allow",
            "reason": f"Hook failed: {e}"
        }))

if __name__ == "__main__":
    main()