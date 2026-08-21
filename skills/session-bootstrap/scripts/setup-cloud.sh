#!/usr/bin/env bash
# setup-cloud.sh — One-time cloud environment setup.
#
# For the cloud Environment Settings "Setup Script" field of each harness,
# see skills/session-bootstrap/SKILL.md §1.  The snippet differs per harness
# (Claude Code paste-snippet targets */.claude/skills/..., Codex targets
# */.agents/skills/...), because install.sh rsyncs this file into both
# .claude/skills/session-bootstrap/scripts/ and
# .agents/skills/session-bootstrap/scripts/ of the consumer repo.
#
# Do NOT recommend a literal "$(pwd)/.claude/..." path — on Claude Code web
# that resolves to /home/user/.claude/... which doesn't exist, yielding
# "file not found".
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

# Resolve project root — Setup Script can run with cwd = parent of clone on
# Claude Code web (e.g. cwd is /home/user while the repo is at
# /home/user/<reponame>/), so we can't trust $(pwd) alone.  Priority:
#   1. $CLAUDE_PROJECT_DIR (set when Claude Code invokes the script).
#   2. Walk up from the script's own location to the git root (works in both
#      canonical skills/... and installed .claude/skills/... layouts).
#   3. Fall back to $(pwd) if we can't find a git root (keeps old behavior).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Structural fallback, used when git can't answer.  SCRIPT_DIR is always
# <root>/skills/session-bootstrap/scripts (canonical) or
# <root>/{.claude,.agents}/skills/session-bootstrap/scripts (mirror layout),
# so the root is 3 levels up, or 4 when that lands on a mirror directory.
#
# This must NOT fall back to $(pwd): the cloud Setup Script normally runs with
# cwd set to the PARENT of the clone, so pwd-based resolution silently pointed
# PROJECT_DIR at a directory with no skills/ in it.  Every later step then
# "succeeded" by doing nothing, and the session came up with no skills.
resolve_project_dir_from_script() {
    local up3
    up3="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    case "$(basename "$up3")" in
        .claude|.agents) (cd "$up3/.." && pwd) ;;
        *)               printf '%s\n' "$up3" ;;
    esac
}

if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    PROJECT_DIR="$CLAUDE_PROJECT_DIR"
elif git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel >/dev/null 2>&1; then
    PROJECT_DIR="$(git -C "$SCRIPT_DIR/../../.." rev-parse --show-toplevel)"
elif git -C "$SCRIPT_DIR/../../../.." rev-parse --show-toplevel >/dev/null 2>&1; then
    PROJECT_DIR="$(git -C "$SCRIPT_DIR/../../../.." rev-parse --show-toplevel)"
else
    PROJECT_DIR="$(resolve_project_dir_from_script)"
fi

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

    # `${a[@]+"${a[@]}"}` because bash 3.2 (still the default /bin/bash on
    # macOS) treats an empty array as unset under `set -u` and aborts here.
    for target in ${targets[@]+"${targets[@]}"}; do
        local label="${target#"$PROJECT_DIR"/}"
        [[ "$label" == "$PROJECT_DIR" ]] && label="(root)"
        log "Installing $label venv..."
        (cd "$target" && uv sync --all-extras) || log "WARNING: $label uv sync failed"
    done
}

# ---------------------------------------------------------------------------
# OpenSpec CLI
# ---------------------------------------------------------------------------
# Pin shared with CI and scripts/setup-cli.sh.  Empty when the file is absent
# (mirror-layout consumer repos), which falls back to unpinned behavior.
openspec_pin() {
    [[ -f "$PROJECT_DIR/.openspec-version" ]] || return 0
    tr -d '[:space:]' < "$PROJECT_DIR/.openspec-version"
}

