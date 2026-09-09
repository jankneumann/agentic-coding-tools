#!/usr/bin/env bash
set -euo pipefail

target=""
out_dir=""
mode="baseline"
api_format="openapi"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { echo "Missing value for --target" >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    --out)
      [[ $# -ge 2 ]] || { echo "Missing value for --out" >&2; exit 2; }
      out_dir="$2"
      shift 2
      ;;
    --mode)
      [[ $# -ge 2 ]] || { echo "Missing value for --mode" >&2; exit 2; }
      mode="$2"
      shift 2
      ;;
    --api-format)
      [[ $# -ge 2 ]] || { echo "Missing value for --api-format" >&2; exit 2; }
      api_format="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./run_zap_scan.sh --target <url-or-spec> [--out <dir>] [--mode baseline|api|full] [--api-format openapi|graphql]
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$target" ]]; then
  echo "--target is required" >&2
  exit 2
fi

if [[ -z "$out_dir" ]]; then
  out_dir="$(pwd)/docs/security-review"
fi
mkdir -p "$out_dir"

report_json="$out_dir/zap-report.json"
status=""
message=""
container_runtime=""

detect_container_runtime() {
  if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
    echo "podman"
    return 0
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "docker"
    return 0
  fi
  return 1
}

container_runtime="$(detect_container_runtime || true)"

if [[ -z "$container_runtime" ]]; then
  status="unavailable"
  message="container runtime unavailable for ZAP scan (requires docker or podman)"
elif [[ $dry_run -eq 1 ]]; then
  status="ok"
  message="dry-run: zap $mode scan would execute via $container_runtime"
else
  case "$mode" in
    baseline)
      zap_cmd=(zap-baseline.py -t "$target" -J zap-report.json -r zap-report.html -m 5)
      ;;
    api)
      zap_cmd=(zap-api-scan.py -t "$target" -f "$api_format" -J zap-report.json -r zap-report.html)
      ;;
    full)
      zap_cmd=(zap-full-scan.py -t "$target" -J zap-report.json -r zap-report.html)
      ;;
    *)
      echo "Invalid --mode: $mode" >&2
      exit 2
      ;;
  esac

  run_args=(run --rm)

  # Loopback targets need the host network namespace; a bridged container
  # resolves `localhost` to itself. Measured on podman 4.9.3 against a
  # 127.0.0.1-bound service: --network=host reaches it (HTTP 200), while
  # --add-host=host.docker.internal:host-gateway does not (HTTP 000), because a
  # service bound to loopback is not reachable through the host gateway at all.
  # The frontend descriptors this scanner is pointed at MUST bind 127.0.0.1
  # (design D7 of factory-missions-architecture-alignment), so host networking
  # is the only posture that can scan them.
  #
  # Scoped deliberately: a remote target keeps the container in its own network
  # namespace. While scanning a loopback target the scanner does share the
  # host's loopback and could in principle reach other 127.0.0.1 services, which
  # is the accepted cost of being able to scan them at all.
  target_host="$target"
  target_host="${target_host#*://}"          # strip scheme
  target_host="${target_host##*@}"           # strip userinfo
  case "$target_host" in
    # Bracketed IPv6 ("[::1]:9"): the host runs to the closing bracket, so the
    # port colon cannot be found by cutting at the first ':'.
    \[*) target_host="${target_host%%\]*}"; target_host="${target_host#\[}" ;;
    *)   target_host="${target_host%%[:/?]*}" ;;
  esac
  case "$target_host" in
    localhost|127.0.0.1|0.0.0.0|::1)
      run_args+=(--network=host)
      ;;
    # 127.0.0.0/8 is all loopback, not just .0.0.1.
    127.*)
      run_args+=(--network=host)
      ;;
  esac

  # Rootless podman maps the container's `zap` user to a subuid that cannot
  # write into a host-owned bind mount, so the report job died with
  # `AccessDeniedException /zap/wrk/zap-report.json` and the scan produced no
  # artifact to parse. keep-id maps it back to the invoking user. Docker's
  # default (non-userns-remap) mapping already writes as the host user, so this
  # is podman-only rather than unconditional.
  if [[ "$container_runtime" == "podman" ]]; then
    run_args+=(--userns=keep-id)
  fi

  set +e
  "$container_runtime" "${run_args[@]}" \
    -v "$out_dir":/zap/wrk \
    ghcr.io/zaproxy/zaproxy:stable \
    "${zap_cmd[@]}" >/tmp/security-review-zap.log 2>&1
  rc=$?
  set -e

  # zap-baseline.py / zap-api-scan.py / zap-full-scan.py exit codes:
  #   0  ran, nothing at or above the configured threshold
  #   1  ran, at least one FAIL-level alert
  #   2  ran, at least one WARN-level alert (absent -I)
  #   3  did NOT run (target unreachable, internal error)
  #
  # Mapping every non-zero code to "error" conflated "found something" with
  # "never ran", and the aggregate gate turns "never ran" into NOT CHECKED —
  # which `--allow-degraded-pass` then converts into a PASS. A scan that found
  # real vulnerabilities was therefore reported as a clean degraded pass with
  # zero findings. Verified 2026-09-09: rc=3 with no host networking (genuinely
  # unreachable) versus rc=2 with it, from a run whose report parsed to 12
  # findings, 2 of them medium.
  #
  # 0/1/2 are all "the scanner ran": the report is written, the parser reads it,
  # and the severity gate — not this wrapper — decides the verdict.
  if [[ $rc -eq 0 || $rc -eq 1 || $rc -eq 2 ]]; then
    status="ok"
    message="zap $mode scan completed via $container_runtime (exit $rc)"
  else
    status="error"
    message="zap $mode scan failed to run via $container_runtime (exit $rc)"
  fi
fi

if [[ $dry_run -eq 1 ]]; then
  cat > "$report_json" <<'JSON'
{"site": [{"name": "dry-run", "alerts": []}]}
JSON
fi

printf '{"scanner":"zap","status":"%s","mode":"%s","runtime":"%s","report_path":"%s","message":"%s"}\n' \
  "$status" "$mode" "${container_runtime:-none}" "$report_json" "${message//\"/\\\"}"

if [[ "$status" == "error" || "$status" == "unavailable" ]]; then
  exit 4
fi
