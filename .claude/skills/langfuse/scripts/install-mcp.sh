#!/usr/bin/env bash
# install-mcp.sh — register the Langfuse MCP server in this repo's .mcp.json.
#
# Idempotent: re-running updates the langfuse entry in place without touching
# other servers.
#
# Default: project-scoped, read/write (no deny entries added). Pass --lock-read-only
# to additionally insert deny rules for the three write tools into
# .claude/settings.json.
#
# Usage:
#   bash skills/langfuse/scripts/install-mcp.sh                    # read/write
#   bash skills/langfuse/scripts/install-mcp.sh --lock-read-only   # add deny rules
#   bash skills/langfuse/scripts/install-mcp.sh --host us          # US cloud
#   bash skills/langfuse/scripts/install-mcp.sh --host self-hosted --url https://lf.example.com
#
# Requires: jq, base64. The script never writes a resolved auth token —
# .mcp.json references the ${LANGFUSE_BASIC_AUTH} env var, which the user
# must export from their shell profile or secret manager.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & arg parsing
# ---------------------------------------------------------------------------

LOCK_READ_ONLY=0
HOST_REGION="eu"
CUSTOM_URL=""
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lock-read-only) LOCK_READ_ONLY=1; shift ;;
    --host) HOST_REGION="$2"; shift 2 ;;
    --url) CUSTOM_URL="$2"; shift 2 ;;
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
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

Done. To finish setup:

  1. Export credentials in your shell profile (or via your secret manager):

       export LANGFUSE_PUBLIC_KEY=pk-lf-...
       export LANGFUSE_SECRET_KEY=sk-lf-...
       export LANGFUSE_HOST=${MCP_URL%/api/public/mcp}
       export LANGFUSE_BASIC_AUTH=\$(printf '%s:%s' \\
         "\$LANGFUSE_PUBLIC_KEY" "\$LANGFUSE_SECRET_KEY" | base64)

  2. Restart Claude Code so it picks up the new .mcp.json.

  3. Verify by calling mcp__langfuse__listPrompts({}) — it should return
     the prompts in your project.

Mode: $([[ "$LOCK_READ_ONLY" -eq 1 ]] && echo "READ-ONLY (deny rules added)" || echo "READ/WRITE (default)")
URL : $MCP_URL
EOF
