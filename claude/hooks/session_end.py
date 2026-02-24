#!/usr/bin/env python3
"""
SessionEnd Hook - Marks session as terminated.
Writes status: "terminated" to ~/.claude/sessions/ when a Claude session exits.
"""

import json
import sys
import os
import datetime
import hashlib
import subprocess
from typing import Optional


def get_tmux_session_name() -> Optional[str]:
    """Get the current tmux session name if running inside tmux."""
    if not os.environ.get("TMUX"):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def write_session_file(session_id: str, cwd: str, status: str):
    """Write session state to ~/.claude/sessions/."""
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:12]
    session_file = os.path.join(sessions_dir, f"{cwd_hash}.json")

    # Preserve existing summary
    existing_summary = None
    existing_user_summary = None
    existing_agent_summary = None
    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                existing_data = json.load(f)
                existing_summary = existing_data.get("summary")
                existing_user_summary = existing_data.get("userSummary")
                existing_agent_summary = existing_data.get("agentSummary")
        except Exception:
            pass

    tmux_session = get_tmux_session_name()

    session_data = {
        "sessionId": session_id,
        "cwd": cwd,
        "status": status,
        "tmuxSession": tmux_session,
        "summary": existing_summary,
        "userSummary": existing_user_summary,
        "agentSummary": existing_agent_summary,
        "updatedAt": datetime.datetime.now().isoformat()
    }

    try:
        with open(session_file, "w") as f:
            json.dump(session_data, f, indent=2)
        with open("/tmp/session-status-debug.log", "a") as dbg:
            dbg.write(f"{datetime.datetime.now().isoformat()} SESSION_END: {session_file} status={status} cwd={cwd}\n")
    except Exception as e:
        with open("/tmp/session-status-debug.log", "a") as dbg:
            dbg.write(f"{datetime.datetime.now().isoformat()} SESSION_END ERROR: {e}\n")


def main():
    # Skip for nested/ephemeral workers
    if os.environ.get("CLAUDE_HOOK_SKIP") == "1":
        sys.exit(0)
    if os.environ.get("EPHEMERAL_WORKER") == "1":
        sys.exit(0)

    try:
        stdin_data = sys.stdin.read()
        input_data = json.loads(stdin_data)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    session_id = input_data.get("session_id", "")
    cwd = input_data.get("cwd", os.getcwd())

    write_session_file(session_id, cwd, "terminated")


if __name__ == "__main__":
    main()
