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

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  status="unavailable"
  message="docker unavailable for ZAP scan"
elif [[ $dry_run -eq 1 ]]; then
  status="ok"
  message="dry-run: zap $mode scan would execute"
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

  set +e
  docker run --rm \
    -v "$out_dir":/zap/wrk \
    ghcr.io/zaproxy/zaproxy:stable \
    "${zap_cmd[@]}" >/tmp/security-review-zap.log 2>&1
  rc=$?
  set -e

  if [[ $rc -eq 0 ]]; then
    status="ok"
    message="zap $mode scan completed"
  else
    status="error"
    message="zap $mode scan failed (exit $rc)"
  fi
fi

if [[ $dry_run -eq 1 ]] && [[ ! -f "$report_json" ]]; then
  cat > "$report_json" <<'JSON'
{"site": [{"name": "dry-run", "alerts": []}]}
JSON
fi

printf '{"scanner":"zap","status":"%s","mode":"%s","report_path":"%s","message":"%s"}\n' \
  "$status" "$mode" "$report_json" "${message//\"/\\\"}"

if [[ "$status" == "error" || "$status" == "unavailable" ]]; then
  exit 4
fi
