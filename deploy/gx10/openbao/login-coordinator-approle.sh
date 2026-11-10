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
# Keep TimeoutStartSec in aca-gx10-coordinator-secrets.service above this.
WAIT_SECONDS="${GX10_BAO_WAIT_SECONDS:-120}"
RETRY_INTERVAL="${GX10_BAO_RETRY_INTERVAL:-5}"

role_id="$(<"$CRED_DIR/coord-role-id")"
secret_id="$(<"$CRED_DIR/coord-secret-id")"
[[ -n "$role_id" && -n "$secret_id" ]] || { echo "coordinator AppRole credentials are empty" >&2; exit 1; }

install -d -m 0700 "$RUNTIME_DIR"
payload="$(mktemp "$RUNTIME_DIR/coord-approle.XXXXXX")"
response="$(mktemp "$RUNTIME_DIR/coord-approle-response.XXXXXX")"
trap 'rm -f -- "$payload" "$response"' EXIT
/usr/bin/jq -nc --arg r "$role_id" --arg s "$secret_id" \
  '{role_id:$r, secret_id:$s}' >"$payload"
chmod 0600 "$payload"

# OpenBao refuses connections while its container restarts and answers 503
# while it is sealed or still starting. Both pass on their own, so wait them
# out here: if this unit fails, the coordinator's start fails with result
# 'dependency' at once, and a later Restart= of this unit never brings it back.
# A 4xx is a wrong credential, which waiting cannot fix.
deadline=$((SECONDS + WAIT_SECONDS))
while :; do
  status="$(/usr/bin/curl --silent --max-time 10 --output "$response" --write-out '%{http_code}' \
    --request POST --data "@$payload" "$BAO_ADDR/auth/approle/login")" || status=000
  case "$status" in
    2??) break ;;
    000|5??) ;;
    *) echo "coordinator AppRole login refused with HTTP $status" >&2; exit 1 ;;
  esac
  if ((SECONDS >= deadline)); then
    echo "coordinator AppRole login failed: OpenBao still unavailable (HTTP $status) after ${WAIT_SECONDS}s" >&2
    exit 1
  fi
  echo "OpenBao unavailable (HTTP $status); retrying in ${RETRY_INTERVAL}s" >&2
  sleep "$RETRY_INTERVAL"
done

token="$(/usr/bin/jq -er '.auth.client_token' "$response")" || {
    echo "coordinator AppRole login returned no token" >&2; exit 1; }

tmp="$(mktemp "$RUNTIME_DIR/coordinator-openbao-token.XXXXXX")"
printf '%s' "$token" >"$tmp"
chmod 0600 "$tmp"
mv -f "$tmp" "$RUNTIME_DIR/coordinator-openbao-token"
