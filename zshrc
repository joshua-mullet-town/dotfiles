export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

. "$HOME/.local/bin/env"
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.local/bin:$PATH"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
export PATH="$HOME/bin:$PATH"

# Soft newline on Shift+Return
# Bind escape + newline code to inserting a newline
bindkey '^[[13;2u' self-insert






# Enhanced Holler - Development Command Center with Auto-Discovery + tmux
holler() {
    local CODE_DIR="/Users/joshuamullet/code"
    local ORIGINAL_DIR=$(pwd)
    local WORKING_DIR="$CODE_DIR"

    # Parse special flags
    local USE_HERE_MODE=false
    local remaining_args=()

    for arg in "$@"; do
        if [ "$arg" = "here" ] && [ "$USE_HERE_MODE" = false ]; then
            USE_HERE_MODE=true
        else
            remaining_args+=("$arg")
        fi
    done

    # Auto-discover all directories and build --add-dir flags
    local ADD_DIR_FLAGS=""
    for dir in "$CODE_DIR"/*; do
        if [ -d "$dir" ] && [ "$(basename "$dir")" != "holler" ]; then
            ADD_DIR_FLAGS="$ADD_DIR_FLAGS --add-dir \"$dir\""
        fi
    done

    # Determine working directory
    if [ "$USE_HERE_MODE" = true ]; then
        WORKING_DIR="$ORIGINAL_DIR"
        echo "📍 'here' mode: Working from current directory"
    fi

    # Generate session name based on working directory
    # For worktrees (~/.worktrees/{project}/{branch}), use holler-{project}--{branch}
    # For main projects (~/code/{project}), use holler-{project}
    local SESSION_NAME
    if [[ "$WORKING_DIR" == */.worktrees/* ]]; then
        # Extract project and branch from worktree path
        local worktree_part="${WORKING_DIR#*/.worktrees/}"
        local wt_project="${worktree_part%%/*}"
        local wt_branch="${worktree_part#*/}"
        SESSION_NAME="holler-${wt_project}--${wt_branch}"
    else
        SESSION_NAME="holler-$(basename "$WORKING_DIR")"
    fi

    # Base Claude command with all discovered directories (use full path to avoid broken alias)
    local CLAUDE_CMD="/Users/joshuamullet/.nvm/versions/node/v20.19.3/bin/claude --dangerously-skip-permissions$ADD_DIR_FLAGS"

    # Add remaining arguments (flags like --resume, --continue, etc.)
    local claude_args=""
    for arg in "${remaining_args[@]}"; do
        claude_args="$claude_args $arg"
    done

    if [ -n "$claude_args" ]; then
        CLAUDE_CMD="$CLAUDE_CMD$claude_args"
    fi

    echo "🚀 Starting holler..."
    echo "📍 Working from: $WORKING_DIR"
    echo "📦 tmux session: $SESSION_NAME"

    # Check if already inside tmux
    if [ -n "$TMUX" ]; then
        # Already in tmux - just run claude directly (for restart scenarios)
        echo "📺 Already in tmux - running claude directly"
        eval "$CLAUDE_CMD"
        return $?
    fi

    # Check if session already exists - ATTACH instead of kill
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "📎 Session exists, attaching..."
        tmux attach-session -t "$SESSION_NAME"
    else
        # Create new tmux session with Claude
        echo "🆕 Creating fresh tmux session..."
        tmux new-session -s "$SESSION_NAME" -c "$WORKING_DIR" "$CLAUDE_CMD; zsh"
    fi

    echo "👋 Returned to $(pwd)"
}
export PATH="$PATH:$HOME/google-cloud-sdk/bin"
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"

cd ~/code

export PATH="$PATH:/Applications/Visual Studio Code.app/Contents/Resources/app/bin"

