#!/usr/bin/env bash
# bootstrap-cloud.sh — Idempotent cloud environment bootstrap.
#
# Detects what the project needs and installs it: Python venvs, OpenSpec CLI,
# skills, git config.  Designed to work in ANY repo that has this skill
# installed — not just agentic-coding-tools.
#
# Design contract:
#   - Idempotent: skip completed steps on re-run.
#   - Always exits 0: never block a session.  Failures become warnings.
#   - All diagnostic output goes to stderr (stdout reserved for hook context).
#
# Usage:
#   .claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh            # full install
#   .claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh --check    # dry-run diagnostics
#
# Wired as a SessionStart hook in .claude/settings.json.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve project root: scripts/ → session-bootstrap/ → skills/ → .claude/ → project root
# Works from both canonical (skills/session-bootstrap/scripts/) and
# installed (.claude/skills/session-bootstrap/scripts/) locations.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"

CHECK_ONLY=false
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

# ---------------------------------------------------------------------------
# Logging helpers — all output to stderr
# ---------------------------------------------------------------------------
INSTALLED=()
SKIPPED=()
WARNINGS=()

log()  { echo "[bootstrap] $*" >&2; }
ok()   { INSTALLED+=("$1"); log "OK  $1"; }
skip() { SKIPPED+=("$1");   log "--- $1 (already done)"; }
warn() { WARNINGS+=("$1");  log "!!! $1"; }

# ---------------------------------------------------------------------------
# Step 1: Python 3.12+
# ---------------------------------------------------------------------------
setup_python() {
    log "Step 1/6: Python 3.12+"
    if $CHECK_ONLY; then
        python3 --version >&2 2>&1 || warn "python3 not found"
        return
    fi

    local py_version
    py_version="$(python3 --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)" || true
    local major="${py_version%%.*}"
    local minor="${py_version#*.}"

    if [[ -n "$major" && "$major" -ge 3 && "$minor" -ge 12 ]]; then
        skip "python3 $py_version >= 3.12"
    elif command -v uv >/dev/null 2>&1; then
        uv python install 3.12 >&2 2>&1 && ok "python 3.12 installed via uv" \
            || warn "uv python install 3.12 failed"
    else
        warn "python3 < 3.12 and uv not available"
    fi
}

