#!/usr/bin/env bash
# Render /run/aca/gx10/coordinator.env from the shared OpenBao.
#
# Same contract as the analyzer's render-secrets.sh: fetch under an AppRole
# token, write to a temp file, install 0600, then atomically move. The
# coordinator never reads OpenBao itself -- it reads an env file, so a
# compromised API container holds its own secrets and no vault token.
#
# Reads its own path (secret/coordinator/gx10/runtime), not the analyzer's.
# Sharing one OpenBao does not mean sharing one secret path: the AppRole
# policy for this unit grants read on the coordinator path only.
set -euo pipefail
umask 077

RUNTIME_DIR="${GX10_RUNTIME_DIR:-/run/aca/gx10}"
COORD_PATH="${GX10_BAO_COORD_PATH:-secret/coordinator/gx10/runtime}"
BAO_ADDR="${GX10_BAO_ADDR:-http://10.89.0.250:8200/v1}"
BAO_TOKEN_FILE="${GX10_BAO_TOKEN_FILE:-$RUNTIME_DIR/coordinator-openbao-token}"

[[ -s "$BAO_TOKEN_FILE" ]] || { echo "coordinator OpenBao token is unavailable" >&2; exit 1; }

install -d -m 0700 "$RUNTIME_DIR"
CURL_CONFIG="$(mktemp "$RUNTIME_DIR/coord-bao-curl.XXXXXX")"
printf 'header = "X-Vault-Token: %s"\n' "$(<"$BAO_TOKEN_FILE")" >"$CURL_CONFIG"
chmod 0600 "$CURL_CONFIG"

COORD_TMP="$(mktemp "$RUNTIME_DIR/coordinator.env.XXXXXX")"
cleanup() { rm -f -- "$CURL_CONFIG" "$COORD_TMP"; }
trap cleanup EXIT

fetch() {
  local path="$1" key="$2" value
  value="$(/usr/bin/curl --fail --silent --show-error --config "$CURL_CONFIG" \
    "$BAO_ADDR/${path%%/*}/data/${path#*/}" \
    | /usr/bin/jq -er --arg k "$key" '.data.data[$k]')" || {
      echo "coordinator secret $path/$key is unavailable" >&2; exit 1; }
  printf '%s' "$value"
}
emit() { printf '%s=%s\n' "$2" "$(fetch "$3" "$4")" >>"$1"; }

# Postgres: the server reads POSTGRES_PASSWORD, the API reads the DSN. Both
# come from the same stored password so they cannot drift.
COORD_DB_PASSWORD="$(fetch "$COORD_PATH" postgres_password)"
printf 'POSTGRES_PASSWORD=%s\n' "$COORD_DB_PASSWORD" >>"$COORD_TMP"
printf 'POSTGRES_DSN=postgresql://coordinator:%s@coordinator-postgres:5432/coordinator\n' \
  "$COORD_DB_PASSWORD" >>"$COORD_TMP"

# API authentication. COORDINATION_API_KEYS is the server's accepted set;
# COORDINATION_API_KEY is what this instance presents when it calls out.
emit "$COORD_TMP" COORDINATION_API_KEYS "$COORD_PATH" coordination_api_keys
emit "$COORD_TMP" COORDINATION_API_KEY_IDENTITIES "$COORD_PATH" coordination_api_key_identities
emit "$COORD_TMP" COORDINATION_API_KEY "$COORD_PATH" coordination_api_key
emit "$COORD_TMP" COORDINATOR_SSE_SIGNING_KEY "$COORD_PATH" sse_signing_key

# Langfuse: the coordinator's OWN project in the shared instance, so its
# traces and its retention window are separate from the analyzer's.
emit "$COORD_TMP" LANGFUSE_PUBLIC_KEY "$COORD_PATH" langfuse_public_key
emit "$COORD_TMP" LANGFUSE_SECRET_KEY "$COORD_PATH" langfuse_secret_key

install -m 0600 "$COORD_TMP" "$RUNTIME_DIR/coordinator.env.new"
mv -f "$RUNTIME_DIR/coordinator.env.new" "$RUNTIME_DIR/coordinator.env"

# The tunnel's config and credential are rendered here too, so the compose
# file mounts them from the same 0700 runtime directory as everything else
# rather than from the repo.
install -d -m 0700 "$RUNTIME_DIR/cloudflared"
if [[ -n "${GX10_COORD_TUNNEL_CONFIG:-}" && -f "${GX10_COORD_TUNNEL_CONFIG}" ]]; then
  install -m 0600 "$GX10_COORD_TUNNEL_CONFIG" "$RUNTIME_DIR/cloudflared/config.yaml.new"
  mv -f "$RUNTIME_DIR/cloudflared/config.yaml.new" "$RUNTIME_DIR/cloudflared/config.yaml"
fi

# Fail closed: the tunnel config must never publish the secret store, the
# databases, or the MCP transport. On this host OpenBao is the real sealed
# instance holding every secret for BOTH projects.
if [[ -f "$RUNTIME_DIR/cloudflared/config.yaml" ]]; then
  if /usr/bin/grep -qE ':(8200|5432|8123|9000|8082)|openbao|coordinator-postgres|clickhouse|minio' \
      "$RUNTIME_DIR/cloudflared/config.yaml"; then
    echo "tunnel config publishes a service that must never be public" >&2
    exit 1
  fi
fi

echo "coordinator secrets rendered" >&2
