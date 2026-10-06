#!/usr/bin/env bash
# Bring the coordinator project up or down on GX-10.
#
# Container lifetime belongs to this script, not to the systemd cgroup: the
# unit runs KillMode=process precisely so a failed start does not SIGTERM every
# conmon in the cgroup and then sit out TimeoutStopSec doing nothing.
set -euo pipefail

ROOT_DIR="${COORD_ROOT_DIR:-/opt/agentic-coding-tools}"
COMPOSE_FILE="${COORD_COMPOSE_FILE:-$ROOT_DIR/deploy/gx10/docker-compose.coordinator.yml}"
PROJECT="${COMPOSE_PROJECT_NAME:-aca-gx10-coord}"
PODMAN="${COORD_PODMAN_BIN:-/usr/bin/podman}"
COMPOSE_BIN="${COORD_COMPOSE_BIN:-/usr/bin/podman-compose}"
WAIT_SECONDS="${COORD_WAIT_SECONDS:-240}"
DOWN_TIMEOUT="${COORD_DOWN_TIMEOUT_SECONDS:-30}"

SERVICES=(coordinator-postgres coordinator-api cloudflared)

if [[ ! -x "$COMPOSE_BIN" ]]; then
  echo "gx10 requires the rootful $COMPOSE_BIN provider" >&2
  exit 127
fi

compose() { "$COMPOSE_BIN" -p "$PROJECT" -f "$COMPOSE_FILE" "$@"; }

# The analyzer owns `aca-gx10_application` and `aca-gx10_egress`. If they are
# missing, podman-compose creates its own networks with those names and the
# coordinator comes up unable to see Langfuse -- a working stack wired to
# nothing. Fail loudly instead.
require_external_networks() {
  local missing=()
  for net in aca-gx10_application aca-gx10_egress; do
    "$PODMAN" network exists "$net" || missing+=("$net")
  done
  if ((${#missing[@]})); then
    printf 'the analyzer runtime must be up first; missing network: %s\n' "${missing[*]}" >&2
    exit 1
  fi
}

wait_healthy() {
  local deadline=$((SECONDS + WAIT_SECONDS))
  local pending=("$@")
  while ((SECONDS < deadline)); do
    local still=()
    for svc in "${pending[@]}"; do
      local name="${PROJECT}_${svc}_1"
      local state
      # A container with no healthcheck reports an empty Health; treat
      # "running" as good for those rather than waiting out the budget.
      state="$("$PODMAN" inspect --format \
        '{{if .State.Health.Status}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        "$name" 2>/dev/null || echo missing)"
      case "$state" in
        healthy|running) ;;
        *) still+=("$svc") ;;
      esac
    done
    pending=("${still[@]}")
    ((${#pending[@]})) || return 0
    sleep 5
  done
  printf 'did not become healthy within %ss: %s\n' "$WAIT_SECONDS" "${pending[*]}" >&2
  for svc in "${pending[@]}"; do
    echo "--- ${PROJECT}_${svc}_1" >&2
    "$PODMAN" logs --tail 40 "${PROJECT}_${svc}_1" 2>&1 | tail -40 >&2 || true
  done
  return 1
}

case "${1:-}" in
  up)
    require_external_networks
    compose up -d
    wait_healthy "${SERVICES[@]}"
    ;;
  down)
    # Remove rather than stop: podman-compose 1.0.6 hashes the whole compose
    # file, and a container left behind from an older file is restarted as-is
    # by a later `up` instead of being recreated.
    "$PODMAN" ps -a --filter "label=io.podman.compose.project=$PROJECT" --format '{{.ID}}' \
      | xargs -r "$PODMAN" rm -f --depend -t "$DOWN_TIMEOUT"
    ;;
  *)
    echo "usage: ${0##*/} {up|down}" >&2
    exit 2
    ;;
esac
