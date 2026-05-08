#!/usr/bin/env bash
# install-mcp.sh — register the Langfuse MCP server with Claude Code, Codex, and Gemini.
#
# Targets and idempotency:
#   - Claude Code: <repo>/.mcp.json (project-scoped, committed). Uses ${LANGFUSE_BASIC_AUTH}
#     env var reference (Claude Code interpolates these at server-start time).
#   - Codex CLI:   ~/.codex/config.toml (USER-GLOBAL — Codex has no project-scope MCP file).
#     Stores the resolved Basic-auth token literally because Codex's TOML reader
#     does not interpolate env vars in header values.
#   - Gemini CLI:  ~/.gemini/settings.json (USER-GLOBAL). Stores the resolved Basic-auth
#     token literally for the same reason.
#
# Re-running this script overwrites only the langfuse entry in each target.
#
# Usage:
#   bash skills/langfuse/scripts/install-mcp.sh                    # all three agents (default)
#   bash skills/langfuse/scripts/install-mcp.sh --no-codex         # skip Codex
#   bash skills/langfuse/scripts/install-mcp.sh --no-gemini        # skip Gemini
#   bash skills/langfuse/scripts/install-mcp.sh --claude-only      # only .mcp.json
#   bash skills/langfuse/scripts/install-mcp.sh --lock-read-only   # deny write tools (Claude Code)
#   bash skills/langfuse/scripts/install-mcp.sh --host us          # US cloud
#   bash skills/langfuse/scripts/install-mcp.sh --host self-hosted --url https://lf.example.com
#
# Credentials (Codex/Gemini only — Claude Code uses env var reference):
#   Resolved from LANGFUSE_PUBLIC_KEY+LANGFUSE_SECRET_KEY (preferred) or LANGFUSE_BASIC_AUTH.
#   Easiest source is the OpenBao bridge:
#     eval "$(skills/bao-vault/scripts/langfuse_env.sh)"
#
# Requires: jq, base64, python3.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & arg parsing
# ---------------------------------------------------------------------------

LOCK_READ_ONLY=0
HOST_REGION="eu"
CUSTOM_URL=""
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
WRITE_CODEX=1
WRITE_GEMINI=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lock-read-only) LOCK_READ_ONLY=1; shift ;;
    --host) HOST_REGION="$2"; shift 2 ;;
    --url) CUSTOM_URL="$2"; shift 2 ;;
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --no-codex) WRITE_CODEX=0; shift ;;
    --no-gemini) WRITE_GEMINI=0; shift ;;
    --claude-only) WRITE_CODEX=0; WRITE_GEMINI=0; shift ;;
    -h|--help)
      sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$HOST_REGION" in
  eu)          MCP_URL="https://cloud.langfuse.com/api/public/mcp" ;;
  us)          MCP_URL="https://us.cloud.langfuse.com/api/public/mcp" ;;
  jp)          MCP_URL="https://jp.cloud.langfuse.com/api/public/mcp" ;;
  hipaa)       MCP_URL="https://hipaa.cloud.langfuse.com/api/public/mcp" ;;
  self-hosted) MCP_URL="${CUSTOM_URL:?--host self-hosted requires --url}" ;;
  *) echo "Unknown --host: $HOST_REGION (use eu|us|jp|hipaa|self-hosted)" >&2; exit 2 ;;
esac

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

command -v jq >/dev/null 2>&1 || { echo "jq required" >&2; exit 1; }

if [[ ! -d "$REPO_ROOT/.git" ]]; then
  echo "Warning: $REPO_ROOT does not look like a git repo root. Continuing." >&2
fi

# ---------------------------------------------------------------------------
# Compose the langfuse server entry
# ---------------------------------------------------------------------------

LANGFUSE_ENTRY=$(jq -n --arg url "$MCP_URL" '{
  type: "http",
  url: $url,
  headers: { Authorization: "Basic ${LANGFUSE_BASIC_AUTH}" }
}')

MCP_FILE="$REPO_ROOT/.mcp.json"

if [[ -f "$MCP_FILE" ]]; then
  # Merge into existing file
  jq --argjson entry "$LANGFUSE_ENTRY" \
    '.mcpServers.langfuse = $entry' \
    "$MCP_FILE" > "$MCP_FILE.tmp"
  mv "$MCP_FILE.tmp" "$MCP_FILE"
  echo "Updated langfuse entry in $MCP_FILE"
else
  jq -n --argjson entry "$LANGFUSE_ENTRY" \
    '{ mcpServers: { langfuse: $entry } }' \
    > "$MCP_FILE"
  echo "Created $MCP_FILE"
fi

# ---------------------------------------------------------------------------
# Codex (~/.codex/config.toml — USER-GLOBAL)
# ---------------------------------------------------------------------------

resolve_auth_token() {
  if [[ -n "${LANGFUSE_PUBLIC_KEY:-}" && -n "${LANGFUSE_SECRET_KEY:-}" ]]; then
    AUTH_TOKEN=$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64 | tr -d '\n')
  elif [[ -n "${LANGFUSE_BASIC_AUTH:-}" ]]; then
    AUTH_TOKEN="$LANGFUSE_BASIC_AUTH"
  else
    cat >&2 <<'EOF'
