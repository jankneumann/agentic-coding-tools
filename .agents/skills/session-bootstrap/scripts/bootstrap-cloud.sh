#!/usr/bin/env bash
# bootstrap-cloud.sh — Fast SessionStart hook: verify environment, repair if needed.
#
# Runs on every session start AND resume.  Must be fast — only checks file
# existence and command availability.  Invokes package managers only when
# something is actually missing (e.g., venv deleted mid-session).
#
# Heavy installs belong in setup-cloud.sh (cloud Environment Settings "Setup
# Script"), which runs once on new sessions only.
#
# Design contract:
#   - Fast on resume: file-existence checks only, no subprocess for package managers.
#   - Repairs drift: if something IS missing, install it.
#   - Always exits 0: never block a session.
#   - All diagnostic output to stderr (stdout reserved for hook context).
#
# Usage:
#   .claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh            # verify + repair
#   .claude/skills/session-bootstrap/scripts/bootstrap-cloud.sh --check    # dry-run (report only)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve project root.  Works from both locations:
#   Canonical: skills/session-bootstrap/scripts/  → 3 levels up
#   Installed: .claude/skills/session-bootstrap/scripts/ → 4 levels up
# CLAUDE_PROJECT_DIR (set by Claude Code hooks) takes precedence.
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    PROJECT_DIR="$CLAUDE_PROJECT_DIR"
elif git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel >/dev/null 2>&1; then
    PROJECT_DIR="$(git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel)"
elif git -C "$SCRIPT_DIR/../../../.." rev-parse --show-toplevel >/dev/null 2>&1; then
    PROJECT_DIR="$(git -C "$SCRIPT_DIR/../../../.." rev-parse --show-toplevel)"
else
    PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
fi

CHECK_ONLY=false
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

# ---------------------------------------------------------------------------
# Logging helpers — all output to stderr
# ---------------------------------------------------------------------------
REPAIRED=()
WARNINGS=()

log()    { echo "[bootstrap] $*" >&2; }
ok()     { log "OK  $1"; }
repair() { REPAIRED+=("$1"); log "FIX $1"; }
warn()   { WARNINGS+=("$1"); log "!!! $1"; }

# ---------------------------------------------------------------------------
# Verify Python 3.12+
# ---------------------------------------------------------------------------
verify_python() {
    local py_version
    py_version="$(python3 --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)" || true
    local major="${py_version%%.*}"
    local minor="${py_version#*.}"

    if [[ -n "$major" && "$major" -ge 3 && "$minor" -ge 12 ]]; then
        ok "python3 $py_version"
    elif $CHECK_ONLY; then
        warn "python3 < 3.12"
    elif command -v uv >/dev/null 2>&1; then
        uv python install 3.12 >&2 2>&1 && repair "python 3.12" || warn "python install failed"
    else
        warn "python3 < 3.12 and uv not available"
    fi
}

# ---------------------------------------------------------------------------
# Verify Python venvs — file existence check only, no uv sync
# ---------------------------------------------------------------------------
verify_venvs() {
    local venv_targets=()
    [[ -f "$PROJECT_DIR/pyproject.toml" ]] && venv_targets+=("$PROJECT_DIR")
    [[ -f "$PROJECT_DIR/agent-coordinator/pyproject.toml" ]] && venv_targets+=("$PROJECT_DIR/agent-coordinator")
    [[ -f "$PROJECT_DIR/skills/pyproject.toml" ]] && venv_targets+=("$PROJECT_DIR/skills")

    for target in "${venv_targets[@]}"; do
        local label="${target#"$PROJECT_DIR"/}"
        [[ "$label" == "$PROJECT_DIR" ]] && label="(root)"

        if [[ -f "$target/.venv/bin/activate" ]]; then
            ok "$label venv"
        elif $CHECK_ONLY; then
            warn "$label venv missing"
        elif command -v uv >/dev/null 2>&1; then
            (cd "$target" && uv sync --all-extras >&2 2>&1) \
                && repair "$label venv" || warn "$label venv repair failed"
        else
            warn "$label venv missing, uv not available"
        fi
    done
}

# ---------------------------------------------------------------------------
# Verify OpenSpec CLI
# ---------------------------------------------------------------------------
verify_openspec() {
    if command -v openspec >/dev/null 2>&1; then
        ok "openspec CLI"
    elif $CHECK_ONLY; then
        warn "openspec not found"
    elif command -v npm >/dev/null 2>&1; then
        npm install -g @fission-ai/openspec >&2 2>&1 \
            && repair "openspec CLI" || warn "openspec install failed"
    else
        warn "openspec not found, npm not available"
    fi
}

