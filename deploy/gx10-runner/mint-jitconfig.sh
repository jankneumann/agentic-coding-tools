#!/usr/bin/env bash
# Mint a single-use GitHub Actions JIT runner config on the HOST (design D5).
#
# Usage: mint-jitconfig.sh <instance>
#
# Runs as the unit's ExecStartPre. The registration credential is read on the host and
# never written to the container env file; the container receives only the single-use
# encoded JIT config and the runner id.
#
# Environment (from the unit's EnvironmentFile=):
#   GX10_RUNNER_REPO         owner/name (required)
#   GX10_RUNNER_LABELS       comma-separated full label set; runner-assigned defaults are stripped
#   GX10_MINT_MAX_ELAPSED    total retry budget in seconds (default 600; keep < TimeoutStartSec)
#   GX10_MINT_BASE_DELAY     first retry delay in seconds (default 5; doubles, capped at 300)
#   GX10_RUNNER_TOKEN_FILE   credential fallback when $CREDENTIALS_DIRECTORY is unset
#   GX10_GITHUB_API          API base (default https://api.github.com)
#   GX10_HOSTNAME            override for `hostname -s` (tests)
set -euo pipefail
umask 077
# EPOCHREALTIME and awk number formatting follow the locale's decimal separator; a
# comma-decimal LANG inherited by the user manager would break the arithmetic below.
export LC_ALL=C

instance="${1:?usage: mint-jitconfig.sh <instance>}"
repo="${GX10_RUNNER_REPO:?GX10_RUNNER_REPO is not set}"
api="${GX10_GITHUB_API:-https://api.github.com}"
max_elapsed="${GX10_MINT_MAX_ELAPSED:-600}"
base_delay="${GX10_MINT_BASE_DELAY:-5}"
host="${GX10_HOSTNAME:-$(hostname -s)}"
prefix="gx10-${host}-${instance}-"
max_pages=10

log() { printf 'mint-jitconfig[%s]: %s\n' "$instance" "$*" >&2; }

# --- credential -----------------------------------------------------------------------
token_file=""
if [[ -n "${CREDENTIALS_DIRECTORY:-}" && -f "${CREDENTIALS_DIRECTORY}/github-token" ]]; then
  token_file="${CREDENTIALS_DIRECTORY}/github-token"
elif [[ -n "${GX10_RUNNER_TOKEN_FILE:-}" ]]; then
  token_file="${GX10_RUNNER_TOKEN_FILE}"
fi
if [[ -z "$token_file" || ! -f "$token_file" ]]; then
  log "no credential: expected \$CREDENTIALS_DIRECTORY/github-token or GX10_RUNNER_TOKEN_FILE"
  exit 1
