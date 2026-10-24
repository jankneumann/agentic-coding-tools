#!/usr/bin/env bash
# Operator step: provision everything the coordinator reads from the shared
# OpenBao -- its policy, its AppRole, the AppRole credentials the secrets unit
# loads, and secret/coordinator/gx10/runtime. Safe to re-run: it reads the
# stored secret, merges, and writes it back, so rotating one field never drops
# the others.
#
# Values are read from the terminal, never argv: argv is world-readable in
# /proc and lands in shell history. A blank answer keeps the stored value.
#
#   sudo deploy/gx10/openbao/provision-coordinator.sh [--import-keys FILE] [--rotate-secret-id]
#
# --import-keys FILE   JSON {"coordination_api_keys": "k1,k2", "coordination_api_key_identities":
#                      "{...}"} -- the Railway values, carried over so no client needs a new key.
# --rotate-secret-id   mint a new AppRole secret id and destroy the one on disk.
set -euo pipefail
umask 077
BAO_ADDR="${GX10_BAO_ADDR:-http://10.89.0.250:8200/v1}"
TOKEN_FILE="${GX10_BAO_TOKEN_FILE:-/etc/aca/gx10/bao-bootstrap-token}"
CRED_DIR="${GX10_COORD_CRED_DIR:-/etc/aca/gx10}"
RUNTIME_ENDPOINT="/secret/data/coordinator/gx10/runtime"
ROLE="aca-gx10-coordinator"
POLICY_FILE="$(dirname "$0")/aca-gx10-coordinator.hcl"
# Keep in step with render-coordinator-secrets.sh, which refuses to render without each one.
REQUIRED=(postgres_password coordination_api_keys coordination_api_key_identities
  coordination_api_key sse_signing_key cf_access_team_domain cf_access_aud
  langfuse_public_key langfuse_secret_key)

import_file=""; rotate=0
while (($#)); do
  case "$1" in
    --import-keys) import_file="${2:?--import-keys needs a file}"; shift 2 ;;
    --rotate-secret-id) rotate=1; shift ;;
    *) echo "usage: ${0##*/} [--import-keys FILE] [--rotate-secret-id]" >&2; exit 2 ;;
  esac
done
[[ -s "$TOKEN_FILE" ]] || { echo "OpenBao admin token unavailable at $TOKEN_FILE" >&2; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf -- "$work"' EXIT
printf 'header = "X-Vault-Token: %s"\n' "$(<"$TOKEN_FILE")" >"$work/curl"
bao() { curl -fsS --config "$work/curl" "$@"; }

health="$(curl -fsS "$BAO_ADDR/sys/health?standbyok=true&perfstandbyok=true")" || {
  echo "OpenBao is unreachable or sealed at $BAO_ADDR" >&2; exit 1; }
jq -e '.initialized == true and .sealed == false' <<<"$health" >/dev/null || {
  echo "OpenBao is uninitialized or sealed" >&2; exit 1; }

# A missing path starts empty; any other failure stops here, because writing
# only this run's fields would silently drop every stored one.
status="$(curl -sS --config "$work/curl" -o "$work/current.json" -w '%{http_code}' "$BAO_ADDR$RUNTIME_ENDPOINT")"
case "$status" in
  200) jq -e '.data.data | objects' "$work/current.json" >"$work/merged.json" ;;
  404) printf '{}\n' >"$work/merged.json" ;;
  *) echo "reading $RUNTIME_ENDPOINT failed with HTTP $status" >&2; exit 1 ;;
esac
# Every edit of the merged secret goes through a temp file, never a truncate-in-place.
update_merged() { jq "$@" "$work/merged.json" >"$work/next.json"; mv -f "$work/next.json" "$work/merged.json"; }
set_field() { VALUE="$2" update_merged --arg f "$1" '.[$f] = env.VALUE'; }
has_field() { jq -e --arg f "$1" 'has($f) and .[$f] != ""' "$work/merged.json" >/dev/null; }
random_key() { od -An -tx1 -N32 /dev/urandom | tr -d ' \n'; }

# The key set and its identity map travel together: a key without an identity
# authenticates as nobody, and an identity without a key is dead weight.
if [[ -n "$import_file" ]]; then
  jq -e '(.coordination_api_keys | type == "string")
         and (.coordination_api_key_identities | fromjson | type == "object")
         and ((.coordination_api_keys | split(",") | sort)
              == (.coordination_api_key_identities | fromjson | keys | sort))' \
    "$import_file" >/dev/null || {
      echo "$import_file: every key needs exactly one identity, and every identity a key" >&2; exit 1; }
  jq -s '.[0] + (.[1] | {coordination_api_keys, coordination_api_key_identities})' \
    "$work/merged.json" "$import_file" >"$work/next.json"
  mv -f "$work/next.json" "$work/merged.json"
  echo "imported $(jq -r '.coordination_api_keys | split(",") | length' "$import_file") keys with their identities" >&2