ERROR: Codex/Gemini install needs a resolved Basic-auth token.
       Set LANGFUSE_PUBLIC_KEY+LANGFUSE_SECRET_KEY or LANGFUSE_BASIC_AUTH first.

       From OpenBao:
         eval "$(skills/bao-vault/scripts/langfuse_env.sh)"

       Or skip these targets:
         --no-codex --no-gemini   (or --claude-only)
EOF
    exit 1
  fi
}

if [[ "$WRITE_CODEX" -eq 1 ]]; then
  resolve_auth_token
  CODEX_FILE="$HOME/.codex/config.toml"
  mkdir -p "$(dirname "$CODEX_FILE")"
  touch "$CODEX_FILE"

  python3 - "$CODEX_FILE" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text() if p.exists() else ""
# Strip [mcp_servers.langfuse] and any [mcp_servers.langfuse.<sub>] sections.
pattern = re.compile(r'(?ms)^\[mcp_servers\.langfuse(?:\.[^\]]+)?\][^\[]*?(?=^\[|\Z)')
text = pattern.sub('', text).rstrip()
p.write_text(text + ('\n' if text else ''))
PY

  cat >> "$CODEX_FILE" <<EOF

[mcp_servers.langfuse]
url = "$MCP_URL"

[mcp_servers.langfuse.headers]
Authorization = "Basic $AUTH_TOKEN"
EOF
  echo "Updated $CODEX_FILE (USER-GLOBAL; contains literal Basic-auth token)"
fi

# ---------------------------------------------------------------------------
# Gemini (~/.gemini/settings.json — USER-GLOBAL)
# ---------------------------------------------------------------------------

if [[ "$WRITE_GEMINI" -eq 1 ]]; then
  resolve_auth_token
  GEMINI_FILE="$HOME/.gemini/settings.json"
  mkdir -p "$(dirname "$GEMINI_FILE")"

  GEMINI_ENTRY=$(jq -n --arg url "$MCP_URL" --arg auth "Basic $AUTH_TOKEN" '{
    httpUrl: $url,
    headers: { Authorization: $auth }
  }')

  if [[ -f "$GEMINI_FILE" ]]; then
    jq --argjson entry "$GEMINI_ENTRY" \
      '.mcpServers = ((.mcpServers // {}) + { langfuse: $entry })' \
      "$GEMINI_FILE" > "$GEMINI_FILE.tmp"
    mv "$GEMINI_FILE.tmp" "$GEMINI_FILE"
  else
    jq -n --argjson entry "$GEMINI_ENTRY" \
      '{ mcpServers: { langfuse: $entry } }' \
      > "$GEMINI_FILE"
  fi
  echo "Updated $GEMINI_FILE (USER-GLOBAL; contains literal Basic-auth token)"
fi

# ---------------------------------------------------------------------------
# Read-only: deny write tools in .claude/settings.json
# ---------------------------------------------------------------------------

WRITE_TOOLS=(
  "mcp__langfuse__createTextPrompt"
  "mcp__langfuse__createChatPrompt"
  "mcp__langfuse__updatePromptLabels"
)

SETTINGS_FILE="$REPO_ROOT/.claude/settings.json"

if [[ "$LOCK_READ_ONLY" -ne 1 ]]; then
  echo "Default (read/write): no deny rules added. Pass --lock-read-only to insert them."
else
  if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "Note: $SETTINGS_FILE does not exist; skipping deny rules." >&2
    echo "      Create it with a 'permissions.deny' array containing:" >&2
    printf '      - %s\n' "${WRITE_TOOLS[@]}" >&2
  else
    # Add each write tool to permissions.deny if not already present
    DENY_JSON=$(printf '%s\n' "${WRITE_TOOLS[@]}" | jq -R . | jq -s .)
    jq --argjson tools "$DENY_JSON" '
      .permissions = (.permissions // {})
      | .permissions.deny = ((.permissions.deny // []) + $tools | unique)
    ' "$SETTINGS_FILE" > "$SETTINGS_FILE.tmp"
    mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
    echo "Added Langfuse write-tool deny rules to $SETTINGS_FILE"
  fi
fi

# ---------------------------------------------------------------------------
# Reminder
# ---------------------------------------------------------------------------

cat <<EOF

Done. Targets:
  - Claude Code  : $MCP_FILE (project-scoped; uses \${LANGFUSE_BASIC_AUTH})
$([[ "$WRITE_CODEX"  -eq 1 ]] && echo "  - Codex CLI    : \$HOME/.codex/config.toml (user-global; literal token)")
$([[ "$WRITE_GEMINI" -eq 1 ]] && echo "  - Gemini CLI   : \$HOME/.gemini/settings.json (user-global; literal token)")

Next:
  1. Ensure Claude Code can resolve \${LANGFUSE_BASIC_AUTH}:
       eval "\$(skills/bao-vault/scripts/langfuse_env.sh)"   # OpenBao path
       # or export the var manually in your shell profile.

  2. Restart each agent CLI so it picks up the new MCP entry.

  3. Verify by calling mcp__langfuse__listPrompts({}).

Mode: $([[ "$LOCK_READ_ONLY" -eq 1 ]] && echo "READ-ONLY (deny rules added)" || echo "READ/WRITE (default)")
URL : $MCP_URL
EOF
