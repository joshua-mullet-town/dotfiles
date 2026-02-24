#!/usr/bin/env python3
import os
import datetime

# Create a simple test file to prove the hook is called
timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open("/tmp/claude-hook-test.txt", "a") as f:
    f.write(f"[{timestamp}] TEST HOOK CALLED!\n")