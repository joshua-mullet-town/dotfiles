#!/usr/bin/env python3
"""
Auto-Save Hook - Automatically commits work in progress to prevent loss.

This hook is triggered by PostToolUse for Edit/Write operations.
It marks repos as dirty, and a companion script (auto_save_daemon.py)
periodically commits dirty repos.

Can also be run directly to force an immediate commit of all dirty repos.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Config
DIRTY_FLAG_DIR = "/tmp/claude-auto-save"
WORKTREE_BASE = os.path.expanduser("~/.worktrees")
CODE_BASE = os.path.expanduser("~/code")
COMMIT_MESSAGE_PREFIX = "WIP auto-save"

# ALWAYS auto-save these repos (checked every 5 min even if not marked dirty)
ALWAYS_SAVE_REPOS = [
    os.path.expanduser("~/code/homestead"),  # Production homestead
    os.path.expanduser("~/code/dotfiles"),   # Dotfiles (zshrc, claude hooks, iterm, etc)
]

def log(message):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr)

def ensure_dir(path):
    """Ensure directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)

def get_git_root(path):
    """Get the git root directory for a path."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return None

def is_dirty(repo_path):
    """Check if a git repo has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        return bool(result.stdout.strip())
    except:
        return False

def mark_dirty(repo_path):
    """Mark a repo as needing auto-save."""
    ensure_dir(DIRTY_FLAG_DIR)
    # Use repo path hash as filename to avoid conflicts
    flag_file = os.path.join(DIRTY_FLAG_DIR, repo_path.replace("/", "_") + ".dirty")
    with open(flag_file, "w") as f:
        json.dump({
            "repo": repo_path,
            "marked_at": datetime.now().isoformat(),
            "cwd": os.getcwd()
        }, f)

