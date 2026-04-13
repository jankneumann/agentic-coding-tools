#!/bin/bash
# setup-cloud.sh — One-time cloud environment setup.
#
# For the cloud Environment Settings "Setup Script" field, paste:
#   bash "$(pwd)/.claude/skills/session-bootstrap/scripts/setup-cloud.sh"
#
# Or paste the full script contents if the skill isn't installed yet.
# Runs as root on new sessions only (skipped on resume).
#
# Claude Code web pre-installs: Python 3.x, uv, pip, npm, pnpm, docker, git.
# Codex pre-installs similar tools via the "universal" image.
#
# This script installs project-specific deps that aren't pre-installed.
# On resume, the SessionStart hook (bootstrap-cloud.sh) verifies everything
# is still in place and repairs anything missing.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

log() { echo "[setup] $*"; }

log "=== Cloud Setup — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
log "Project: $PROJECT_DIR"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Python venvs — auto-detect pyproject.toml locations
# ---------------------------------------------------------------------------
install_venvs() {
    local targets=()
    [[ -f "$PROJECT_DIR/pyproject.toml" ]] && targets+=("$PROJECT_DIR")
    [[ -f "$PROJECT_DIR/agent-coordinator/pyproject.toml" ]] && targets+=("$PROJECT_DIR/agent-coordinator")
    [[ -f "$PROJECT_DIR/skills/pyproject.toml" ]] && targets+=("$PROJECT_DIR/skills")

    for target in "${targets[@]}"; do
        local label="${target#"$PROJECT_DIR"/}"
        [[ "$label" == "$PROJECT_DIR" ]] && label="(root)"
        log "Installing $label venv..."
        (cd "$target" && uv sync --all-extras) || log "WARNING: $label uv sync failed"
    done
}

# ---------------------------------------------------------------------------
# OpenSpec CLI
# ---------------------------------------------------------------------------
install_openspec() {
    if ! command -v openspec >/dev/null 2>&1; then
        log "Installing OpenSpec CLI..."
        npm install -g @fission-ai/openspec || log "WARNING: openspec install failed"
    fi
}

# ---------------------------------------------------------------------------
# Skills (only in source repo)
# ---------------------------------------------------------------------------
install_skills() {
    if [[ -f "$PROJECT_DIR/skills/install.sh" ]]; then
        log "Installing skills..."
        bash "$PROJECT_DIR/skills/install.sh" --mode rsync --deps none --python-tools none --force
    fi
}

# ---------------------------------------------------------------------------
# Frontend (if web/ or frontend/ exists)
# ---------------------------------------------------------------------------
install_frontend() {
    local dir=""
    [[ -f "$PROJECT_DIR/web/package.json" ]] && dir="$PROJECT_DIR/web"
    [[ -f "$PROJECT_DIR/frontend/package.json" ]] && dir="$PROJECT_DIR/frontend"

    if [[ -n "$dir" ]]; then
        local label="${dir#"$PROJECT_DIR"/}"
        log "Installing $label dependencies..."
        if command -v pnpm >/dev/null 2>&1; then
            (cd "$dir" && pnpm install --frozen-lockfile) || log "WARNING: pnpm install failed"
        else
            (cd "$dir" && npm ci) || log "WARNING: npm ci failed"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Git parallel config
# ---------------------------------------------------------------------------
setup_git() {
    if git rev-parse --git-dir >/dev/null 2>&1; then
        git config --local rerere.enabled true
        git config --local rerere.autoUpdate true
        git config --local merge.conflictStyle zdiff3
        git config --local diff.algorithm histogram
        git config --local rebase.updateRefs true
        log "Git parallel config applied"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
install_venvs
install_openspec
install_skills
install_frontend
setup_git
log "=== Setup complete ==="