fi
mode="$(stat -c '%a' "$token_file")"
if (( (8#$mode) & ~8#600 )); then
  log "refusing credential file $token_file with mode $mode (must be 0600 or narrower)"
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# The Authorization header lives in a 0600 file passed as -H @file, so the credential
# never appears in a process argument list.
{ printf 'Authorization: Bearer '; tr -d '\r\n' < "$token_file"; printf '\n'; } > "$work/auth"

# api_call METHOD URL [JSON_BODY] -> prints the HTTP status; body in $work/body, headers in
# $work/hdr. A transport failure prints 000.
api_call() {
  local method="$1" url="$2" data="${3:-}" code
  local args=(-sS --max-time 30 -X "$method"
    -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28"
    -H "@$work/auth" -D "$work/hdr" -o "$work/body" -w '%{http_code}')
  [[ -n "$data" ]] && args+=(-d "$data")
  code="$(curl "${args[@]}" "$url" 2>/dev/null)" || code="000"
  printf '%s' "${code:-000}"
}

# --- sweep stale registrations of THIS instance (best-effort) -------------------------
# Two passes: list every bounded page first, then delete. Deleting while paging would shift
# later runners onto pages already read, so the next page request would skip them.
sweep() {
  local page=1 url code id name status has_next stale=()
  while (( page <= max_pages )); do
    url="${api}/repos/${repo}/actions/runners?per_page=100&page=${page}"
    code="$(api_call GET "$url")"
    if [[ "$code" != 2* ]]; then
      log "sweep: list runners returned HTTP $code (continuing without sweep)"
      return 0
    fi
    while IFS=$'\t' read -r id name status; do
      [[ -z "$id" ]] && continue
      if [[ "$name" == "$prefix"* && "$status" == "offline" ]]; then
        stale+=("${id}"$'\t'"${name}")
      fi
    done < <(jq -r '.runners[]? | [.id, .name, .status] | @tsv' "$work/body" 2>/dev/null || true)
    has_next=0
    grep -qi '^link:.*rel="next"' "$work/hdr" 2>/dev/null && has_next=1
    (( has_next )) || break
    page=$((page + 1))
  done
  if (( page > max_pages )); then
    log "sweep: reached the ${max_pages}-page bound for instance ${instance}; stale runners beyond it" \
      "are left for the next start (continuing to mint)"
  fi
  local entry
  for entry in "${stale[@]}"; do
    id="${entry%%$'\t'*}"
    name="${entry#*$'\t'}"
    code="$(api_call DELETE "${api}/repos/${repo}/actions/runners/${id}")"
    log "sweep: deleted stale offline runner $name (id $id): HTTP $code"
  done
}
sweep || log "sweep failed (ignored)"

# --- labels: the API takes CUSTOM labels only -----------------------------------------
custom_labels="$(printf '%s' "${GX10_RUNNER_LABELS:-self-hosted,linux,ARM64,gx10}" |
  tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' |
  awk 'NF && tolower($0) != "self-hosted" && tolower($0) != "linux" && tolower($0) != "arm64"' |
  jq -R . | jq -sc .)"

name="${prefix}$(date +%s)"
body="$(jq -nc --arg name "$name" --argjson labels "$custom_labels" \
  '{name: $name, runner_group_id: 1, labels: $labels, work_folder: "_work"}')"

# --- mint with bounded exponential backoff --------------------------------------------
now_us() { local t="${EPOCHREALTIME/./}"; printf '%s' "$t"; }
budget_us="$(awk -v s="$max_elapsed" 'BEGIN { printf "%d", s * 1000000 }')"
start_us="$(now_us)"
attempt=0
env_dir="${XDG_RUNTIME_DIR:?XDG_RUNTIME_DIR is not set}/gx10-runner"
env_file="${env_dir}/${instance}.env"
mkdir -p "$env_dir"
chmod 700 "$env_dir"
rm -f "$env_file"

while :; do
  code="$(api_call POST "${api}/repos/${repo}/actions/runners/generate-jitconfig" "$body")"
  if [[ "$code" == 2* ]]; then
    jit="$(jq -r '.encoded_jit_config // empty' "$work/body")"
    rid="$(jq -r '.runner.id // empty' "$work/body")"
    if [[ -n "$jit" && -n "$rid" ]]; then
      tmp="$(mktemp "${env_dir}/.${instance}.XXXXXX")"
      printf 'ACTIONS_RUNNER_INPUT_JITCONFIG=%s\nGX10_RUNNER_ID=%s\n' "$jit" "$rid" > "$tmp"
      chmod 600 "$tmp"
      mv -f "$tmp" "$env_file"
      log "minted runner $name (id $rid)"
      exit 0
    fi
    log "HTTP $code but the response lacked encoded_jit_config/runner.id"
  elif [[ "$code" != 5* && "$code" != "000" && "$code" != "429" ]]; then
    log "generate-jitconfig failed with non-retryable HTTP $code"
    exit 1
  fi
  delay="$(awk -v b="$base_delay" -v n="$attempt" 'BEGIN { d = b * (2 ^ n); if (d > 300) d = 300; print d }')"
  elapsed_us=$(( $(now_us) - start_us ))
  next_us="$(awk -v d="$delay" 'BEGIN { printf "%d", d * 1000000 }')"
  if (( elapsed_us + next_us > budget_us )); then
    log "retry budget of ${max_elapsed}s spent after $((attempt + 1)) attempt(s) (last HTTP $code)"
    exit 1
  fi
  log "HTTP $code; retrying in ${delay}s (attempt $((attempt + 1)))"
  sleep "$delay"
  attempt=$((attempt + 1))
done