# ---------------------------------------------------------------------------
# Verify skills installed
# ---------------------------------------------------------------------------
verify_skills() {
    if [[ ! -f "$PROJECT_DIR/skills/install.sh" ]]; then
        return  # not a skills source repo
    fi

    if [[ -d "$PROJECT_DIR/.claude/skills" ]] || [[ -d "$PROJECT_DIR/.agents/skills" ]]; then
        ok "skills installed"
    elif $CHECK_ONLY; then
        warn "skills directories missing"
    else
        bash "$PROJECT_DIR/skills/install.sh" \
            --mode rsync --deps none --python-tools none --force >&2 2>&1 \
            && repair "skills installed" || warn "skills install failed"
    fi
}

# ---------------------------------------------------------------------------
# Verify frontend dependencies
# ---------------------------------------------------------------------------
verify_frontend() {
    local frontend_dir=""
    [[ -f "$PROJECT_DIR/web/package.json" ]] && frontend_dir="$PROJECT_DIR/web"
    [[ -f "$PROJECT_DIR/frontend/package.json" ]] && frontend_dir="$PROJECT_DIR/frontend"
    [[ -z "$frontend_dir" ]] && return

    local label="${frontend_dir#"$PROJECT_DIR"/}"
    if [[ -d "$frontend_dir/node_modules" ]]; then
        ok "$label dependencies"
    elif $CHECK_ONLY; then
        warn "$label/node_modules/ missing"
    elif command -v pnpm >/dev/null 2>&1; then
        (cd "$frontend_dir" && pnpm install --frozen-lockfile >&2 2>&1) \
            && repair "$label dependencies" || warn "$label install failed"
    elif command -v npm >/dev/null 2>&1; then
        (cd "$frontend_dir" && npm ci >&2 2>&1) \
            && repair "$label dependencies" || warn "$label install failed"
    else
        warn "$label/node_modules/ missing, no package manager"
    fi
}

# ---------------------------------------------------------------------------
# Verify git parallel config
# ---------------------------------------------------------------------------
verify_git() {
    if ! git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
        return
    fi

    if git -C "$PROJECT_DIR" config --local rerere.enabled >/dev/null 2>&1; then
        ok "git parallel config"
    elif $CHECK_ONLY; then
        warn "git parallel config not set"
    else
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
        repair "git parallel config"
    fi
}

# ---------------------------------------------------------------------------
# Activate venv — CLAUDE_ENV_FILE (Claude Code) or ~/.bashrc (Codex)
# ---------------------------------------------------------------------------
activate_venv() {
    local candidates=(
        "$PROJECT_DIR/agent-coordinator/.venv/bin/activate"
        "$PROJECT_DIR/.venv/bin/activate"
    )

    local venv_activate=""
    for candidate in "${candidates[@]}"; do
        if [[ -f "$candidate" ]]; then
            venv_activate="$candidate"
            break
        fi
    done
    [[ -z "$venv_activate" ]] && return

    local source_line="source \"$venv_activate\""

    # Claude Code: CLAUDE_ENV_FILE persists env across Bash calls
    if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
        echo "$source_line" >> "$CLAUDE_ENV_FILE"
        ok "venv activated via CLAUDE_ENV_FILE: ${venv_activate#"$PROJECT_DIR"/}"
        return
    fi

    # Codex / other: append to ~/.bashrc (idempotent — check before appending)
    if ! grep -qF "$venv_activate" ~/.bashrc 2>/dev/null; then
        echo "$source_line" >> ~/.bashrc
        ok "venv activated via ~/.bashrc: ${venv_activate#"$PROJECT_DIR"/}"
    else
        ok "venv activation already in ~/.bashrc"
    fi
}

# ---------------------------------------------------------------------------
# Environment variable check
# ---------------------------------------------------------------------------
check_env_vars() {
    local vars=("COORDINATION_API_URL" "COORDINATION_API_KEY")
    local missing=()
    for var in "${vars[@]}"; do
        [[ -z "${!var:-}" ]] && missing+=("$var")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log "Coordinator env not set: ${missing[*]}"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "=== Session Bootstrap — $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    $CHECK_ONLY && log "Mode: --check (dry run)"

    verify_python
    verify_venvs
    verify_openspec
    verify_skills
    verify_frontend
    verify_git
    activate_venv
    check_env_vars

    if [[ ${#REPAIRED[@]} -gt 0 ]]; then
        log "Repaired ${#REPAIRED[@]} item(s): ${REPAIRED[*]}"
    fi
    if [[ ${#WARNINGS[@]} -gt 0 ]]; then
        log "Warnings: ${WARNINGS[*]}"
    fi

    return 0
}

trap 'log "Bootstrap finished (trapped)"; exit 0' ERR
main
exit 0