def get_dirty_repos():
    """Get list of repos marked as dirty."""
    ensure_dir(DIRTY_FLAG_DIR)
    repos = []
    for fname in os.listdir(DIRTY_FLAG_DIR):
        if fname.endswith(".dirty"):
            fpath = os.path.join(DIRTY_FLAG_DIR, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                    repos.append(data["repo"])
            except:
                pass
    return repos

def clear_dirty(repo_path):
    """Clear dirty flag for a repo."""
    flag_file = os.path.join(DIRTY_FLAG_DIR, repo_path.replace("/", "_") + ".dirty")
    try:
        os.remove(flag_file)
    except:
        pass

def sync_dotfiles():
    """Sync actual dotfiles into the dotfiles repo before committing."""
    dotfiles_repo = os.path.expanduser("~/code/dotfiles")
    if not os.path.exists(dotfiles_repo):
        return

    home = os.path.expanduser("~")
    copies = [
        (os.path.join(home, ".zshrc"), os.path.join(dotfiles_repo, "zshrc")),
        (os.path.join(home, ".tmux.conf"), os.path.join(dotfiles_repo, "tmux.conf")),
    ]

    # Sync claude hooks
    hooks_src = os.path.join(home, ".claude", "hooks")
    hooks_dst = os.path.join(dotfiles_repo, "claude", "hooks")
    if os.path.isdir(hooks_src):
        os.makedirs(hooks_dst, exist_ok=True)
        for fname in os.listdir(hooks_src):
            src = os.path.join(hooks_src, fname)
            dst = os.path.join(hooks_dst, fname)
            if os.path.isfile(src):
                copies.append((src, dst))

    # Sync claude settings (but NOT secrets/credentials)
    settings_src = os.path.join(home, ".claude", "settings.json")
    settings_dst = os.path.join(dotfiles_repo, "claude", "settings.json")
    if os.path.isfile(settings_src):
        copies.append((settings_src, settings_dst))

    import shutil
    for src, dst in copies:
        if os.path.isfile(src):
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            except Exception as e:
                log(f"Failed to sync {src} -> {dst}: {e}")

def auto_commit(repo_path):
    """Auto-commit all changes in a repo."""
    # Sync dotfiles before checking if dirty
    dotfiles_repo = os.path.expanduser("~/code/dotfiles")
    if repo_path == dotfiles_repo:
        sync_dotfiles()

    if not is_dirty(repo_path):
        clear_dirty(repo_path)
        return False

    try:
        # Get branch name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        branch = result.stdout.strip() or "unknown"

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
            timeout=10
        )

        # Commit
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = f"{COMMIT_MESSAGE_PREFIX} ({branch}) - {timestamp}"

        result = subprocess.run(
            ["git", "commit", "-m", message, "--no-verify"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            log(f"Auto-saved: {repo_path}")
            clear_dirty(repo_path)

            # Auto-push to remote if tracking branch exists
            try:
                push_result = subprocess.run(
                    ["git", "push"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if push_result.returncode == 0:
                    log(f"Auto-pushed: {repo_path}")
                else:
                    log(f"Push failed (non-fatal): {push_result.stderr.strip()}")
            except Exception as push_err:
                log(f"Push error (non-fatal): {push_err}")

            return True
        else:
            log(f"Commit failed for {repo_path}: {result.stderr}")
            return False

    except Exception as e:
        log(f"Error auto-committing {repo_path}: {e}")
        return False

def find_all_worktrees():
    """Find all git worktrees under the worktree base."""
    repos = []
    if not os.path.exists(WORKTREE_BASE):
        return repos

    for project in os.listdir(WORKTREE_BASE):
        project_path = os.path.join(WORKTREE_BASE, project)
        if not os.path.isdir(project_path):
            continue
        for branch in os.listdir(project_path):
            branch_path = os.path.join(project_path, branch)
            if os.path.isdir(branch_path) and os.path.exists(os.path.join(branch_path, ".git")):
                repos.append(branch_path)

    return repos

def commit_all_dirty():
    """Commit all dirty repos."""
    committed = 0
    checked = set()

    # First, ALWAYS check the priority repos (homestead production, etc)
    for repo in ALWAYS_SAVE_REPOS:
        if os.path.exists(repo) and is_dirty(repo):
            if auto_commit(repo):
                committed += 1
            checked.add(repo)

    # Check explicitly marked dirty repos
    for repo in get_dirty_repos():
        if repo in checked:
            continue
        if os.path.exists(repo):
            if auto_commit(repo):
                committed += 1
            checked.add(repo)

    # Also scan all worktrees for any uncommitted changes
    for repo in find_all_worktrees():
        if repo in checked:
            continue
        if is_dirty(repo):
            if auto_commit(repo):
                committed += 1

    return committed

def handle_hook():
    """Handle being called as a Claude hook."""
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data:
            return

        input_data = json.loads(stdin_data)
        hook_event = input_data.get("hook_event_name", "")
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Only care about PostToolUse for Edit/Write
        if hook_event != "PostToolUse":
            return

        if tool_name not in ("Edit", "Write"):
            return

        # Get the file path that was modified
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return

        # Find git root
        dir_path = os.path.dirname(file_path)
        if not os.path.exists(dir_path):
            return

        git_root = get_git_root(dir_path)
        if git_root:
            mark_dirty(git_root)
            log(f"Marked dirty: {git_root}")

    except Exception as e:
        log(f"Hook error: {e}")

def main():
    # If run with --commit, do immediate commit of all dirty repos
    if len(sys.argv) > 1 and sys.argv[1] == "--commit":
        committed = commit_all_dirty()
        log(f"Committed {committed} repos")
        return

    # If run with --daemon, start the daemon loop
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        import time
        log("Auto-save daemon started (commits every 5 minutes)")
        while True:
            time.sleep(300)  # 5 minutes
            committed = commit_all_dirty()
            if committed > 0:
                log(f"Auto-saved {committed} repos")
        return

    # Otherwise, handle as a hook
    handle_hook()

if __name__ == "__main__":
    main()
