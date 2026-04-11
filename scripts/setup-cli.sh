#!/usr/bin/env bash
# setup-cli.sh — One-time local CLI setup for agentic-coding-tools.
#
# Complements bootstrap-cloud.sh: this script handles the interactive and
# infrastructure steps that cloud environments can't do (Docker, MCP
# registration, env var configuration).
#
# Run once after cloning.  Safe to re-run (idempotent where possible).
#
# Usage:
#   scripts/setup-cli.sh                # full interactive setup
#   scripts/setup-cli.sh --check        # report what's configured vs missing
#   scripts/setup-cli.sh --skip-docker  # skip Docker/ParadeDB (e.g. using cloud DB)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COORDINATOR_DIR="$PROJECT_DIR/agent-coordinator"

CHECK_ONLY=false
SKIP_DOCKER=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check)      CHECK_ONLY=true; shift ;;
        --skip-docker) SKIP_DOCKER=true; shift ;;
        -h|--help)
            echo "Usage: scripts/setup-cli.sh [--check] [--skip-docker]"
            echo ""
            echo "One-time local setup for CLI agent development."
            echo ""
            echo "Steps:"
            echo "  1. Install Python dependencies (agent-coordinator + skills)"
            echo "  2. Install OpenSpec CLI"
            echo "  3. Install skills"
            echo "  4. Configure git for parallel development"
            echo "  5. Start Docker/ParadeDB (unless --skip-docker)"
            echo "  6. Register coordination MCP server with Claude Code"
            echo "  7. Guide env var configuration"
            echo ""
            echo "Options:"
            echo "  --check        Report status without making changes"
            echo "  --skip-docker  Skip Docker/ParadeDB setup (using remote DB)"
            exit 0
            ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC}   $1"; }
miss() { echo -e "${RED}[MISS]${NC} $1"; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }
step() { echo ""; echo "=== Step $1 ==="; }

# ---------------------------------------------------------------------------
# Step 1: Python dependencies
# ---------------------------------------------------------------------------
step_python() {
    step "1/7: Python dependencies"

    # Check uv
    if ! command -v uv >/dev/null 2>&1; then
        miss "uv not installed — see https://docs.astral.sh/uv/getting-started/installation/"
        return
    fi
    ok "uv available"

    # agent-coordinator venv
    if [[ -f "$COORDINATOR_DIR/.venv/bin/coordination-mcp" ]]; then
        ok "agent-coordinator venv (entry point exists)"
    elif $CHECK_ONLY; then
        miss "agent-coordinator venv"
    else
        info "Installing agent-coordinator dependencies..."
        (cd "$COORDINATOR_DIR" && uv sync --all-extras)
        ok "agent-coordinator venv created"
    fi

    # skills venv
    if [[ -f "$PROJECT_DIR/skills/.venv/bin/activate" ]]; then
        ok "skills venv"
    elif $CHECK_ONLY; then
        miss "skills venv"
    else
        info "Installing skills dependencies..."
        (cd "$PROJECT_DIR/skills" && uv sync --all-extras)
        ok "skills venv created"
    fi
}

# ---------------------------------------------------------------------------
# Step 2: OpenSpec CLI
# ---------------------------------------------------------------------------
step_openspec() {
    step "2/7: OpenSpec CLI"

    if command -v openspec >/dev/null 2>&1; then
        ok "openspec CLI ($(openspec --version 2>/dev/null || echo 'installed'))"
    elif $CHECK_ONLY; then
        miss "openspec CLI — install with: npm install -g @fission-ai/openspec"
    else
        info "Installing OpenSpec CLI..."
        npm install -g @fission-ai/openspec
        ok "openspec CLI installed"
    fi
}

# ---------------------------------------------------------------------------
# Step 3: Skills
# ---------------------------------------------------------------------------
step_skills() {
    step "3/7: Install skills"

    if $CHECK_ONLY; then
        [[ -d "$PROJECT_DIR/.claude/skills" ]] && ok ".claude/skills/ exists" \
            || miss ".claude/skills/ — run: bash skills/install.sh"
        return
    fi

    bash "$PROJECT_DIR/skills/install.sh" \
        --mode rsync --deps none --python-tools none --force
    ok "Skills installed to .claude/skills/"
}

