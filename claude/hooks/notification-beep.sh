#!/bin/bash

# Claude Code notification beep hook
# Plays system beep when Claude finishes responding

# Log that hook was called
echo "$(date): Hook executed" >> /tmp/claude-hook.log
echo "HOOK CALLED" >> /tmp/hook-debug.log

# Check if notifications are enabled
HOOKS_CONFIG="$HOME/.claude/hooks-config.json"

if [[ -f "$HOOKS_CONFIG" ]]; then
    NOTIFICATIONS_ENABLED=$(python3 -c "
import json
try:
    with open('$HOOKS_CONFIG', 'r') as f:
        config = json.load(f)
    enabled = config.get('notifications', {}).get('enabled', True)
    print('true' if enabled else 'false')
except:
    print('true')
")
    NOTIFICATION_TYPE=$(python3 -c "
import json
try:
    with open('$HOOKS_CONFIG', 'r') as f:
        config = json.load(f)
    print(config.get('notifications', {}).get('type', 'beep'))
except:
    print('beep')
")
else
    NOTIFICATIONS_ENABLED="true"
    NOTIFICATION_TYPE="beep"
fi

if [[ "$NOTIFICATIONS_ENABLED" == "true" ]]; then
    case "$NOTIFICATION_TYPE" in
        "sound")
            # Play system sound (more noticeable)
            if command -v afplay >/dev/null 2>&1; then
                afplay /System/Library/Sounds/Glass.aiff
            else
                osascript -e 'beep 2' || echo -e '\a'
            fi
            ;;
        "unique")
            # Play distinctive completion sound
            if command -v afplay >/dev/null 2>&1; then
                afplay /System/Library/Sounds/Sosumi.aiff
            else
                osascript -e 'beep 2' || echo -e '\a'
            fi
            ;;
        "beep")
            # System beep
            if command -v osascript >/dev/null 2>&1; then
                osascript -e 'beep'
            else
                echo -e '\a'
            fi
            ;;
        "loud")
            # Multiple beeps
            if command -v osascript >/dev/null 2>&1; then
                osascript -e 'beep 3'
            else
                echo -e '\a\a\a'
            fi
            ;;
        *)
            # Default to beep
            if command -v osascript >/dev/null 2>&1; then
                osascript -e 'beep'
            else
                echo -e '\a'
            fi
            ;;
    esac
fi