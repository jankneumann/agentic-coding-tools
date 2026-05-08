#!/usr/bin/env bash
# run_stop_hook.sh — Claude Code Stop-hook wrapper for Langfuse tracing.
#
# Resolves LANGFUSE_* credentials (preferring OpenBao via langfuse_env.sh,
# falling back to inherited environment), then invokes the agent-coordinator's
# langfuse_hook.py with the transcript JSON on stdin.
#
# Silently exits 0 when credentials are unavailable so the Stop hook never
# blocks a session.
set -euo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
BAO_HELPER="$REPO_ROOT/skills/bao-vault/scripts/langfuse_env.sh"
HOOK_PY="$REPO_ROOT/agent-coordinator/scripts/langfuse_hook.py"
VENV_PY="$REPO_ROOT/agent-coordinator/.venv/bin/python"

if [ -x "$BAO_HELPER" ]; then
    eval "$(bash "$BAO_HELPER" 2>/dev/null || true)"
fi

if [ ! -f "$HOOK_PY" ]; then
    exit 0
fi

if [ -z "${LANGFUSE_PUBLIC_KEY:-}" ] || [ -z "${LANGFUSE_SECRET_KEY:-}" ]; then
    exit 0
fi

export LANGFUSE_ENABLED=true

if [ -x "$VENV_PY" ]; then
    exec "$VENV_PY" "$HOOK_PY"
elif command -v uv >/dev/null 2>&1; then
    exec uv run --quiet --with 'langfuse>=3.0,<4.0' python "$HOOK_PY"
else
    exec python3 "$HOOK_PY"
fi
