#!/usr/bin/env python3
"""
Stop Hook - Session Summary Generator
Reads the transcript, extracts last assistant response, includes project context
(CLAUDE.md and PLAN.md), calls Claude Code CLI (haiku) to generate a summary, and saves to the project.
"""

import json
import re
import sys
import os
import subprocess
import pty
import select
import time
from datetime import datetime
from typing import Optional

# Use Claude Code CLI instead of local Ollama for better quality summaries
CLAUDE_MODEL = "haiku"  # Fast and cheap, good for summaries
DEBUG_LOG = "/tmp/claude-debug-stop.log"

# ALWAYS-ON logging for debugging - remove after fixing the issue
VERBOSE_DEBUG = True

def verbose_log(message):
    """Always-on verbose logging to debug assistant response capture issue."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    with open(DEBUG_LOG, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
        f.flush()

def find_claude_cli() -> str:
    """Find the claude CLI binary, checking common locations."""
    import shutil
    # Check PATH first
    found = shutil.which("claude")
    if found:
        return found
    # Common install locations
    common_paths = [
        os.path.expanduser("~/.claude/local/claude"),
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
        os.path.expanduser("~/.npm-global/bin/claude"),
    ]
    for path in common_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return "claude"  # Fallback, hope it's in PATH

def debug_log(message):
    """Log debugging info with timestamp (only if CLAUDE_HOOK_DEBUG=1)"""
    if os.environ.get("CLAUDE_HOOK_DEBUG") != "1":
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
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
    """Write session state to ~/.claude/sessions/ for Whisper Village to read.

    Summary can be either:
    - A plain string (legacy format): "USER asked: ...\nAGENT: ..."
    - A JSON string: {"user_summary": "...", "agent_summary": "..."}
    """
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    # Use a hash of cwd as filename to avoid path issues
    import hashlib
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:12]
    session_file = os.path.join(sessions_dir, f"{cwd_hash}.json")

    # Try to parse summary as JSON for structured format
    user_summary = None
    agent_summary = None
    if summary:
        # Strip markdown code fences if present
        clean_summary = summary.strip()
        if clean_summary.startswith("```"):
            # Remove opening fence (```json or ```)
            lines = clean_summary.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_summary = "\n".join(lines).strip()

        try:
            parsed = json.loads(clean_summary)
            if isinstance(parsed, dict):
                user_summary = parsed.get("user_summary")
                agent_summary = parsed.get("agent_summary")
                debug_log(f"Parsed structured summary: user={user_summary[:50] if user_summary else None}...")
        except json.JSONDecodeError:
            debug_log(f"JSON parse failed, trying legacy format")
            # Legacy format - try to extract from "USER asked: ...\nAGENT: ..."
            lines = summary.strip().split("\n")
            for line in lines:
                if line.startswith("USER"):
                    user_summary = line.replace("USER asked:", "").replace("USER asked", "").replace("USER:", "").strip()
                elif line.startswith("AGENT"):
                    agent_summary = line.replace("AGENT:", "").strip()

    # Get actual tmux session name for proper matching
    tmux_session = get_tmux_session_name()

    session_data = {
        "sessionId": session_id,
        "cwd": cwd,
        "status": status,
        "read": False,  # Mark as unread when agent responds
        "tmuxSession": tmux_session,  # The actual tmux session name (e.g., holler-GiveGrove--prod-debug)
        "summary": summary,  # Keep raw for backwards compat
        "userSummary": user_summary,
        "agentSummary": agent_summary,
        "updatedAt": datetime.now().isoformat()
    }

    try:
        with open(session_file, "w") as f:
            json.dump(session_data, f, indent=2)
        debug_log(f"Wrote session file: {session_file}")
    except Exception as e:
        debug_log(f"Error writing session file: {e}")


def read_project_context(cwd: str) -> dict:
    """Read CLAUDE.md and PLAN.md for project context."""
    context = {
        "claude_md": "",
        "plan_md": "",
        "current_task": ""
    }

    # Read CLAUDE.md (project instructions)
    claude_path = os.path.join(cwd, "CLAUDE.md")
    if os.path.exists(claude_path):
        try:
            with open(claude_path, "r") as f:
                content = f.read()
                # Take first 2000 chars - usually has project name and key info
                context["claude_md"] = content[:2000]
        except Exception:
            pass

    # Read PLAN.md
    plan_path = os.path.join(cwd, "PLAN.md")
    if os.path.exists(plan_path):
        try:
            with open(plan_path, "r") as f:
                content = f.read()
                context["plan_md"] = content[:3000]

                # Extract just the CURRENT section for focused context
                match = re.search(r'## CURRENT[:\s].*?(?=\n## |\n---|\Z)', content, re.DOTALL | re.IGNORECASE)
                if match:
                    context["current_task"] = match.group(0).strip()[:1000]
        except Exception:
            pass

    return context


def extract_last_assistant_response(transcript_path: str) -> str:
    """Extract the last assistant response from JSONL transcript.

    Strategy:
    1. Only look at the LAST 200 lines of the transcript (recent context)
    2. Find the last assistant message with text content
    3. Skip tool_use messages (intermediate, tool call follows)

    We don't rely on stop_reason='end_turn' because long-running sessions
    may have stale end_turn messages from hours ago that would incorrectly
    be preferred over recent responses.
    """
    verbose_log(f"=== extract_last_assistant_response START ===")
    verbose_log(f"transcript_path: {transcript_path}")

    if not transcript_path:
        verbose_log("ABORT: transcript_path is empty/None")
        return ""

    if not os.path.exists(transcript_path):
        verbose_log(f"ABORT: transcript_path does not exist: {transcript_path}")
        return ""

    verbose_log(f"Transcript file exists, size: {os.path.getsize(transcript_path)} bytes")

    try:
        # Read only the last 200 lines for efficiency and to avoid stale data
        with open(transcript_path, "r") as f:
            lines = f.readlines()

        verbose_log(f"Total lines in transcript: {len(lines)}")
        recent_lines = lines[-200:] if len(lines) > 200 else lines
        verbose_log(f"Processing last {len(recent_lines)} lines")

        last_text_response = ""
        assistant_count = 0
        tool_use_count = 0
        text_response_count = 0

        for i, line in enumerate(recent_lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_type = entry.get("type")

                if entry_type == "assistant":
                    assistant_count += 1
                    message = entry.get("message", {})
                    stop_reason = message.get("stop_reason")

                    # Skip tool_use - these are intermediate (Claude is about to call a tool)
                    if stop_reason == "tool_use":
                        tool_use_count += 1
                        continue

                    content = message.get("content", [])
                    if isinstance(content, list):
                        texts = []
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                texts.append(c.get("text", ""))
                        if texts:
                            text_response_count += 1
                            # Always use the latest text response
                            last_text_response = "\n".join(texts)
                            verbose_log(f"Found text response #{text_response_count} at line {i}, stop_reason={stop_reason}, len={len(last_text_response)}")
            except json.JSONDecodeError as e:
                verbose_log(f"JSON decode error at line {i}: {e}")
                continue

        verbose_log(f"Summary: assistant_entries={assistant_count}, tool_use_skipped={tool_use_count}, text_responses={text_response_count}")
        verbose_log(f"Final response length: {len(last_text_response)}")
        if last_text_response:
            verbose_log(f"Final response preview: {last_text_response[:200]}...")
        else:
            verbose_log("NO RESPONSE FOUND!")
        verbose_log(f"=== extract_last_assistant_response END ===")
        return last_text_response
    except Exception as e:
        verbose_log(f"EXCEPTION in extract_last_assistant_response: {type(e).__name__}: {e}")
        import traceback
        verbose_log(traceback.format_exc())
        return ""


def build_conversation_text(exchanges: list) -> str:
    """Build formatted conversation text from exchanges."""
    parts = []
    for ex in exchanges:
        if ex.get("user") and ex.get("assistant"):
            # Only include complete exchanges
            parts.append(f"USER: {ex['user']}\nAGENT: {ex['assistant']}")
    return "\n\n".join(parts)


def generate_summary(conversation_text: str, project_context: dict) -> str:
    """Call Claude Code CLI to generate a brief 2-line summary with project context."""
    # Truncate conversation if too long
    max_conversation_len = 6000
    if len(conversation_text) > max_conversation_len:
        conversation_text = conversation_text[:max_conversation_len] + "..."

    # Build context section
    context_parts = []
    if project_context.get("current_task"):
        context_parts.append(f"CURRENT TASK:\n{project_context['current_task']}")
    elif project_context.get("plan_md"):
        context_parts.append(f"PROJECT PLAN:\n{project_context['plan_md'][:500]}")

    if project_context.get("claude_md"):
        # Extract just the project name/description from CLAUDE.md
        claude_excerpt = project_context["claude_md"][:500]
        context_parts.append(f"PROJECT INFO:\n{claude_excerpt}")

    context_section = "\n\n".join(context_parts) if context_parts else ""

    summary_prompt = f"""Summarize this coding session in MINIMAL words.
{f"{chr(10)}PROJECT: {context_section[:300]}{chr(10)}" if context_section else ""}
CONVERSATION:
{conversation_text}

