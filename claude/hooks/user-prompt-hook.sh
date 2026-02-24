#!/bin/bash
echo "HOOK TRIGGERED: $(date)" >> /tmp/claude-hook-test.txt
echo "PTY TEST WORKED!" >> /tmp/claude-hook-test.txt
echo '{"decision": "approve", "reason": "Test hook"}'