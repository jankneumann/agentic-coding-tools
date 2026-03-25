#!/usr/bin/env bash
# Worktree bootstrap: copy environment files and install dependencies.
#
# Usage: scripts/worktree-bootstrap.sh <worktree-path> <main-repo-path>
#
# Non-fatal: prints warnings on failure but always exits 0.
# Idempotent: safe to run multiple times.

set -u

WORKTREE_PATH="${1:?Usage: worktree-bootstrap.sh <worktree-path> <main-repo-path>}"
MAIN_REPO="${2:?Usage: worktree-bootstrap.sh <worktree-path> <main-repo-path>}"

# Log agent identity if provided (set by worktree.py setup --agent-id)
if [ -n "${AGENT_ID:-}" ]; then
    echo "Agent ID: $AGENT_ID"
fi

# Share uv cache across worktrees
export UV_CACHE_DIR="${MAIN_REPO}/.uv-cache"

errors=0

# --- Copy environment files ---
for f in .env .secrets.yaml; do
    # Skip .secrets.yaml when OpenBao is enabled — agents authenticate independently
    if [ "${f}" = ".secrets.yaml" ] && [ -n "${BAO_ADDR:-}" ]; then
        echo "Skipping ${f} (BAO_ADDR is set — using OpenBao for secrets)"
        continue
    fi
    if [ -f "${MAIN_REPO}/${f}" ]; then
        cp "${MAIN_REPO}/${f}" "${WORKTREE_PATH}/${f}" 2>/dev/null && \
            echo "Copied ${f}" || \
            { echo "Warning: failed to copy ${f}" >&2; errors=$((errors + 1)); }
    fi
done

# --- Install Python dependencies ---
if [ -f "${WORKTREE_PATH}/agent-coordinator/pyproject.toml" ]; then
    echo "Installing agent-coordinator dependencies..."
    (cd "${WORKTREE_PATH}/agent-coordinator" && uv sync --all-extras 2>&1) || \
        { echo "Warning: uv sync failed in agent-coordinator" >&2; errors=$((errors + 1)); }
fi

if [ -f "${WORKTREE_PATH}/skills/pyproject.toml" ]; then
    echo "Installing skills dependencies..."
    (cd "${WORKTREE_PATH}/skills" && uv sync --all-extras 2>&1) || \
        { echo "Warning: uv sync failed in skills" >&2; errors=$((errors + 1)); }
fi

# --- Sync skills ---
if [ -f "${WORKTREE_PATH}/skills/install.sh" ]; then
    echo "Syncing skills..."
    (cd "${WORKTREE_PATH}" && bash skills/install.sh --mode rsync --force --deps none --python-tools none 2>&1) || \
        { echo "Warning: skills install failed" >&2; errors=$((errors + 1)); }
fi

if [ "${errors}" -gt 0 ]; then
    echo "Bootstrap completed with ${errors} warning(s)" >&2
else
    echo "Bootstrap completed successfully"
fi

# Always exit 0 — bootstrap failures are non-fatal
exit 0
