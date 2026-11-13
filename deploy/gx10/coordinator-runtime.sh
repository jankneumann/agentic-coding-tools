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
NETWORK_WAIT_SECONDS="${COORD_NETWORK_WAIT_SECONDS:-60}"
NETWORK_RETRY_INTERVAL="${COORD_NETWORK_RETRY_INTERVAL:-5}"
DOWN_TIMEOUT="${COORD_DOWN_TIMEOUT_SECONDS:-30}"

SERVICES=(coordinator-postgres coordinator-api cloudflared)

if [[ ! -x "$COMPOSE_BIN" ]]; then
  echo "gx10 requires the rootful $COMPOSE_BIN provider" >&2
  exit 127
fi

compose() { "$COMPOSE_BIN" -p "$PROJECT" -f "$COMPOSE_FILE" "$@"; }

# The analyzer owns `aca-gx10_application`. If it is missing, podman-compose
# creates its own network with that name and the coordinator comes up unable
# to see Langfuse -- a working stack wired to nothing. At boot the analyzer may
# still be creating it, so wait a bounded time, then fail loudly.
require_external_network() {
  local net=aca-gx10_application deadline=$((SECONDS + NETWORK_WAIT_SECONDS))
  until "$PODMAN" network exists "$net"; do
    if ((SECONDS >= deadline)); then
      printf 'the analyzer runtime must be up first; missing network: %s\n' "$net" >&2
      exit 1
    fi
    sleep "$NETWORK_RETRY_INTERVAL"
  done
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

# Remove rather than stop: podman-compose 1.0.6 meets an existing name with
# `podman start`, reviving the container as it was created -- old image, old
# healthcheck -- instead of recreating it from the current compose file.
sweep_project_containers() {
  "$PODMAN" ps -a --filter "label=io.podman.compose.project=$PROJECT" --format '{{.ID}}' \
    | xargs -r "$PODMAN" rm -f --depend -t "$DOWN_TIMEOUT"
}

case "${1:-}" in
  up)
    require_external_network
    # A failed start leaves its containers for a post-mortem; this is where
    # they go. All state lives on bind mounts, as in the analyzer's runtime.
    sweep_project_containers
    compose up -d
    wait_healthy "${SERVICES[@]}"
    ;;
  down)
    sweep_project_containers
    ;;
  *)
    echo "usage: ${0##*/} {up|down}" >&2
    exit 2
    ;;
esac