fi

# The kanban board gets its own key, so revoking it touches nothing else.
if has_field coordination_api_keys && ! jq -e '.coordination_api_key_identities | fromjson
     | any(.[]; .agent_id == "gx10-kanban")' "$work/merged.json" >/dev/null; then
  KANBAN_KEY="$(random_key)" update_merged '.coordination_api_keys += "," + env.KANBAN_KEY
    | .coordination_api_key_identities = (.coordination_api_key_identities | fromjson
        | .[env.KANBAN_KEY] = {agent_id: "gx10-kanban", agent_type: "kanban_viz"} | tojson)'
  echo "added the gx10-kanban identity" >&2
fi

# Generated once and never again. postgres_password above all: the database
# keeps the password it was initialised with, so a new one locks the API out.
# coordination_api_key is what this instance would present when calling out;
# only the MCP HTTP-proxy transport reads it, so it stays outside the accepted set.
for field in postgres_password sse_signing_key coordination_api_key; do
  has_field "$field" || set_field "$field" "$(random_key)"
done

prompt() {
  local field="$1" pattern="$2" hidden="$3" stored value
  stored="$(has_field "$field" && echo stored || echo unset)"
  while true; do
    if [[ "$hidden" == yes ]]; then
      read -rsp "$field [$stored; blank keeps] (hidden): " value; echo >&2
    else
      read -rp "$field [$stored; blank keeps]: " value
    fi
    [[ -n "$value" ]] || return 0
    [[ "$value" =~ $pattern ]] && { set_field "$field" "$value"; return 0; }
    echo "  does not look like a $field; try again" >&2
  done
}
prompt cf_access_team_domain '^https://[a-z0-9-]+\.cloudflareaccess\.com$' no
prompt cf_access_aud '^[0-9a-f]{64}(,[0-9a-f]{64})*$' no
prompt langfuse_public_key '^pk-lf-' no
prompt langfuse_secret_key '^sk-lf-' yes

jq '{data: .}' "$work/merged.json" >"$work/secret.json"
bao -X POST --data-binary "@$work/secret.json" "$BAO_ADDR$RUNTIME_ENDPOINT" >/dev/null

jq -n --rawfile policy "$POLICY_FILE" '{policy:$policy}' >"$work/policy.json"
bao -X PUT --data-binary "@$work/policy.json" "$BAO_ADDR/sys/policies/acl/$ROLE" >/dev/null
# secret_id_ttl 0: the secret id lives on disk and is reused at every boot.
# The analyzer re-mints its own per boot; with a TTL, this unit would fail the
# first boot after the TTL ran out -- a reboot bug, discovered at the worst time.
printf '{"token_policies":["%s"],"token_ttl":"15m","token_max_ttl":"1h","secret_id_ttl":"0"}\n' "$ROLE" >"$work/role.json"
bao -X POST --data-binary "@$work/role.json" "$BAO_ADDR/auth/approle/role/$ROLE" >/dev/null

install -d -m 0700 "$CRED_DIR"
bao "$BAO_ADDR/auth/approle/role/$ROLE/role-id" | jq -er '.data.role_id' \
  | install -m 0600 /dev/stdin "$CRED_DIR/coordinator-role-id"
secret_id_file="$CRED_DIR/coordinator-secret-id"
if [[ ! -s "$secret_id_file" || "$rotate" == 1 ]]; then
  [[ -s "$secret_id_file" ]] && cp -p "$secret_id_file" "$work/old-secret-id"
  bao -X POST "$BAO_ADDR/auth/approle/role/$ROLE/secret-id" | jq -er '.data.secret_id' \
    | install -m 0600 /dev/stdin "$secret_id_file.new"
  mv -f "$secret_id_file.new" "$secret_id_file"
  # Destroy the old one only once the new one is on disk.
  if [[ -s "$work/old-secret-id" ]]; then
    jq -n --rawfile s "$work/old-secret-id" '{secret_id: ($s | rtrimstr("\n"))}' >"$work/destroy.json"
    bao -X POST --data-binary "@$work/destroy.json" "$BAO_ADDR/auth/approle/role/$ROLE/secret-id/destroy" >/dev/null
  fi
  echo "wrote a new AppRole secret id" >&2
fi

missing=()
for field in "${REQUIRED[@]}"; do has_field "$field" || missing+=("$field"); done
echo "stored $(jq -r 'keys | join(", ")' "$work/merged.json")"
if ((${#missing[@]})); then
  echo "still missing: ${missing[*]} -- the secrets unit refuses to render until they are set; re-run to add them"
else
  echo "complete. apply with: systemctl restart aca-gx10-coordinator-secrets.service"
fi
