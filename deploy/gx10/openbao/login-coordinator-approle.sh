#!/usr/bin/env bash
# Exchange the coordinator's AppRole for a short-lived token.
#
# The role id and secret id arrive as systemd credentials, so they are never
# in the environment or the process table. The resulting token lands in the
# 0700 runtime directory for render-coordinator-secrets.sh to consume.
set -euo pipefail
umask 077

RUNTIME_DIR="${GX10_RUNTIME_DIR:-/run/aca/gx10}"
BAO_ADDR="${GX10_BAO_ADDR:-http://10.89.0.250:8200/v1}"
CRED_DIR="${CREDENTIALS_DIRECTORY:?systemd credentials are required}"

role_id="$(<"$CRED_DIR/coord-role-id")"
secret_id="$(<"$CRED_DIR/coord-secret-id")"
[[ -n "$role_id" && -n "$secret_id" ]] || { echo "coordinator AppRole credentials are empty" >&2; exit 1; }

install -d -m 0700 "$RUNTIME_DIR"
payload="$(mktemp "$RUNTIME_DIR/coord-approle.XXXXXX")"
trap 'rm -f -- "$payload"' EXIT
/usr/bin/jq -nc --arg r "$role_id" --arg s "$secret_id" \
  '{role_id:$r, secret_id:$s}' >"$payload"
chmod 0600 "$payload"

token="$(/usr/bin/curl --fail --silent --show-error \
  --request POST --data "@$payload" \
  "$BAO_ADDR/auth/approle/login" | /usr/bin/jq -er '.auth.client_token')" || {
    echo "coordinator AppRole login failed" >&2; exit 1; }

tmp="$(mktemp "$RUNTIME_DIR/coordinator-openbao-token.XXXXXX")"
printf '%s' "$token" >"$tmp"
chmod 0600 "$tmp"
mv -f "$tmp" "$RUNTIME_DIR/coordinator-openbao-token"
