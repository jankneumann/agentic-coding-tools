#!/usr/bin/env bash
# run_stop_hook.sh — Claude Code Stop-hook wrapper for Langfuse tracing.
#
# Resolves LANGFUSE_* credentials (preferring OpenBao via langfuse_env.sh,
# falling back to inherited environment), then invokes the co-installed hook.
#
# Silently exits 0 when credentials are unavailable so the Stop hook never
# blocks a session.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SKILLS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
BAO_HELPER="$SKILLS_ROOT/bao-vault/scripts/langfuse_env.sh"
HOOK_PY="$SCRIPT_DIR/langfuse_hook.py"

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

if command -v uv >/dev/null 2>&1; then
    exec uv run --quiet --with 'langfuse>=4.14,<5.0' python "$HOOK_PY"
else
    exec python3 "$HOOK_PY"
fi
