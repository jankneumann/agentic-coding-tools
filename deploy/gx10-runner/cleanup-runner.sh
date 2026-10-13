#!/usr/bin/env bash
# Best-effort removal of this instance's runner registration (design D5).
#
# Usage: cleanup-runner.sh <instance>
#
# Runs as the unit's ExecStopPost. A JIT runner deregisters itself after its job, so the
# registration normally no longer exists; this removes it only when it is still registered
# AND offline (a never-used or crashed runner). It always exits 0.
set -uo pipefail
umask 077

instance="${1:-}"
repo="${GX10_RUNNER_REPO:-}"
api="${GX10_GITHUB_API:-https://api.github.com}"
env_file="${XDG_RUNTIME_DIR:-/nonexistent}/gx10-runner/${instance}.env"

log() { printf 'cleanup-runner[%s]: %s\n' "$instance" "$*" >&2; }

main() {
  [[ -n "$instance" && -n "$repo" && -f "$env_file" ]] || return 0
  local rid token_file work code status
  rid="$(sed -n 's/^GX10_RUNNER_ID=//p' "$env_file" | head -n1)"
  # The env file holds the single-use JIT config; drop it whatever happens next.
  rm -f "$env_file"
  [[ "$rid" =~ ^[0-9]+$ ]] || return 0

  token_file=""
  if [[ -n "${CREDENTIALS_DIRECTORY:-}" && -f "${CREDENTIALS_DIRECTORY}/github-token" ]]; then
    token_file="${CREDENTIALS_DIRECTORY}/github-token"
  elif [[ -n "${GX10_RUNNER_TOKEN_FILE:-}" ]]; then
    token_file="${GX10_RUNNER_TOKEN_FILE}"
  fi
  [[ -n "$token_file" && -f "$token_file" ]] || { log "no credential; skipping"; return 0; }

  work="$(mktemp -d)"
  trap 'rm -rf "$work"' RETURN
  { printf 'Authorization: Bearer '; tr -d '\r\n' < "$token_file"; printf '\n'; } > "$work/auth"
  local common=(-sS --max-time 30 -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28" -H "@$work/auth" -o "$work/body" -w '%{http_code}')

  code="$(curl "${common[@]}" -X GET "${api}/repos/${repo}/actions/runners/${rid}" 2>/dev/null)" || code=000
  if [[ "$code" != 2* ]]; then
    log "runner $rid not registered (HTTP $code); nothing to delete"
    return 0
  fi
  status="$(jq -r '.status // empty' "$work/body" 2>/dev/null)"
  if [[ "$status" == "offline" ]]; then
    code="$(curl "${common[@]}" -X DELETE "${api}/repos/${repo}/actions/runners/${rid}" 2>/dev/null)" || code=000
    log "deleted offline runner $rid: HTTP $code"
  else
    log "runner $rid is '$status'; leaving it"
  fi
  return 0
}

main "$@" || true
exit 0