install_openspec() {
    local pinned installed
    pinned="$(openspec_pin)"
    installed=""
    command -v openspec >/dev/null 2>&1 && installed="$(openspec --version 2>/dev/null || echo unknown)"

    if [[ -z "$pinned" ]]; then
        if [[ -z "$installed" ]]; then
            log "Installing OpenSpec CLI (unpinned)..."
            npm install -g @fission-ai/openspec || log "WARNING: openspec install failed"
        fi
        return
    fi

    # Version, not presence: a sandbox image or a resumed session can carry an
    # older CLI whose `--strict` semantics disagree with CI (issue #318).
    if [[ "$installed" == "$pinned" ]]; then
        log "OpenSpec CLI $installed (pinned)"
        return
    fi

    log "Installing OpenSpec CLI $pinned (was: ${installed:-absent})..."
    npm install -g "@fission-ai/openspec@$pinned" || log "WARNING: openspec install failed"
}

# ---------------------------------------------------------------------------
# Skills — regenerate runtime mirrors (.claude/skills/, .agents/skills/) from
# the canonical skills/ tree.  In the canonical-layout repo the mirrors are
# gitignored, so a fresh clone ships only skills/ and install.sh must rebuild
# them (otherwise skill discovery and the SessionStart hooks, which live under
# .claude/skills/, are missing).  Mirror-layout consumer repos commit their
# mirrors and have no skills/install.sh — the guard makes this a no-op there.
# ---------------------------------------------------------------------------
install_skills() {
    # -f, not -x: the installer is invoked via `bash <path>`, which needs no
    # execute bit.  Testing -x meant a clone that lost the mode bit fell through
    # to the "committed mirrors" branch and installed nothing.
    local source_installer="$PROJECT_DIR/skills/install.sh"  # source-contribution-only
    if [[ -f "$source_installer" ]]; then
        log "Syncing skill mirrors from canonical skills/ via install.sh..."
        (cd "$PROJECT_DIR" && bash "$source_installer" --mode rsync --force \
            --deps none --python-tools none --openspec-cli none) \
            || log "WARNING: skills install.sh failed"
    else
        log "No canonical skill installer — assuming committed mirrors (consumer-repo layout)"
    fi

    verify_skills_present
}

# Post-condition: the whole point of this script is that the harness finds
# skills under .claude/skills/.  Every install step above is `|| log WARNING`,
# so without this check a failed install (missing rsync, wrong PROJECT_DIR, a
# clone with no skills at all) exits 0 and the session comes up silently
# skill-less.  A setup step that cannot fail cannot tell you it failed.
count_skills() {
    local dir="$1"
    [[ -d "$dir" ]] || { printf '0\n'; return; }
    find "$dir" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l | tr -d '[:space:]'
}

verify_skills_present() {
    local claude_count agents_count
    claude_count="$(count_skills "$PROJECT_DIR/.claude/skills")"
    agents_count="$(count_skills "$PROJECT_DIR/.agents/skills")"

    [[ "$claude_count" -gt 0 ]] && log "Skills present: $claude_count under .claude/skills"
    [[ "$agents_count" -gt 0 ]] && log "Skills present: $agents_count under .agents/skills"

    # Either harness tree satisfies the post-condition.  .claude/ is Claude
    # Code's and .agents/ is Codex's, and a mirror-layout consumer repo
    # legitimately ships only the one its harness reads -- failing a healthy
    # Codex-only checkout because .claude/skills is absent would break the
    # documented Codex setup script for no reason.  What is never right is
    # both trees being empty: no harness can discover anything.
    if [[ "$claude_count" -eq 0 && "$agents_count" -eq 0 ]]; then
        log "ERROR: no skills installed under .claude/skills or .agents/skills"
        log "       PROJECT_DIR=$PROJECT_DIR"
        log "       Harnesses discover skills there; two empty trees mean no"
        log "       skills are available to this session."
        log "       Canonical-layout repos rebuild them with the source installer;"
        log "       mirror-layout repos commit the tree directly."
        log "       Check above for a failed installer run or a wrong PROJECT_DIR."
        return 1
    fi

    # One empty tree is only worth a note: which one is expected depends on
    # which harness the repo targets, and this script cannot tell.
    if [[ "$claude_count" -eq 0 ]]; then
        log "NOTE: no skills under .claude/skills (fine if this repo targets Codex only)"
    elif [[ "$agents_count" -eq 0 ]]; then
        log "NOTE: no skills under .agents/skills (fine if this repo targets Claude only)"
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
