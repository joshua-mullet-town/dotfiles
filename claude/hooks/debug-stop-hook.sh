#!/bin/bash

# Debug Stop Hook - Dump all available data
echo "=== STOP HOOK DEBUG DUMP ===" >> ~/stop-hook-debug.txt
echo "Timestamp: $(date)" >> ~/stop-hook-debug.txt
echo "" >> ~/stop-hook-debug.txt

# Dump all environment variables that start with CLAUDE
echo "--- CLAUDE Environment Variables ---" >> ~/stop-hook-debug.txt
env | grep CLAUDE >> ~/stop-hook-debug.txt
echo "" >> ~/stop-hook-debug.txt

# Dump all command line arguments
echo "--- Command Line Arguments ---" >> ~/stop-hook-debug.txt
echo "Argument count: $#" >> ~/stop-hook-debug.txt
for i in "$@"; do
  echo "Arg: $i" >> ~/stop-hook-debug.txt
done
echo "" >> ~/stop-hook-debug.txt

# Dump all stdin data (JSON input from Claude)
echo "--- STDIN Data (JSON from Claude) ---" >> ~/stop-hook-debug.txt
input_data=$(cat)
echo "$input_data" >> ~/stop-hook-debug.txt
echo "" >> ~/stop-hook-debug.txt

# Try to pretty-print the JSON if possible
echo "--- Pretty JSON (if valid) ---" >> ~/stop-hook-debug.txt
echo "$input_data" | python3 -m json.tool >> ~/stop-hook-debug.txt 2>/dev/null || echo "JSON parsing failed" >> ~/stop-hook-debug.txt
echo "" >> ~/stop-hook-debug.txt

echo "=== END DEBUG DUMP ===" >> ~/stop-hook-debug.txt
echo "" >> ~/stop-hook-debug.txt

# Always approve the operation
echo '{"decision": "approve", "reason": "Debug hook completed"}'