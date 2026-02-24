#!/usr/bin/env python3

import sys
import json
import os
from datetime import datetime

def main():
    try:
        # Read the event data from Claude
        input_data = json.load(sys.stdin)
        
        # Create a test file in the user's home directory
        test_file = os.path.expanduser("~/claude-hook-worked.txt")
        
        with open(test_file, "w") as f:
            f.write(f"✅ CLAUDE HOOK WORKED!\n")
            f.write(f"Time: {datetime.now()}\n")
            f.write(f"Event: {input_data.get('hook_event_name', 'Unknown')}\n")
            f.write(f"Full data: {json.dumps(input_data, indent=2)}\n")
        
        # Also log to stderr for debugging
        print(f"Hook created file: {test_file}", file=sys.stderr)
        
        sys.exit(0)
    except Exception as e:
        print(f"Error in hook handler: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()