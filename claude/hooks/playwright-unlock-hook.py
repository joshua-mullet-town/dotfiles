#!/usr/bin/env python3
"""
🎭 Playwright Browser Lock Auto-Fix Hook
This hook automatically runs when Playwright MCP encounters browser lock errors
Called by Claude Code's PostToolUse hook system
"""

import json
import sys
import subprocess
import os

def main():
    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)
        
        # Extract tool response
        tool_response = input_data.get('tool_response', {})
        
        # Check if this is an error response
        error_message = ""
        if 'error' in tool_response:
            error_message = str(tool_response['error'])
        elif isinstance(tool_response, dict) and 'message' in tool_response:
            error_message = str(tool_response['message'])
        elif isinstance(tool_response, str):
            error_message = tool_response
        
        # Check for the specific Playwright browser lock error
        playwright_error_patterns = [
            "Browser is already in use for /Users/joshuamullet/Library/Caches/ms-playwright/mcp-chrome",
            "use --isolated to run multiple instances of the same browser",
            "Browser is already in use"
        ]
        
        error_detected = any(pattern in error_message for pattern in playwright_error_patterns)
        
        if error_detected:
            print("🔧 Playwright browser lock detected - running auto-unlock...", file=sys.stderr)
            
            # Run the unlock script
            unlock_script_path = "/Users/joshuamullet/code/holler/playwright-unlock.sh"
            
            if os.path.exists(unlock_script_path):
                try:
                    result = subprocess.run([unlock_script_path], 
                                          capture_output=True, 
                                          text=True, 
                                          timeout=60)
                    
                    print("✅ Auto-unlock completed - you can continue using Playwright MCP", file=sys.stderr)
                    
                    # Output success decision
                    output = {
                        "decision": "allow",
                        "reason": "Auto-fixed Playwright browser lock error"
                    }
                    
                except subprocess.TimeoutExpired:
                    print("⚠️ Auto-unlock timed out", file=sys.stderr)
                    output = {
                        "decision": "allow", 
                        "reason": "Auto-unlock attempted but timed out"
                    }
                except Exception as e:
                    print(f"⚠️ Auto-unlock failed: {e}", file=sys.stderr)
                    output = {
                        "decision": "allow",
                        "reason": f"Auto-unlock failed: {e}"
                    }
            else:
                print(f"⚠️ Unlock script not found at {unlock_script_path}", file=sys.stderr)
                output = {
                    "decision": "allow",
                    "reason": "Unlock script not found"
                }
        else:
            # No error detected, allow normally
            output = {
                "decision": "allow",
                "reason": "No browser lock error detected"
            }
        
        # Output the decision
        print(json.dumps(output))
        
    except Exception as e:
        # If anything goes wrong, allow the operation and log the error
        print(f"Hook error: {e}", file=sys.stderr)
        print(json.dumps({
            "decision": "allow",
            "reason": f"Hook failed: {e}"
        }))
        
if __name__ == "__main__":
    main()