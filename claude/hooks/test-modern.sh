#!/bin/bash
echo "[$(date)] Modern hook called with args: $*" >> /tmp/claude-modern-hook.log
echo "Working directory: $(pwd)" >> /tmp/claude-modern-hook.log
echo "Environment vars:" >> /tmp/claude-modern-hook.log
env | grep -i claude >> /tmp/claude-modern-hook.log
echo "---" >> /tmp/claude-modern-hook.log