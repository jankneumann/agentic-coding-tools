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
native_rc=0
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

if command -v dependency-check >/dev/null 2>&1; then
  mode="native"
  if [[ $dry_run -eq 1 ]]; then
    status="ok"
    message="dry-run: native dependency-check would execute"
  else
    set +e
    dependency-check --scan "$repo" --project "$project" --format JSON --out "$out_dir" >/tmp/security-review-depcheck.log 2>&1
    native_rc=$?
    set -e
    if [[ $native_rc -eq 0 ]]; then
      status="ok"
      message="native dependency-check completed"
    elif [[ -n "$container_runtime" ]]; then
      mode="${container_runtime}-fallback"
      set +e
      "$container_runtime" run --rm \
        -v "$repo":/src \
        -v "$out_dir":/report \
        owasp/dependency-check:latest \
        --scan /src \
        --project "$project" \
        --format JSON \
        --out /report \
        --noupdate >/tmp/security-review-depcheck.log 2>&1
      runtime_rc=$?
      set -e
      if [[ $runtime_rc -eq 0 ]]; then
        status="ok"
        message="native dependency-check failed (exit $native_rc); $container_runtime fallback completed"
      else
        status="error"
        message="native dependency-check failed (exit $native_rc); $container_runtime fallback failed (exit $runtime_rc)"
      fi
    else
      status="error"
      message="native dependency-check failed (exit $native_rc) and container runtime fallback unavailable"
    fi
  fi
elif [[ -n "$container_runtime" ]]; then
  mode="$container_runtime"
  if [[ $dry_run -eq 1 ]]; then
    status="ok"
    message="dry-run: $container_runtime dependency-check would execute"
  else
    set +e
    "$container_runtime" run --rm \
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
      message="$container_runtime dependency-check completed"
    else
      status="error"
      message="$container_runtime dependency-check failed (exit $rc)"
    fi
  fi
else
  mode="none"
  status="unavailable"
  message="dependency-check unavailable (missing binary and container runtime access)"
fi

if [[ $dry_run -eq 1 ]]; then
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

printf '{"scanner":"dependency-check","status":"%s","mode":"%s","runtime":"%s","report_path":"%s","message":"%s"}\n' \
  "$status" "$mode" "${container_runtime:-none}" "$report_path" "${message//\"/\\\"}"

if [[ "$status" == "error" || "$status" == "unavailable" ]]; then
  exit 4
fi
