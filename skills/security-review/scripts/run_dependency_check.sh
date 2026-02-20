#!/usr/bin/env bash
set -euo pipefail

repo="."
out_dir=""
project=""
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      [[ $# -ge 2 ]] || { echo "Missing value for --repo" >&2; exit 2; }
      repo="$2"
      shift 2
      ;;
    --out)
      [[ $# -ge 2 ]] || { echo "Missing value for --out" >&2; exit 2; }
      out_dir="$2"
      shift 2
      ;;
    --project)
      [[ $# -ge 2 ]] || { echo "Missing value for --project" >&2; exit 2; }
      project="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./run_dependency_check.sh [--repo <path>] [--out <dir>] [--project <name>] [--dry-run]
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

repo="$(cd "$repo" && pwd)"
if [[ -z "$project" ]]; then
  project="$(basename "$repo")"
fi
if [[ -z "$out_dir" ]]; then
  out_dir="$repo/docs/security-review"
fi
mkdir -p "$out_dir"

report_path="$out_dir/dependency-check-report.json"
mode=""
status=""
message=""

if command -v dependency-check >/dev/null 2>&1; then
  mode="native"
  if [[ $dry_run -eq 1 ]]; then
    status="ok"
    message="dry-run: native dependency-check would execute"
  else
    set +e
    dependency-check --scan "$repo" --project "$project" --format JSON --out "$out_dir" >/tmp/security-review-depcheck.log 2>&1
    rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
      status="ok"
      message="native dependency-check completed"
    else
      status="error"
      message="native dependency-check failed (exit $rc)"
    fi
  fi
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  mode="docker"
  if [[ $dry_run -eq 1 ]]; then
    status="ok"
    message="dry-run: docker dependency-check would execute"
  else
    set +e
    docker run --rm \
      -v "$repo":/src \
      -v "$out_dir":/report \
      owasp/dependency-check:latest \
      --scan /src \
      --project "$project" \
      --format JSON \
      --out /report \
      --noupdate >/tmp/security-review-depcheck.log 2>&1
    rc=$?
    set -e
    if [[ $rc -eq 0 ]]; then
      status="ok"
      message="docker dependency-check completed"
    else
      status="error"
      message="docker dependency-check failed (exit $rc)"
    fi
  fi
else
  mode="none"
  status="unavailable"
  message="dependency-check unavailable (missing binary and docker access)"
fi

if [[ $dry_run -eq 1 ]] && [[ ! -f "$report_path" ]]; then
  cat > "$report_path" <<'JSON'
{"scanInfo": {"engineVersion": "dry-run"}, "dependencies": []}
JSON
fi

if [[ ! -f "$report_path" ]]; then
  generated="$(find "$out_dir" -maxdepth 1 -name '*.json' | head -1 || true)"
  if [[ -n "$generated" ]]; then
    report_path="$generated"
  fi
fi

printf '{"scanner":"dependency-check","status":"%s","mode":"%s","report_path":"%s","message":"%s"}\n' \
  "$status" "$mode" "$report_path" "${message//\"/\\\"}"

if [[ "$status" == "error" || "$status" == "unavailable" ]]; then
  exit 4
fi
