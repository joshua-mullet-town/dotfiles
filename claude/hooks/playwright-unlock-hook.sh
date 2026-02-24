#!/bin/bash
# 🎭 Playwright Browser Lock Auto-Fix Hook
# This hook automatically runs when Playwright MCP encounters browser lock errors
# Called by Claude Code's PostToolUse hook system

echo "🔧 Playwright browser lock detected - running auto-unlock..."

# Run the main unlock script
/Users/joshuamullet/code/holler/playwright-unlock.sh

echo "✅ Auto-unlock completed - you can continue using Playwright MCP"

exit 0