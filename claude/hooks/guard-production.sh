#!/bin/bash
#
# Guard Production - Prevents worktree agents from editing production files
#
# This hook blocks Edit/Write operations when:
# - Agent is running from a worktree (~/.worktrees/homestead/*)
# - Trying to edit files in production (~/code/homestead/*)
#
# The main agent (running from ~/code/homestead) can edit freely.
#

# Production directory (the sacred one)
PRODUCTION_DIR="/Users/joshuamullet/code/homestead"

# Worktree parent directory
WORKTREE_PARENT="/Users/joshuamullet/.worktrees/homestead"

# Read input from stdin
INPUT=$(cat)

# Parse the hook input
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only check Edit and Write operations
if [[ "$TOOL_NAME" != "Edit" && "$TOOL_NAME" != "Write" ]]; then
    exit 0
fi

# If no file path, allow (shouldn't happen but be safe)
if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Resolve file path to absolute (handle relative paths)
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="$CWD/$FILE_PATH"
fi

# Normalize paths (resolve .. and such)
FILE_PATH=$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd)/$(basename "$FILE_PATH") 2>/dev/null || echo "$FILE_PATH"

# Check if agent is in a worktree
IS_IN_WORKTREE=false
if [[ "$CWD" == "$WORKTREE_PARENT"* ]]; then
    IS_IN_WORKTREE=true
fi

# Check if trying to edit production
IS_EDITING_PRODUCTION=false
if [[ "$FILE_PATH" == "$PRODUCTION_DIR"* ]]; then
    IS_EDITING_PRODUCTION=true
fi

# If in worktree AND trying to edit production -> BLOCK
if [[ "$IS_IN_WORKTREE" == "true" && "$IS_EDITING_PRODUCTION" == "true" ]]; then
    # Extract worktree name for helpful message
    WORKTREE_NAME=$(echo "$CWD" | sed "s|$WORKTREE_PARENT/||" | cut -d'/' -f1)

    # Create the block message
    cat >&2 << EOF
{
  "decision": "block",
  "reason": "🛡️ PRODUCTION PROTECTED - Cannot edit production files from a worktree.

You are working in:  $CWD
Trying to edit:      $FILE_PATH

Production files can only be edited by the main Homestead agent.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TO MERGE YOUR CHANGES INTO PRODUCTION:

1. Commit your changes in this worktree:
   git add -A && git commit -m 'Your message'

2. Use the /worktree skill to safely merge:
   /worktree merge

This will merge main into your branch first (so you don't lose
any production changes), then merge your branch into main.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}
EOF
    exit 2
fi

# Allow the operation
exit 0
