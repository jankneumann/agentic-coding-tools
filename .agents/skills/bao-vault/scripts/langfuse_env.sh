#!/usr/bin/env bash
# langfuse_env.sh — Resolve LANGFUSE_* credentials from OpenBao and emit shell exports.
#
# Usage:
#   eval "$(skills/bao-vault/scripts/langfuse_env.sh)"
#
# Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from the KV v2
# path configured by BAO_MOUNT_PATH/BAO_SECRET_PATH (defaults: secret/coordinator),
# computes LANGFUSE_BASIC_AUTH from the public+secret pair, and prints export lines.
#
# Authentication uses BAO_TOKEN if set, otherwise BAO_ROLE_ID + BAO_SECRET_ID via
# the AppRole login flow (matching skills/bao-vault/scripts/bao_seed.py).
#
# Falls back to existing environment values when OpenBao is unavailable, so it is
# safe to eval unconditionally during shell init.
set -euo pipefail

bao_addr="${BAO_ADDR:-}"
mount_path="${BAO_MOUNT_PATH:-secret}"
secret_path="${BAO_SECRET_PATH:-coordinator}"

emit_export() {
    local name="$1" value="$2"
    [ -z "$value" ] && return
    printf 'export %s=%q\n' "$name" "$value"
}

emit_basic_auth() {
    local pk="$1" sk="$2"
    [ -z "$pk" ] || [ -z "$sk" ] && return
    local token
    token=$(printf '%s:%s' "$pk" "$sk" | base64 | tr -d '\n')
    printf 'export LANGFUSE_BASIC_AUTH=%q\n' "$token"
}

# Resolution order: explicit env > OpenBao > nothing.
pk="${LANGFUSE_PUBLIC_KEY:-}"
sk="${LANGFUSE_SECRET_KEY:-}"
host="${LANGFUSE_HOST:-}"

skip_bao=false
[ -z "$bao_addr" ] && skip_bao=true
[ -n "$pk" ] && [ -n "$sk" ] && skip_bao=true

if [ "$skip_bao" = "true" ]; then
    : # Already populated from environment, or no BAO_ADDR configured.
else
    if ! command -v curl >/dev/null 2>&1; then
        echo "# langfuse_env.sh: curl missing, cannot reach OpenBao" >&2
    else
        token="${BAO_TOKEN:-}"
        if [ -z "$token" ] && [ -n "${BAO_ROLE_ID:-}" ] && [ -n "${BAO_SECRET_ID:-}" ]; then
            token=$(curl -fsS \
                -X POST \
                -H "Content-Type: application/json" \
                --data "{\"role_id\":\"${BAO_ROLE_ID}\",\"secret_id\":\"${BAO_SECRET_ID}\"}" \
                "${bao_addr}/v1/auth/approle/login" \
                | sed -n 's/.*"client_token":"\([^"]*\)".*/\1/p')
        fi
        if [ -n "$token" ]; then
            payload=$(curl -fsS \
                -H "X-Vault-Token: ${token}" \
                "${bao_addr}/v1/${mount_path}/data/${secret_path}" || echo "")
            extract() {
                printf '%s' "$payload" | sed -n "s/.*\"$1\":\"\\([^\"]*\\)\".*/\\1/p" | head -n1
            }
            [ -z "$pk"   ] && pk=$(extract LANGFUSE_PUBLIC_KEY)
            [ -z "$sk"   ] && sk=$(extract LANGFUSE_SECRET_KEY)
            [ -z "$host" ] && host=$(extract LANGFUSE_HOST)
        fi
    fi
fi

emit_export LANGFUSE_PUBLIC_KEY "$pk"
emit_export LANGFUSE_SECRET_KEY "$sk"
emit_export LANGFUSE_HOST "$host"
emit_basic_auth "$pk" "$sk"
