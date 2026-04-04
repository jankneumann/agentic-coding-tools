#!/usr/bin/env bash
# Setup script for Langfuse observability integration.
#
# Usage:
#   ./scripts/setup_langfuse.sh [--cloud|--local|--install-hook]
#
# Options:
#   --local         Start self-hosted Langfuse stack (default)
#   --cloud         Configure for Langfuse Cloud (no Docker needed)
#   --install-hook  Install the Claude Code Stop hook only
#   --check         Verify Langfuse is healthy and reachable

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK_SRC="$SCRIPT_DIR/langfuse_hook.py"
HOOK_DST="$HOME/.claude/hooks/langfuse_hook.py"

# Default config
LANGFUSE_HOST="${LANGFUSE_HOST:-http://localhost:3050}"
LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-pk-lf-local-coding-agents}"
LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-sk-lf-local-coding-agents}"

info() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; }
die()  { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_local() {
    info "Starting self-hosted Langfuse stack (reusing existing Postgres)..."
    cd "$REPO_ROOT"

    # Start the langfuse profile
    docker compose --profile langfuse up -d

    info "Waiting for Langfuse to become healthy..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -sf "${LANGFUSE_HOST}/api/public/health" >/dev/null 2>&1; then
            info "Langfuse is healthy at ${LANGFUSE_HOST}"
            break
        fi
        retries=$((retries - 1))
        sleep 2
    done

    if [ $retries -eq 0 ]; then
        warn "Langfuse did not become healthy within 60s. Check: docker compose --profile langfuse logs langfuse-web"
    fi

    cmd_install_hook
    info "Setup complete! Langfuse UI: ${LANGFUSE_HOST}"
}

cmd_cloud() {
    info "Configuring for Langfuse Cloud..."

    if [ -z "${LANGFUSE_PUBLIC_KEY:-}" ] || [ "$LANGFUSE_PUBLIC_KEY" = "pk-lf-local-coding-agents" ]; then
        die "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY for your Langfuse Cloud project"
    fi

    # Override the default localhost host — the script-level default would
    # have already set LANGFUSE_HOST to localhost, so we must check whether
    # the user explicitly exported a custom host or fall back to cloud URL.
    if [ "$LANGFUSE_HOST" = "http://localhost:3050" ]; then
        LANGFUSE_HOST="https://cloud.langfuse.com"
    fi
    cmd_install_hook
    info "Cloud setup complete! Using ${LANGFUSE_HOST}"
}

cmd_install_hook() {
    info "Installing Claude Code Langfuse hook..."

    # Create hooks directory
    mkdir -p "$(dirname "$HOOK_DST")"

    # Copy hook script
    cp "$HOOK_SRC" "$HOOK_DST"
    chmod +x "$HOOK_DST"

    info "Hook installed at: $HOOK_DST"
    info ""
    info "Add the following to your ~/.claude/settings.json:"
    info ""
    cat <<SETTINGS_EOF
{
  "env": {
    "LANGFUSE_ENABLED": "true",
    "LANGFUSE_PUBLIC_KEY": "${LANGFUSE_PUBLIC_KEY}",
    "LANGFUSE_SECRET_KEY": "${LANGFUSE_SECRET_KEY}",
    "LANGFUSE_HOST": "${LANGFUSE_HOST}"
  },
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run --with 'langfuse>=3.0,<4.0' --python 3.12 ${HOOK_DST}"
          }
        ]
      }
    ]
  }
}
SETTINGS_EOF
    info ""
    info "Or if you have the agent-coordinator venv:"
    info "  \"command\": \"$REPO_ROOT/.venv/bin/python $HOOK_DST\""
}

cmd_check() {
    info "Checking Langfuse health at ${LANGFUSE_HOST}..."

    if curl -sf "${LANGFUSE_HOST}/api/public/health" 2>/dev/null; then
        echo ""
        info "Langfuse is healthy!"
    else
        die "Langfuse is not reachable at ${LANGFUSE_HOST}"
    fi

    # Test API key auth
    info "Testing API key authentication..."
    response=$(curl -sf -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${LANGFUSE_SECRET_KEY}" \
        "${LANGFUSE_HOST}/api/public/health" 2>/dev/null || true)

    if [ "$response" = "200" ] || [ "$response" = "401" ]; then
        info "API endpoint responding (HTTP $response)"
    else
        warn "Unexpected response: HTTP $response"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

case "${1:-local}" in
    --local|local)     cmd_local ;;
    --cloud|cloud)     cmd_cloud ;;
    --install-hook|install-hook) cmd_install_hook ;;
    --check|check)     cmd_check ;;
    --help|-h)
        echo "Usage: $0 [--local|--cloud|--install-hook|--check]"
        echo ""
        echo "  --local         Start self-hosted Langfuse + install hook (default)"
        echo "  --cloud         Configure for Langfuse Cloud"
        echo "  --install-hook  Install the Claude Code Stop hook only"
        echo "  --check         Verify Langfuse health"
        ;;
    *)
        die "Unknown option: $1. Use --help for usage."
        ;;
esac