# ---------------------------------------------------------------------------
# Step 4: Git config
# ---------------------------------------------------------------------------
step_git() {
    step "4/7: Git parallel config"

    if git -C "$PROJECT_DIR" config --local rerere.enabled >/dev/null 2>&1; then
        ok "Git parallel config (rerere, zdiff3, histogram)"
    elif $CHECK_ONLY; then
        miss "Git parallel config"
    else
        bash "$PROJECT_DIR/skills/worktree/scripts/git-parallel-setup.sh"
        ok "Git parallel config applied"
    fi
}

# ---------------------------------------------------------------------------
# Step 5: Docker / ParadeDB
# ---------------------------------------------------------------------------
step_docker() {
    step "5/7: Docker / ParadeDB"

    if $SKIP_DOCKER; then
        info "Skipped (--skip-docker)"
        return
    fi

    if ! command -v docker >/dev/null 2>&1; then
        miss "Docker not installed — https://docs.docker.com/get-docker/"
        return
    fi
    ok "Docker available"

    # Check if ParadeDB is running
    if pg_isready -h localhost -p "${AGENT_COORDINATOR_DB_PORT:-54322}" -U postgres >/dev/null 2>&1; then
        ok "ParadeDB running on port ${AGENT_COORDINATOR_DB_PORT:-54322}"
    elif $CHECK_ONLY; then
        miss "ParadeDB not running — start with: make -C agent-coordinator db-up"
    else
        info "Starting ParadeDB..."
        make -C "$COORDINATOR_DIR" db-up
        ok "ParadeDB started"
    fi
}

# ---------------------------------------------------------------------------
# Step 6: MCP registration
# ---------------------------------------------------------------------------
step_mcp() {
    step "6/7: Coordination MCP server"

    if ! command -v claude >/dev/null 2>&1; then
        info "Claude CLI not found — skipping MCP registration"
        return
    fi

    # Check if already registered
    if claude mcp get coordination >/dev/null 2>&1; then
        ok "Coordination MCP server registered"
    elif $CHECK_ONLY; then
        miss "Coordination MCP not registered — run: make -C agent-coordinator claude-mcp-setup"
    else
        info "Registering coordination MCP server with Claude Code..."
        make -C "$COORDINATOR_DIR" claude-mcp-setup
        ok "MCP server registered (restart Claude Code to activate)"
    fi
}

# ---------------------------------------------------------------------------
# Step 7: Environment variables
# ---------------------------------------------------------------------------
step_env() {
    step "7/7: Environment variables"

    local vars=(
        "COORDINATION_API_URL:Coordinator HTTP API URL (e.g. http://localhost:8081)"
        "COORDINATION_API_KEY:API key for coordinator auth"
        "AGENT_ID:Agent identifier (e.g. claude-code-1)"
        "AGENT_TYPE:Agent type (e.g. claude_code)"
    )

    local all_set=true
    for entry in "${vars[@]}"; do
        local var="${entry%%:*}"
        local desc="${entry#*:}"
        if [[ -n "${!var:-}" ]]; then
            ok "$var is set"
        else
            miss "$var — $desc"
            all_set=false
        fi
    done

    if [[ "$all_set" == false ]]; then
        echo ""
        info "Set these in your shell profile or agent-coordinator/.env:"
        echo "  export COORDINATION_API_URL=http://localhost:8081"
        echo "  export COORDINATION_API_KEY=<your-key>"
        echo "  export AGENT_ID=claude-code-1"
        echo "  export AGENT_TYPE=claude_code"
        echo ""
        info "For cloud coordinator (Railway):"
        echo "  export COORDINATION_API_URL=https://coord.yourdomain.com"
        echo "  export COORDINATION_API_KEY=<your-api-key>"
        echo ""
        info "Tip: copy agent-coordinator/.env.example to .env and fill in values."
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo "============================================"
    echo "  agentic-coding-tools — CLI Setup"
    echo "============================================"
    $CHECK_ONLY && echo "(--check mode: reporting status only)"

    step_python
    step_openspec
    step_skills
    step_git
    step_docker
    step_mcp
    step_env

    echo ""
    echo "============================================"
    if $CHECK_ONLY; then
        echo "  Status check complete."
    else
        echo "  Setup complete!"
    fi
    echo "============================================"
    echo ""
    echo "Next steps:"
    echo "  - Start the coordinator API:  make -C agent-coordinator api-serve"
    echo "  - Verify hooks:               Restart Claude Code — SessionStart will fire"
    echo "  - Run a skill:                /plan-feature \"my feature\""
}

main
