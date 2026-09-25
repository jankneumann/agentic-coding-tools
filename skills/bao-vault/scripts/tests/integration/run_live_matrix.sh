#!/usr/bin/env bash
# Dedicated, hermetic Bao conformance runner. Never inherits PostgREST fixtures.
set -euo pipefail

repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
image='quay.io/openbao/openbao@sha256:11fd73a2102cda9c55d5d881a8c3210303146a7ec1e8ac76f526e175c6d24641'
compose_image="$(sed -n '/^  openbao:/,/^  [a-z]/s/^[[:space:]]*image: //p' "$repo_root/agent-coordinator/docker-compose.yml" | head -n 1)"
if [[ "$compose_image" != "$image" || "$compose_image" == *':latest' ]]; then
  echo 'OpenBao Compose image must match the immutable live matrix image' >&2
  exit 1
fi

if command -v podman >/dev/null 2>&1; then
  engine=podman
elif command -v docker >/dev/null 2>&1; then
  engine=docker
else
  echo 'Podman or Docker is required for the live OpenBao matrix' >&2
  exit 1
fi

container="$($engine run --rm -d -p 127.0.0.1::8200 \
  -e BAO_DEV_ROOT_TOKEN_ID=dev-root-token \
  -e BAO_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
  "$image" server -dev)"
cleanup() {
  "$engine" stop "$container" >/dev/null 2>&1 || true
  if [[ -n "${report:-}" ]]; then rm -f "$report"; fi
}
trap cleanup EXIT
port="$($engine port "$container" 8200/tcp | awk -F: '{print $NF}' | head -n 1)"
[[ "$port" =~ ^[0-9]+$ ]] || { echo 'OpenBao host port unavailable' >&2; exit 1; }
export BAO_ADDR="http://127.0.0.1:$port" BAO_TOKEN=dev-root-token
ready=0
for _ in {1..60}; do
  if curl -fsS --max-time 1 "$BAO_ADDR/v1/sys/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || { echo 'OpenBao did not become healthy' >&2; exit 1; }

python_bin="$repo_root/skills/.venv/bin/python"
[[ -x "$python_bin" ]] || { echo 'Run uv sync --project skills first' >&2; exit 1; }
cd "$repo_root"
report="$(mktemp)"
"$python_bin" -m pytest skills/bao-vault/scripts/tests/integration -q --junitxml="$report"
"$python_bin" - "$report" <<'PY'
import sys
import xml.etree.ElementTree as ET

cases = ET.parse(sys.argv[1]).findall(".//testcase")
passed = sum(case.find("skipped") is None and case.find("failure") is None
             and case.find("error") is None for case in cases)
if passed == 0:
    raise SystemExit("Live OpenBao matrix collected no passing tests")
PY
