#!/usr/bin/env python3
"""
Tool Activity Hook - Tracks tool usage for live activity streaming
Handles both PreToolUse and PostToolUse events.
Writes activity to /tmp/claude-session-{tmux_session}-activity.json
"""

import json
import sys
import os
import subprocess
from datetime import datetime
from typing import Optional

DEBUG_LOG = "/tmp/claude-debug-activity.log"

def debug_log(message):
    """Log debugging info with timestamp (only if CLAUDE_HOOK_DEBUG=1)"""
    if os.environ.get("CLAUDE_HOOK_DEBUG") != "1":
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()


def get_tmux_session_name() -> Optional[str]:
    """Get the current tmux session name if running inside tmux."""
    if not os.environ.get("TMUX"):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        debug_log(f"Failed to get tmux session: {e}")
    return None


def format_tool_activity(tool_name: str, tool_input: dict, phase: str, tool_response: str = None) -> str:
    """Format tool activity into a human-readable string."""

    # Tool-specific formatting
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        if phase == "start":
            return f"Running: {desc}" if desc else f"$ {cmd[:80]}..."
        else:
            # For completion, show brief result
            if tool_response:
                lines = tool_response.strip().split('\n')
                if len(lines) > 3:
                    return f"Completed ({len(lines)} lines output)"
                return f"Done"
            return "Done"

    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        filename = os.path.basename(path) if path else "file"
        return f"Reading {filename}" if phase == "start" else f"Read {filename}"

    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        filename = os.path.basename(path) if path else "file"
        return f"Writing {filename}" if phase == "start" else f"Wrote {filename}"

    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        filename = os.path.basename(path) if path else "file"
        return f"Editing {filename}" if phase == "start" else f"Edited {filename}"

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "*")
        return f"Finding files: {pattern}" if phase == "start" else "Found files"

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"Searching: {pattern[:40]}" if phase == "start" else "Search complete"

    elif tool_name == "Task":
        desc = tool_input.get("description", "")
        return f"Agent: {desc}" if phase == "start" else f"Agent done: {desc}"

    elif tool_name == "WebFetch":
        url = tool_input.get("url", "")
        return f"Fetching: {url[:50]}" if phase == "start" else "Fetched"

    elif tool_name == "WebSearch":
        query = tool_input.get("query", "")
        return f"Searching: {query[:40]}" if phase == "start" else "Search done"

    elif tool_name == "TodoWrite":
        return "Updating todos" if phase == "start" else "Todos updated"

    elif tool_name.startswith("mcp__"):
        # MCP tool - extract readable name
        parts = tool_name.split("__")
        if len(parts) >= 3:
            server = parts[1]
            action = parts[2]
            return f"{server}: {action}" if phase == "start" else f"{server}: done"
        return f"{tool_name}" if phase == "start" else "Done"

    else:
        return f"{tool_name}" if phase == "start" else f"{tool_name} done"


def main():
    debug_log("Tool activity hook started")

    # Skip if hook skip is set (nested claude calls)
    if os.environ.get("CLAUDE_HOOK_SKIP") == "1":
        debug_log("CLAUDE_HOOK_SKIP set, exiting")
        sys.exit(0)

    try:
        stdin_data = sys.stdin.read()
        input_data = json.loads(stdin_data)
    except Exception as e:
        debug_log(f"Error reading input: {e}")
        sys.exit(0)

    hook_event = input_data.get("hook_event_name", "")
    session_id = input_data.get("session_id", "unknown")
    cwd = input_data.get("cwd", os.getcwd())
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    tool_response = input_data.get("tool_response", "")
    tool_use_id = input_data.get("tool_use_id", "")

    debug_log(f"Event: {hook_event}, Tool: {tool_name}, ID: {tool_use_id}")

    # Determine phase
    if hook_event == "PreToolUse":
        phase = "start"
    elif hook_event in ("PostToolUse", "PostToolUseFailure"):
        phase = "complete"
    else:
        debug_log(f"Unknown hook event: {hook_event}")
        sys.exit(0)

    # Get tmux session name
    tmux_session = get_tmux_session_name()
    if not tmux_session:
        project_name = os.path.basename(cwd) if cwd else "unknown"
        tmux_session = f"holler-{project_name}"

    # Activity file path
    activity_file = f"/tmp/claude-session-{tmux_session}-activity.json"

    # Load existing activity
    activity = {
        "tmux_session": tmux_session,
        "session_id": session_id,
        "cwd": cwd,
        "is_working": True,
        "current_tool": None,
        "activities": [],
        "updated_at": datetime.now().isoformat()
    }

    if os.path.exists(activity_file):
        try:
            with open(activity_file, "r") as f:
                activity = json.load(f)
        except:
            pass

    # Format activity message
    message = format_tool_activity(tool_name, tool_input, phase, tool_response)

    # Create activity entry
    entry = {
        "id": tool_use_id,
        "tool": tool_name,
        "phase": phase,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }

    # Update activity state
    if phase == "start":
        activity["current_tool"] = tool_name
        activity["is_working"] = True
        # Mark any "Thinking..." entry as complete when first real tool starts
        for act in activity["activities"]:
            if act.get("tool") == "thinking" and act.get("phase") == "start":
                act["phase"] = "complete"
                act["message"] = "Done thinking"
                act["completed_at"] = datetime.now().isoformat()
        # Add to activities list (keep last 20)
        activity["activities"].append(entry)
        activity["activities"] = activity["activities"][-20:]
    else:
        activity["current_tool"] = None
        # Update the matching start entry or add completion
        found = False
        for i, act in enumerate(activity["activities"]):
            if act.get("id") == tool_use_id and act.get("phase") == "start":
                # Update existing entry with completion info
                activity["activities"][i]["phase"] = "complete"
                activity["activities"][i]["message"] = message
                activity["activities"][i]["completed_at"] = datetime.now().isoformat()
                found = True
                break
        if not found:
            activity["activities"].append(entry)
            activity["activities"] = activity["activities"][-20:]

    activity["updated_at"] = datetime.now().isoformat()

    # Write activity file
    try:
        with open(activity_file, "w") as f:
            json.dump(activity, f)
        debug_log(f"Wrote activity to {activity_file}")
    except Exception as e:
        debug_log(f"Error writing activity: {e}")

    sys.exit(0)


if __name__ == "__main__":
    main()