CRITICAL: Be EXTREMELY concise. Max 8-10 words each. No filler words. Telegraph style.

Respond with ONLY valid JSON, no markdown, no code fences:
{{"user_summary": "max 10 words - what user wanted", "agent_summary": "max 10 words - what was done"}}

Examples of good summaries:
- "user_summary": "Add dark mode toggle"
- "agent_summary": "Implemented theme switcher in settings"

- "user_summary": "Fix login crash on iOS"
- "agent_summary": "Fixed nil pointer in auth flow"

Be this concise."""

    try:
        # Find claude CLI (handles pyenv/homebrew/npm path issues)
        claude_bin = find_claude_cli()
        debug_log(f"Using claude CLI: {claude_bin}")

        # Call Claude Code CLI in one-shot mode using PTY to prevent /dev/tty blocking
        # Claude opens /dev/tty directly causing hangs - we detach from controlling terminal
        # See: https://github.com/anthropics/claude-code/issues/13598
        env = os.environ.copy()
        # CRITICAL: Disable hooks for this nested Claude call to prevent infinite recursion
        env["CLAUDE_HOOK_SKIP"] = "1"

        before_claude = datetime.now()
        debug_log("Creating PTY for claude CLI call...")

        try:
            # Create pseudo-terminal pair
            master_fd, slave_fd = pty.openpty()
            debug_log(f"PTY created: master={master_fd}, slave={slave_fd}")

            # Spawn claude with PTY and detach from controlling terminal
            process = subprocess.Popen(
                [
                    claude_bin, "-p",
                    "--model", CLAUDE_MODEL,
                    "--no-session-persistence",  # Don't save this as a session
                    summary_prompt
                ],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,  # CRITICAL: Detach from controlling terminal (prevents /dev/tty access)
                env=env,
                close_fds=False  # Keep slave fd open for child
            )
            debug_log(f"Process spawned with PID={process.pid}")

            # Close slave fd in parent (child keeps it open)
            os.close(slave_fd)

            # Make master fd non-blocking
            os.set_blocking(master_fd, False)

            # Read from master fd with timeout
            output_bytes = b""
            timeout_duration = 90  # Increased from 15s - claude -p takes 40-50s even for simple prompts
            timeout_start = time.time()
            poll_interval = 0.1

            debug_log(f"Starting read loop with {timeout_duration}s timeout...")
            while time.time() - timeout_start < timeout_duration:
                # Check if process is still running
                if process.poll() is not None:
                    debug_log(f"Process exited with code {process.returncode}")
                    # Process finished, do final read
                    try:
                        while True:
                            chunk = os.read(master_fd, 4096)
                            if not chunk:
                                break
                            output_bytes += chunk
                    except (BlockingIOError, OSError):
                        pass
                    break

                # Try to read data
                try:
                    chunk = os.read(master_fd, 4096)
                    if chunk:
                        output_bytes += chunk
                        debug_log(f"Read {len(chunk)} bytes (total: {len(output_bytes)})")
                except BlockingIOError:
                    # No data available yet
                    time.sleep(poll_interval)
                except OSError as e:
                    debug_log(f"OSError during read: {e}")
                    break

            # Close master fd
            os.close(master_fd)

            # Check for timeout
            if process.poll() is None:
                debug_log("TIMEOUT - killing process")
                process.kill()
                process.wait()
                return f"USER asked: (see conversation)\nAGENT: (Claude CLI timeout after {timeout_duration}s)"

            # Process finished successfully
            after_claude = datetime.now()
            elapsed = (after_claude - before_claude).total_seconds()
            debug_log(f"Claude CLI took: {elapsed:.4f}s")

            # Decode output and strip ANSI escape codes from PTY
            stdout = output_bytes.decode('utf-8', errors='replace')
            # Remove ANSI escape sequences in multiple passes
            # Pass 1: Remove full ANSI sequences (ESC-based)
            ansi_escape_1 = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1B]*(?:\x07|\x1B\\))')
            stdout_temp = ansi_escape_1.sub('', stdout)
            # Pass 2: Remove trailing terminal garbage lines (e.g., "9;4;0;" with BEL)
            ansi_escape_2 = re.compile(r'\r?\n[0-9;]+[\x00-\x1F]*$')
            stdout_clean = ansi_escape_2.sub('', stdout_temp)
            debug_log(f"Claude CLI finished with returncode={process.returncode}, stdout_len={len(stdout)}, clean_len={len(stdout_clean)}")

            if process.returncode == 0 and stdout_clean.strip():
                # Success
                clean_output = stdout_clean.strip()
                debug_log(f"SUCCESS - got output: {clean_output[:100]}")
                return clean_output
            else:
                debug_log(f"Claude CLI error: returncode={process.returncode}")
                debug_log(f"stdout: {stdout_clean[:500]}")
                return f"USER asked: (see conversation)\nAGENT: (Claude CLI error: {process.returncode})"

        except Exception as e:
            debug_log(f"Exception in PTY handling: {type(e).__name__}: {e}")
            return f"USER asked: (see conversation)\nAGENT: (PTY error: {e})"

    except FileNotFoundError:
        debug_log(f"Claude CLI NOT FOUND at: {claude_bin}")
        return "USER asked: (see conversation)\nAGENT: (Claude CLI not found)"
    except Exception as e:
        debug_log(f"Claude CLI exception: {e}")
        return f"USER asked: (see conversation)\nAGENT: (error: {e})"


def _run_summary_pipeline(session_id: str, transcript_path: str, cwd_from_input: str):
    """Run the full summary pipeline. Raises on failure so caller can handle."""
    verbose_log(f"")
    verbose_log(f"--- _run_summary_pipeline START ---")
    verbose_log(f"  session_id: {session_id}")
    verbose_log(f"  transcript_path: {transcript_path}")
    verbose_log(f"  cwd_from_input: {cwd_from_input}")

    # Get actual tmux session name (e.g., holler-GiveGrove--prod-debug)
    # This is the authoritative name, not derived from cwd
    tmux_session_name = get_tmux_session_name()
    verbose_log(f"  tmux_session_name from get_tmux_session_name(): {tmux_session_name}")

    # Fallback to old behavior if not in tmux
    project_name = os.path.basename(cwd_from_input) if cwd_from_input else "unknown"
    verbose_log(f"  project_name: {project_name}")
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
                if registry.get("sessions") and cwd_from_input and ("homestead" in cwd_from_input or "steward" in cwd_from_input):
                    debug_log(f"No TMUX env but ephemeral workers exist and cwd contains 'homestead' or 'steward' - likely ephemeral worker, skipping")
                    return
            except Exception as e:
                debug_log(f"Error checking ephemeral registry: {e}")

        tmux_session_name = f"holler-{project_name}"
        debug_log(f"Not in tmux, using fallback session name: {tmux_session_name}")
    else:
        debug_log(f"Using actual tmux session name: {tmux_session_name}")

    # Skip conversation file updates for ephemeral workers - they pollute user session files
    # But DO kill the session before returning
    if tmux_session_name.startswith("ephemeral-"):
        debug_log(f"Ephemeral session detected, skipping summary pipeline")
        # Kill the ephemeral session
        ephemeral_registry_file = "/tmp/ephemeral-workers.json"
        if os.path.exists(ephemeral_registry_file):
            try:
                with open(ephemeral_registry_file, "r") as f:
                    registry = json.load(f)
                if tmux_session_name in registry.get("sessions", []):
                    debug_log(f"Ephemeral worker in registry: {tmux_session_name}")
                    # Remove from registry first
                    registry["sessions"] = [s for s in registry["sessions"] if s != tmux_session_name]
                    with open(ephemeral_registry_file, "w") as f:
                        json.dump(registry, f, indent=2)
                    debug_log(f"Removed {tmux_session_name} from ephemeral registry")
                    # Kill the tmux session (fork to background so hook exits fast)
                    subprocess.Popen(
                        ["tmux", "kill-session", "-t", tmux_session_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    debug_log(f"Sent kill command for tmux session: {tmux_session_name}")
            except Exception as e:
                debug_log(f"Error killing ephemeral session: {e}")
        return

    # Primary file keyed by actual tmux session name
    session_file = f"/tmp/claude-session-{tmux_session_name}-conversation.json"
    # Legacy files
    temp_file = f"/tmp/claude-{session_id}-conversation.json"
    project_file = f"/tmp/claude-project-{project_name}-conversation.json"

    verbose_log(f"Looking for conversation file: {session_file}")
    verbose_log(f"  File exists? {os.path.exists(session_file)}")

    # Only use the tmux-session-keyed file (primary source of truth)
    # Legacy files (temp_file, project_file) are written for backwards compat
    # but should NOT be used as input to avoid cross-session contamination
    if not os.path.exists(session_file):
        verbose_log(f"ABORT: Conversation file not found: {session_file}")
        verbose_log(f"  Checking if legacy files exist:")
        verbose_log(f"    temp_file ({temp_file}): {os.path.exists(temp_file)}")
        verbose_log(f"    project_file ({project_file}): {os.path.exists(project_file)}")
        return

    actual_file = session_file
    verbose_log(f"Using conversation file: {session_file}")

    try:
        with open(actual_file, "r") as f:
            conversation = json.load(f)
        verbose_log(f"Loaded conversation from {actual_file}: {len(conversation.get('exchanges', []))} exchanges")
    except (json.JSONDecodeError, FileNotFoundError) as e:
        verbose_log(f"Error reading conversation file: {e}")
        return

    cwd = conversation.get("cwd", cwd_from_input)
    exchanges = conversation.get("exchanges", [])
    verbose_log(f"Conversation data - cwd: {cwd}, exchanges count: {len(exchanges)}")

    if exchanges:
        last_exchange = exchanges[-1]
        verbose_log(f"Last exchange - user: {str(last_exchange.get('user', ''))[:100]}...")
        verbose_log(f"Last exchange - assistant: {str(last_exchange.get('assistant', 'NULL'))[:100]}...")

    if not cwd or not exchanges:
        verbose_log(f"ABORT: Missing required data - cwd: {bool(cwd)}, exchanges: {bool(exchanges)}")
        # Still write waiting status with no summary
        if cwd:
            write_session_file(session_id, cwd, "waiting", None)
        return

    # Extract last assistant response from transcript
    verbose_log(f"")
    verbose_log(f">>> Calling extract_last_assistant_response <<<")
    verbose_log(f"  transcript_path: {transcript_path}")
    verbose_log(f"  transcript exists: {os.path.exists(transcript_path) if transcript_path else 'N/A (empty path)'}")
    if transcript_path and os.path.exists(transcript_path):
        verbose_log(f"  transcript size: {os.path.getsize(transcript_path)} bytes")

    assistant_response = extract_last_assistant_response(transcript_path)
    verbose_log(f"<<< extract_last_assistant_response returned >>>")
    verbose_log(f"  Assistant response length: {len(assistant_response) if assistant_response else 0}")

    if not assistant_response:
        verbose_log("NO ASSISTANT RESPONSE FOUND - This is the bug!")
        verbose_log("  - Either transcript_path is wrong/empty")
        verbose_log("  - Or transcript has no assistant messages with text content")
        verbose_log("  - Marking waiting without summary")
        write_session_file(session_id, cwd, "waiting", None)
        return

    verbose_log(f"SUCCESS: Got assistant response, length={len(assistant_response)}")

    # Fill in the assistant response for the last exchange
    if exchanges and exchanges[-1].get("assistant") is None:
        exchanges[-1]["assistant"] = assistant_response
        verbose_log("Filled in assistant response for last exchange")
    else:
        verbose_log(f"Last exchange already has assistant response (not None)")

    # Save updated conversation back to all files
    conversation["exchanges"] = exchanges
    conversation["project_name"] = project_name
    conversation["tmux_session"] = tmux_session_name
    try:
        # Write to tmux-session-keyed file (primary) and legacy files
        with open(session_file, "w") as f:
            json.dump(conversation, f)
        with open(temp_file, "w") as f:
            json.dump(conversation, f)
        with open(project_file, "w") as f:
            json.dump(conversation, f)
        debug_log("Updated conversation files")
    except Exception as e:
        debug_log(f"Error updating conversation: {e}")

    # Build conversation text for summary (all complete exchanges)
    conversation_text = build_conversation_text(exchanges)
    debug_log(f"Built conversation text: {len(conversation_text)} chars")

    if not conversation_text:
        debug_log("No conversation text to summarize")
        write_session_file(session_id, cwd, "waiting", None)
        return

    # Read project context (CLAUDE.md and PLAN.md)
    debug_log(f"Reading project context from: {cwd}")
    project_context = read_project_context(cwd)
    debug_log(f"Project context loaded - claude_md: {len(project_context.get('claude_md', ''))}, plan_md: {len(project_context.get('plan_md', ''))}")

    # Generate summary using Claude Haiku
    debug_log("Calling Claude Haiku to generate summary...")
    summary = generate_summary(conversation_text, project_context)
    debug_log(f"Generated summary: {len(summary)} chars")

    # Write slim summary to .claude/SUMMARY.txt (for HUD display)
    output_dir = os.path.join(cwd, ".claude")
    os.makedirs(output_dir, exist_ok=True)

    summary_path = os.path.join(output_dir, "SUMMARY.txt")
    debug_log(f"Writing summary to: {summary_path}")

    try:
        with open(summary_path, "w") as f:
            f.write(summary)
        debug_log("Successfully wrote summary file")
    except Exception as e:
        debug_log(f"Error writing summary: {e}")

    # Write session file for Whisper Village session dots
    write_session_file(session_id, cwd, "waiting", summary)


def main():
    start_time = datetime.now()
    verbose_log(f"")
    verbose_log(f"{'='*60}")
    verbose_log(f"STOP HOOK STARTED at {start_time.strftime('%H:%M:%S.%f')}")
    verbose_log(f"{'='*60}")

    # Prevent recursive hook execution from nested claude CLI calls
    if os.environ.get("CLAUDE_HOOK_SKIP") == "1":
        verbose_log("CLAUDE_HOOK_SKIP detected, exiting immediately")
        sys.exit(0)

    # Skip for ephemeral workers - they shouldn't write to conversation files
    if os.environ.get("EPHEMERAL_WORKER") == "1":
        verbose_log("EPHEMERAL_WORKER detected, skipping conversation file updates")
        sys.exit(0)

    # Log environment
    verbose_log(f"TMUX env: {os.environ.get('TMUX', 'NOT SET')}")
    verbose_log(f"PWD env: {os.environ.get('PWD', 'NOT SET')}")
    verbose_log(f"CWD: {os.getcwd()}")

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

    after_path = datetime.now()
    verbose_log(f"Path setup took: {(after_path - start_time).total_seconds():.4f}s")

    try:
        stdin_data = sys.stdin.read()
        after_stdin = datetime.now()
        verbose_log(f"Reading stdin took: {(after_stdin - after_path).total_seconds():.4f}s")
        verbose_log(f"stdin_data length: {len(stdin_data)}")
        verbose_log(f"stdin_data preview: {stdin_data[:500]}...")

        input_data = json.loads(stdin_data)
        after_parse = datetime.now()
        verbose_log(f"Parsing JSON took: {(after_parse - after_stdin).total_seconds():.4f}s")
        verbose_log(f"input_data keys: {list(input_data.keys())}")
    except json.JSONDecodeError as e:
        verbose_log(f"JSON decode error: {e}")
        verbose_log(f"stdin_data was: {stdin_data[:1000]}")
        sys.exit(0)
    except Exception as e:
        verbose_log(f"Unexpected error reading input: {type(e).__name__}: {e}")
        sys.exit(0)

    session_id = input_data.get("session_id", "unknown")
    transcript_path = input_data.get("transcript_path", "")
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
                cwd = real_cwd
    except Exception as e:
        verbose_log(f"Failed to get tmux pane cwd: {e}")

    verbose_log(f"Extracted values:")
    verbose_log(f"  session_id: {session_id}")
    verbose_log(f"  transcript_path: {transcript_path}")
    verbose_log(f"  cwd: {cwd} (reported: {reported_cwd})")

    # IMMEDIATELY mark session as "waiting" — this is the critical path
    # The dot must turn green as soon as the agent stops, regardless of summary generation
    before_session = datetime.now()
    write_session_file(session_id, cwd, "waiting", None)
    after_session = datetime.now()
    debug_log(f"Writing session file took: {(after_session - before_session).total_seconds():.4f}s")

    # Mark activity as done (is_working = false) for Homestead activity stream
    # Keep activities list intact so UI can show what happened
    tmux_session = get_tmux_session_name()
    if not tmux_session:
        project_name = os.path.basename(cwd) if cwd else "unknown"
        tmux_session = f"holler-{project_name}"
    activity_file = f"/tmp/claude-session-{tmux_session}-activity.json"
    if os.path.exists(activity_file):
        try:
            with open(activity_file, "r") as f:
                activity = json.load(f)
            activity["is_working"] = False
            activity["current_tool"] = None
            activity["updated_at"] = datetime.now().isoformat()
            # Mark any "Thinking..." entry as complete
            for act in activity.get("activities", []):
                if act.get("tool") == "thinking" and act.get("phase") == "start":
                    act["phase"] = "complete"
                    act["message"] = "Done thinking"
                    act["completed_at"] = datetime.now().isoformat()
            with open(activity_file, "w") as f:
                json.dump(activity, f)
            debug_log(f"Marked activity as done: {activity_file}")
        except Exception as e:
            debug_log(f"Error updating activity file: {e}")

    # Check if this is an ephemeral worker that should be killed
    ephemeral_registry_file = "/tmp/ephemeral-workers.json"
    if tmux_session and os.path.exists(ephemeral_registry_file):
        try:
            with open(ephemeral_registry_file, "r") as f:
                registry = json.load(f)
            if tmux_session in registry.get("sessions", []):
                debug_log(f"Ephemeral worker detected: {tmux_session}")
                # Remove from registry first
                registry["sessions"] = [s for s in registry["sessions"] if s != tmux_session]
                with open(ephemeral_registry_file, "w") as f:
                    json.dump(registry, f, indent=2)
                debug_log(f"Removed {tmux_session} from ephemeral registry")
                # Kill the tmux session (fork to background so hook exits fast)
                try:
                    subprocess.Popen(
                        ["tmux", "kill-session", "-t", tmux_session],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    debug_log(f"Sent kill command for tmux session: {tmux_session}")
                except Exception as kill_err:
                    debug_log(f"Error killing ephemeral session: {kill_err}")
        except Exception as e:
            debug_log(f"Error checking ephemeral registry: {e}")

    # Spawn turn watcher for non-ephemeral sessions (runs in background)
    # This meta-agent verifies what just happened and reports back
    debug_log(f"=== WATCHER CHECK START === tmux_session={tmux_session}")
    if tmux_session and not tmux_session.startswith("ephemeral-") and not tmux_session.startswith("watcher-"):
        debug_log(f"Session passes prefix check")
        try:
            turn_watcher_script = "/Users/joshuamullet/code/homestead/lib/spawn-turn-watcher.js"
            debug_log(f"Watcher script exists: {os.path.exists(turn_watcher_script)}")
            if os.path.exists(turn_watcher_script):
                # Check if turn watcher is enabled for this session
                # Homestead writes enabled sessions to this file
                watcher_enabled_file = "/Users/joshuamullet/code/homestead/data/watcher-enabled-sessions.json"
                debug_log(f"Checking watcher enabled file: {watcher_enabled_file}")
                debug_log(f"File exists: {os.path.exists(watcher_enabled_file)}")
                turn_watcher_enabled = False
                if os.path.exists(watcher_enabled_file):
                    try:
                        with open(watcher_enabled_file, 'r') as f:
                            enabled_sessions = json.load(f)
                            debug_log(f"Enabled sessions: {enabled_sessions}")
                            turn_watcher_enabled = tmux_session in enabled_sessions
                            debug_log(f"This session enabled: {turn_watcher_enabled}")
                    except Exception as e:
                        debug_log(f"Error reading watcher enabled file: {e}")
                else:
                    debug_log("Watcher enabled file does not exist")

                if turn_watcher_enabled:
                    debug_log(f"Spawning turn watcher for session: {tmux_session}")
                    subprocess.Popen(
                        ["node", turn_watcher_script, tmux_session],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        cwd="/Users/joshuamullet/code/homestead"
                    )
                    debug_log("Watcher spawn command issued")
                else:
                    debug_log(f"Turn watcher disabled for session: {tmux_session}")
        except Exception as tw_err:
            debug_log(f"Error spawning turn watcher: {tw_err}")
    else:
        debug_log(f"Session skipped: ephemeral or watcher prefix")
    debug_log("=== WATCHER CHECK END ===")

    # Fork summary generation into a background process so the hook exits instantly
    # The parent (hook) exits immediately, the child generates the summary async
    before_fork = datetime.now()
    pid = os.fork()
    after_fork = datetime.now()
    debug_log(f"Fork took: {(after_fork - before_fork).total_seconds():.4f}s")

    if pid == 0:
        # Child process — detach from parent and generate summary
        try:
            os.setsid()  # Create new session, fully detach from hook process group
            debug_log("Background summary process started (detached)")
            _run_summary_pipeline(session_id, transcript_path, cwd)
            debug_log("Background summary process FINISHED")
        except Exception as e:
            debug_log(f"Background summary error: {e}")
        finally:
            os._exit(0)  # Exit child without cleanup (don't trigger atexit handlers)
    else:
        # Parent (hook) — exit immediately, don't wait for child
        debug_log(f"Forked summary to background pid={pid}, hook exiting now")
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        debug_log(f"Stop Hook FINISHED - Total time: {total_time:.4f}s")

    # Note: We keep temp_file to accumulate exchanges over time
    # user_prompt_submit.py handles trimming to MAX_EXCHANGES

    sys.exit(0)


if __name__ == "__main__":
    main()
