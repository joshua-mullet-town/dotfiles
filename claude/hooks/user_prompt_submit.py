#!/usr/bin/env python3
"""
UserPromptSubmit Hook - Message Assistant
Captures the user's prompt and appends to conversation history (last 50 exchanges).
Also writes session status to ~/.claude/sessions/ for Whisper Village.
"""

import json
import sys
import os
import datetime
import hashlib
import subprocess
from typing import Optional

MAX_EXCHANGES = 50  # Keep last 50 user/assistant pairs
DEBUG_LOG = "/tmp/claude-debug-user-prompt.log"

# ALWAYS-ON logging for debugging - remove after fixing the issue
VERBOSE_DEBUG = True

def verbose_log(message):
    """Always-on verbose logging to debug assistant response capture issue."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()

def debug_log(message):
    """Log debugging info with timestamp (only if CLAUDE_HOOK_DEBUG=1)"""
    if os.environ.get("CLAUDE_HOOK_DEBUG") != "1":
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()


def get_tmux_session_name() -> Optional[str]:
    """Get the current tmux session name if running inside tmux.

    Returns the actual session name (e.g., 'holler-GiveGrove--prod-debug')
    or None if not in tmux.
    """
    # Check if we're in tmux
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
            session_name = result.stdout.strip()
            debug_log(f"Detected tmux session: {session_name}")
            return session_name
    except Exception as e:
        debug_log(f"Failed to get tmux session name: {e}")

    return None


def write_session_file(session_id: str, cwd: str, status: str, summary: str = None):
    """Write session state to ~/.claude/sessions/ for Whisper Village to read."""
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    # Use a hash of cwd as filename to avoid path issues
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:12]
    session_file = os.path.join(sessions_dir, f"{cwd_hash}.json")

    # Read existing summary if available
    existing_summary = summary
    if not existing_summary and os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                existing_data = json.load(f)
                existing_summary = existing_data.get("summary")
        except:
            pass

    # Get actual tmux session name for proper matching
    tmux_session = get_tmux_session_name()

    session_data = {
        "sessionId": session_id,
        "cwd": cwd,
        "status": status,
        "tmuxSession": tmux_session,  # The actual tmux session name
        "summary": existing_summary,
        "updatedAt": datetime.datetime.now().isoformat()
    }

    try:
        with open(session_file, "w") as f:
            json.dump(session_data, f, indent=2)
        debug_log(f"Wrote session file: {session_file} (status: {status}, tmux: {tmux_session})")
        # ALWAYS log session file writes to /tmp for debugging
        with open("/tmp/session-status-debug.log", "a") as dbg:
            dbg.write(f"{datetime.datetime.now().isoformat()} WRITE: {session_file} status={status} cwd={cwd}\n")
    except Exception as e:
        debug_log(f"Error writing session file: {e}")
        with open("/tmp/session-status-debug.log", "a") as dbg:
            dbg.write(f"{datetime.datetime.now().isoformat()} ERROR: {e}\n")

def main():
    start_time = datetime.datetime.now()
    verbose_log(f"")
    verbose_log(f"{'='*60}")
    verbose_log(f"USER_PROMPT_SUBMIT HOOK STARTED at {start_time.strftime('%H:%M:%S.%f')}")
    verbose_log(f"{'='*60}")

    # Log environment
    verbose_log(f"TMUX env: {os.environ.get('TMUX', 'NOT SET')}")
    verbose_log(f"PWD env: {os.environ.get('PWD', 'NOT SET')}")
    verbose_log(f"CWD: {os.getcwd()}")

    # Prevent recursive hook execution from nested claude CLI calls
    if os.environ.get("CLAUDE_HOOK_SKIP") == "1":
        verbose_log("CLAUDE_HOOK_SKIP detected, exiting immediately")
        sys.exit(0)

    # Skip for ephemeral workers - they shouldn't write to conversation files
    if os.environ.get("EPHEMERAL_WORKER") == "1":
        verbose_log("EPHEMERAL_WORKER detected, skipping conversation file updates")
        sys.exit(0)

    # Ensure common binary locations are in PATH (hooks may run with stripped environment)
    extra_paths = [
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.claude/local"),
        "/usr/local/bin",
        os.path.expanduser("~/.npm-global/bin"),
    ]
    current_path = os.environ.get("PATH", "")
    for p in extra_paths:
        if p not in current_path:
            current_path = f"{p}:{current_path}"
    os.environ["PATH"] = current_path

    after_path = datetime.datetime.now()
    debug_log(f"Path setup took: {(after_path - start_time).total_seconds():.4f}s")

    try:
        stdin_data = sys.stdin.read()
        after_stdin = datetime.datetime.now()
        verbose_log(f"Reading stdin took: {(after_stdin - after_path).total_seconds():.4f}s")
        verbose_log(f"stdin_data length: {len(stdin_data)}")

        input_data = json.loads(stdin_data)
        after_parse = datetime.datetime.now()
        verbose_log(f"Parsing JSON took: {(after_parse - after_stdin).total_seconds():.4f}s")
        verbose_log(f"input_data keys: {list(input_data.keys())}")
    except json.JSONDecodeError as e:
        verbose_log(f"JSON decode error: {e}")
        sys.exit(0)
    except Exception as e:
        verbose_log(f"Unexpected error reading input: {e}")
        sys.exit(0)

    prompt = input_data.get("prompt", "")
    session_id = input_data.get("session_id", "unknown")
    reported_cwd = input_data.get("cwd", os.getcwd())

    # Claude Code sometimes reports wrong cwd (e.g., production path instead of worktree)
    # Get the REAL cwd from the tmux pane if available
    cwd = reported_cwd
    try:
        tmux_pane = os.environ.get("TMUX_PANE")
        if tmux_pane:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "-t", tmux_pane, "#{pane_current_path}"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                real_cwd = result.stdout.strip()
                if real_cwd != reported_cwd:
                    verbose_log(f"CWD MISMATCH: Claude reported {reported_cwd}, tmux says {real_cwd}")
                    with open("/tmp/session-status-debug.log", "a") as dbg:
                        dbg.write(f"{datetime.datetime.now().isoformat()} CWD_FIX: {reported_cwd} -> {real_cwd}\n")
                cwd = real_cwd
    except Exception as e:
        verbose_log(f"Failed to get tmux pane cwd: {e}")

    verbose_log(f"Extracted values:")
    verbose_log(f"  prompt: '{prompt[:100]}...'")
    verbose_log(f"  session_id: {session_id}")
    verbose_log(f"  cwd: {cwd} (reported: {reported_cwd})")

    if not prompt:
        debug_log("No prompt provided, exiting")
        sys.exit(0)

    # Get actual tmux session name (e.g., holler-GiveGrove--prod-debug)
    # This is the authoritative name, not derived from cwd
    project_name = os.path.basename(cwd) if cwd else "unknown"
    tmux_session_name = get_tmux_session_name()

    # Fallback to old behavior if not in tmux
    if not tmux_session_name:
        # Before falling back to holler-{project}, check if we're an ephemeral worker
        # that somehow lost its TMUX env var. This prevents conversation file contamination.
        ephemeral_registry_file = "/tmp/ephemeral-workers.json"
        if os.path.exists(ephemeral_registry_file):
            try:
                with open(ephemeral_registry_file, "r") as f:
                    registry = json.load(f)
                # If there are any ephemeral workers registered and we're in homestead dir,
                # we're likely an ephemeral worker that lost its TMUX env. Skip to be safe.
                # Ephemeral workers run from homestead and shouldn't write to user conversation files.
                if registry.get("sessions") and cwd and ("homestead" in cwd or "steward" in cwd):
                    debug_log(f"No TMUX env but ephemeral workers exist and cwd contains 'homestead' or 'steward' - likely ephemeral worker, skipping")
                    write_session_file(session_id, cwd, "working")
                    sys.exit(0)
            except Exception as e:
                debug_log(f"Error checking ephemeral registry: {e}")

        tmux_session_name = f"holler-{project_name}"
        debug_log(f"Not in tmux, using fallback session name: {tmux_session_name}")
    else:
        debug_log(f"Using actual tmux session name: {tmux_session_name}")

    # Skip conversation logging for ephemeral workers - they pollute user session files
    if tmux_session_name.startswith("ephemeral-"):
        debug_log(f"Ephemeral session detected, skipping conversation logging")
        # Still write session status for activity tracking, but skip conversation files
        write_session_file(session_id, cwd, "working")
        sys.exit(0)

    # Primary file keyed by actual tmux session name (prevents cross-session mixing)
    session_file = f"/tmp/claude-session-{tmux_session_name}-conversation.json"
    # Legacy files for backwards compatibility
    temp_file = f"/tmp/claude-{session_id}-conversation.json"
    project_file = f"/tmp/claude-project-{project_name}-conversation.json"

    verbose_log(f"File paths:")
    verbose_log(f"  session_file: {session_file}")
    verbose_log(f"  temp_file: {temp_file}")
    verbose_log(f"  project_file: {project_file}")

    before_file_ops = datetime.datetime.now()

    # Load existing conversation or start fresh
    conversation = {
        "cwd": cwd,
        "session_id": session_id,
        "project_name": project_name,
        "tmux_session": tmux_session_name,
        "exchanges": []  # List of {"user": ..., "assistant": ...}
    }

    # Only load from the tmux-session-keyed file (primary source of truth)
    # Legacy files are written for backwards compat but should NOT be used as input
    # to avoid cross-session contamination from stale UUID-based files
    loaded = False
    verbose_log(f"Checking if session_file exists: {os.path.exists(session_file)}")
    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                conversation = json.load(f)
                conversation["session_id"] = session_id  # Update to current session
                conversation["project_name"] = project_name
                conversation["tmux_session"] = tmux_session_name
            after_file_read = datetime.datetime.now()
            verbose_log(f"Loaded existing conversation: {len(conversation.get('exchanges', []))} exchanges")
            verbose_log(f"Reading took: {(after_file_read - before_file_ops).total_seconds():.4f}s")
            loaded = True
        except (json.JSONDecodeError, FileNotFoundError) as e:
            verbose_log(f"Error loading conversation from {session_file}: {e}")

    if not loaded:
        verbose_log("Creating new conversation file")

    # Add new user message as pending exchange
    new_exchange = {
        "user": prompt,
        "assistant": None  # Will be filled by Stop hook
    }
    conversation["exchanges"].append(new_exchange)
    verbose_log(f"Added new exchange with assistant=None. Total exchanges: {len(conversation['exchanges'])}")

    # Keep only last N exchanges
    conversation["exchanges"] = conversation["exchanges"][-MAX_EXCHANGES:]
    conversation["cwd"] = cwd  # Update in case it changed

    before_write = datetime.datetime.now()

    try:
        # Write to tmux-session-keyed file (primary) and legacy files for backwards compat
        with open(session_file, "w") as f:
            json.dump(conversation, f)
        with open(temp_file, "w") as f:
            json.dump(conversation, f)
        with open(project_file, "w") as f:
            json.dump(conversation, f)
        after_write = datetime.datetime.now()
        debug_log(f"Writing conversation files took: {(after_write - before_write).total_seconds():.4f}s")
    except Exception as e:
        debug_log(f"Error writing conversation file: {e}")

    # Write session file with "working" status for Whisper Village
    before_session = datetime.datetime.now()
    write_session_file(session_id, cwd, "working")
    after_session = datetime.datetime.now()
    debug_log(f"Writing session file took: {(after_session - before_session).total_seconds():.4f}s")

    # Initialize activity file with "Thinking..." state for Homestead activity stream
    activity_file = f"/tmp/claude-session-{tmux_session_name}-activity.json"
    activity = {
        "tmux_session": tmux_session_name,
        "session_id": session_id,
        "cwd": cwd,
        "is_working": True,
        "current_tool": None,
        "activities": [
            {
                "id": "thinking-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "tool": "thinking",
                "phase": "start",
                "message": "Thinking...",
                "timestamp": datetime.datetime.now().isoformat()
            }
        ],
        "updated_at": datetime.datetime.now().isoformat()
    }
    try:
        with open(activity_file, "w") as f:
            json.dump(activity, f)
        debug_log(f"Initialized activity file: {activity_file}")
    except Exception as e:
        debug_log(f"Error writing activity file: {e}")

    end_time = datetime.datetime.now()
    total_time = (end_time - start_time).total_seconds()
    verbose_log(f"UserPromptSubmit Hook FINISHED - Total time: {total_time:.4f}s")
    verbose_log(f"{'='*60}")
    sys.exit(0)


if __name__ == "__main__":
    main()