# ---------------------------------------------------------------------------
# Step 2: Python venvs — auto-detect pyproject.toml locations
# ---------------------------------------------------------------------------
setup_venvs() {
    log "Step 2/6: Python venvs"

    if ! command -v uv >/dev/null 2>&1; then
        warn "uv not available — cannot set up venvs"
        return
    fi

    # Discover pyproject.toml files that need venvs.
    # Priority: project root, then known subdirectories.
    local venv_targets=()

    # Project root pyproject.toml (most repos)
    if [[ -f "$PROJECT_DIR/pyproject.toml" ]]; then
        venv_targets+=("$PROJECT_DIR")
    fi

    # agent-coordinator (agentic-coding-tools specific)
    if [[ -f "$PROJECT_DIR/agent-coordinator/pyproject.toml" ]]; then
        venv_targets+=("$PROJECT_DIR/agent-coordinator")
    fi

    # skills infrastructure (agentic-coding-tools specific)
    if [[ -f "$PROJECT_DIR/skills/pyproject.toml" ]]; then
        venv_targets+=("$PROJECT_DIR/skills")
    fi

    if [[ ${#venv_targets[@]} -eq 0 ]]; then
        skip "no pyproject.toml found"
        return
    fi

    for target in "${venv_targets[@]}"; do
        local label="${target#"$PROJECT_DIR"/}"
        [[ "$label" == "$PROJECT_DIR" ]] && label="(root)"
        local venv_dir="$target/.venv"

        if $CHECK_ONLY; then
            [[ -f "$venv_dir/bin/activate" ]] && log "  $label venv exists" >&2 \
                || warn "$label venv missing"
            continue
        fi

        if [[ -f "$venv_dir/bin/activate" ]]; then
            skip "$label venv"
        else
            (cd "$target" && uv sync --all-extras >&2 2>&1) \
                && ok "$label venv" \
                || warn "$label uv sync failed"
        fi
    done
}

# ---------------------------------------------------------------------------
# Step 3: OpenSpec CLI
# ---------------------------------------------------------------------------
setup_openspec() {
    log "Step 3/6: OpenSpec CLI"
    if $CHECK_ONLY; then
        command -v openspec >/dev/null 2>&1 && log "  openspec found" >&2 \
            || warn "openspec not found"
        return
    fi

    if command -v openspec >/dev/null 2>&1; then
        skip "openspec CLI"
    elif command -v npm >/dev/null 2>&1; then
        npm install -g @fission-ai/openspec >&2 2>&1 \
            && ok "openspec CLI" \
            || warn "npm install openspec failed"
    else
        warn "npm not available — cannot install openspec"
    fi
}

# ---------------------------------------------------------------------------
# Step 4: Install skills (only in repos with skills/install.sh)
# ---------------------------------------------------------------------------
setup_skills() {
    log "Step 4/6: Install skills"

    if [[ ! -f "$PROJECT_DIR/skills/install.sh" ]]; then
        skip "no skills/install.sh (not a skills source repo)"
        return
    fi

    if $CHECK_ONLY; then
        [[ -d "$PROJECT_DIR/.claude/skills" ]] && log "  .claude/skills/ exists" >&2 \
            || warn ".claude/skills/ missing"
        return
    fi

    # Always rsync — fast when unchanged, catches new/updated skills
    bash "$PROJECT_DIR/skills/install.sh" \
        --mode rsync --deps none --python-tools none --force >&2 2>&1 \
        && ok "skills installed (.claude/skills/)" \
        || warn "skills install.sh failed"
}

# ---------------------------------------------------------------------------
# Step 5: Frontend dependencies (if web/ or frontend/ exists)
# ---------------------------------------------------------------------------
setup_frontend() {
    log "Step 5/6: Frontend dependencies"

    local frontend_dir=""
    if [[ -f "$PROJECT_DIR/web/package.json" ]]; then
        frontend_dir="$PROJECT_DIR/web"
    elif [[ -f "$PROJECT_DIR/frontend/package.json" ]]; then
        frontend_dir="$PROJECT_DIR/frontend"
    fi

    if [[ -z "$frontend_dir" ]]; then
        skip "no frontend directory found"
        return
    fi

    local label="${frontend_dir#"$PROJECT_DIR"/}"

    if $CHECK_ONLY; then
        [[ -d "$frontend_dir/node_modules" ]] && log "  $label/node_modules/ exists" >&2 \
            || warn "$label/node_modules/ missing"
        return
    fi

    if [[ -d "$frontend_dir/node_modules" ]]; then
        skip "$label dependencies"
    elif command -v pnpm >/dev/null 2>&1; then
        (cd "$frontend_dir" && pnpm install --frozen-lockfile >&2 2>&1) \
            && ok "$label dependencies (pnpm)" \
            || warn "$label pnpm install failed"
    elif command -v npm >/dev/null 2>&1; then
        (cd "$frontend_dir" && npm ci >&2 2>&1) \
            && ok "$label dependencies (npm)" \
            || warn "$label npm ci failed"
    else
        warn "no package manager available for $label"
    fi
}

# ---------------------------------------------------------------------------
# Step 6: Git parallel config
# ---------------------------------------------------------------------------
setup_git() {
    log "Step 6/6: Git parallel config"

    if ! git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
        skip "not a git repo"
        return
    fi

    if $CHECK_ONLY; then
        git -C "$PROJECT_DIR" config --local rerere.enabled >/dev/null 2>&1 \
            && log "  git parallel config set" >&2 \
            || warn "git parallel config not set"
        return
    fi

    if git -C "$PROJECT_DIR" config --local rerere.enabled >/dev/null 2>&1; then
        skip "git parallel config"
    else
        # Apply inline — no dependency on git-parallel-setup.sh existing
        local configs=(
            "rerere.enabled=true"
            "rerere.autoUpdate=true"
            "merge.conflictStyle=zdiff3"
            "diff.algorithm=histogram"
            "rebase.updateRefs=true"
        )
        for entry in "${configs[@]}"; do
            git -C "$PROJECT_DIR" config --local "${entry%%=*}" "${entry#*=}"
        done
        ok "git parallel config"
    fi
}

# ---------------------------------------------------------------------------
# Venv activation via CLAUDE_ENV_FILE
# ---------------------------------------------------------------------------
activate_venv() {
    # CLAUDE_ENV_FILE is a Claude Code mechanism: lines appended to this file
    # are sourced into every subsequent Bash invocation during the session.
    if [[ -z "${CLAUDE_ENV_FILE:-}" ]]; then
        return
    fi

    log "Activating venv for session"

    # Prefer the most specific venv, falling back to generic
    local candidates=(
        "$PROJECT_DIR/agent-coordinator/.venv/bin/activate"
        "$PROJECT_DIR/.venv/bin/activate"
    )
    for venv_activate in "${candidates[@]}"; do
        if [[ -f "$venv_activate" ]]; then
            echo "source \"$venv_activate\"" >> "$CLAUDE_ENV_FILE"
            log "  Activated: $venv_activate"
            return
        fi
    done
    log "  No venv found to activate"
}

# ---------------------------------------------------------------------------
# Environment variable guidance
# ---------------------------------------------------------------------------
check_env_vars() {
    local vars=("COORDINATION_API_URL" "COORDINATION_API_KEY")
    local missing=()
    for var in "${vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing+=("$var")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log "Coordinator env vars not set: ${missing[*]}"
        log "  Set these for coordinator access (optional for local-only work)"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "=== Cloud Bootstrap — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    log "Project: $PROJECT_DIR"
    [[ "$CHECK_ONLY" == true ]] && log "Mode: --check (dry run)"

    setup_python
    setup_venvs
    setup_openspec
    setup_skills
    setup_frontend
    setup_git
    activate_venv
    check_env_vars

    # Summary
    log "=== Bootstrap Summary ==="
    log "  Installed: ${#INSTALLED[@]}  Skipped: ${#SKIPPED[@]}  Warnings: ${#WARNINGS[@]}"
    if [[ ${#WARNINGS[@]} -gt 0 ]]; then
        log "  Warnings:"
        for w in "${WARNINGS[@]}"; do
            log "    - $w"
        done
    fi

    return 0
}

# Trap ensures exit 0 even on unexpected errors
trap 'log "Bootstrap finished (trapped)"; exit 0' ERR
main
exit 0
