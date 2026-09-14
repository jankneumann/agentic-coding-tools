#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=scanner_images.sh
source "$(dirname "${BASH_SOURCE[0]}")/scanner_images.sh"

repo="."
out_dir=""
project=""
dry_run=0
update_nvd=0
nvd_status=0
# The NVD database is a multi-GB artifact that must outlive the container, so it
# lives outside the repo by default. Scans mount it read-write (H2 opens its own
# lock file) but never update it; only --update-nvd does.
data_dir="${DEPENDENCY_CHECK_DATA_DIR:-$HOME/.cache/dependency-check/data}"
# A CVE database is stale within days, and matching against stale data is not a
# check — it is a check-shaped no-op. 0 disables the floor.
max_db_age_days="${DEPENDENCY_CHECK_MAX_DB_AGE_DAYS:-7}"
# Read from the environment, never from argv: a key on the command line lands in
# the process table and in any shell history that recorded the invocation.
# `.secrets.yaml` -> OpenBao -> env is the path this repo already uses.
nvd_api_key="${NVD_API_KEY:-}"

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
    --data-dir)
      [[ $# -ge 2 ]] || { echo "Missing value for --data-dir" >&2; exit 2; }
      data_dir="$2"
      shift 2
      ;;
    --max-db-age-days)
      [[ $# -ge 2 ]] || { echo "Missing value for --max-db-age-days" >&2; exit 2; }
      max_db_age_days="$2"
      shift 2
      ;;
    --update-nvd)
      update_nvd=1
      shift
      ;;
    --nvd-status)
      nvd_status=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./run_dependency_check.sh [--repo <path>] [--out <dir>] [--project <name>]
                                 [--data-dir <path>] [--max-db-age-days <n>]
                                 [--update-nvd] [--dry-run]

Scanning keeps --noupdate and reads a database seeded separately, so a scan's
verdict never depends on whether NVD was reachable at that moment.

  --nvd-status          Report the database's age against the floor and exit.
                        Exit 0 fresh, 4 absent or stale — so it can gate a cron.
  --update-nvd          Refresh the NVD database into --data-dir and exit.
                        Requires NVD_API_KEY in the environment. This is the
                        only mode that talks to NVD.
  --data-dir <path>     Where the database lives (default:
                        $DEPENDENCY_CHECK_DATA_DIR, else
                        ~/.cache/dependency-check/data).
  --max-db-age-days <n> Refuse to report a scan as checked when the database is
                        older than n days (default: $DEPENDENCY_CHECK_MAX_DB_AGE_DAYS,
                        else 7). 0 disables the floor.
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

#: Where the OWASP image keeps its H2 database. Mounted, not baked in.
DC_CONTAINER_DATA_DIR="/usr/share/dependency-check/data"

_db_file() {
  # The H2 file is `odc.mv.db` today, but the name has moved between major
  # versions. Take the newest regular file in the data dir instead of pinning a
  # name, so a version bump degrades to "looks seeded" rather than "looks empty".
  [[ -d "$data_dir" ]] || return 1
  find "$data_dir" -maxdepth 1 -type f -name '*.db' -print 2>/dev/null \
    | head -1
}

_db_age_days() {
  local f
  f="$(_db_file)" || return 1
  [[ -n "$f" ]] || return 1
  local mtime now
  mtime="$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null)" || return 1
  now="$(date +%s)"
  echo $(( (now - mtime) / 86400 ))
}

_db_state() {
  # Three outcomes, deliberately distinguished. "absent" and "stale" both mean
  # the scan cannot be trusted, but they have different remedies and conflating
  # them is how "NOT CHECKED" stopped being informative in the first place.
  local age
  if ! age="$(_db_age_days)"; then
    echo "absent"
    return
  fi
  if [[ "$max_db_age_days" != "0" ]] && (( age > max_db_age_days )); then
    echo "stale:$age"
    return
  fi
  echo "fresh:$age"
}

#: Paths that are not this repository's dependencies.
#
# `.git-worktrees/` holds transient branch checkouts — duplicate copies of
# manifests that already exist at their real path. On the first real scan all 5
# worktree paths were scanned and BOTH findings were attributed to a worktree
# copy rather than to apps/kanban-viz/package-lock.json, where the vulnerable
# dependency actually lives. The duplicates also multiplied npm audit calls until
# registry.npmjs.org returned 429, which is what produced the non-zero exit.
_SCAN_EXCLUDES=(
  --exclude "**/.git-worktrees/**"
  --exclude "**/node_modules/**"
  --exclude "**/.venv/**"
  --exclude "**/.uv-cache/**"
  --exclude "**/site-packages/**"
)

_report_has_results() {
  # Did the scan actually produce a report? That is the observable fact, and a
  # better rule than an exit-code table: dependency-check's codes are
  # version-specific, but "there is a parseable report with a dependencies
  # array" is unambiguous.
  python3 -c 'import json,sys
try:
    doc = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if isinstance(doc.get("dependencies"), list) else 1)' "$report_path" 2>/dev/null
}

_classify_scan_rc() {
  # $1: the scanner exit code. Echoes "ok" or "error".
  #
  # A non-zero exit with a written report means the scan RAN and some analyzer
  # failed — not that nothing was checked. Observed 2026-09-10 on this repo's
  # first real scan: NodeAuditAnalyzer took a 429 from registry.npmjs.org,
  # dependency-check exited 14, and a complete 1.9 MB report naming 556
  # dependencies and a real moderate CVE (GHSA-82fw-gwwq-j7x9) was discarded as
  # NOT CHECKED — which `--allow-degraded-pass` then turned into a clean PASS.
  #
  # Same conflation fixed for ZAP in e9aec674 and not carried here. The findings
  # are real whatever the exit code says, so they flow; the non-zero exit is
  # recorded in the message rather than erasing them.
  if [[ "$1" -eq 0 ]]; then
    echo "ok"
  elif _report_has_results; then
    echo "ok"
  else
    echo "error"
  fi
}

_degraded_note() {
  # Names the partial coverage rather than implying completeness.
  [[ "$1" -eq 0 ]] && return
  printf '%s' " (exit $1 — the scan completed but at least one analyzer failed, so coverage is partial; see /tmp/security-review-depcheck.log)"
}

_nvd_hint() {
  # dependency-check is invoked with --noupdate, so it needs a pre-populated NVD
  # database mounted at its data directory. With none, it exits 13 having logged
  # "Autoupdate is disabled and the database does not exist" — a fully
  # deterministic cause with a specific remedy, which is worth naming here so the
  # aggregate gate's "NOT CHECKED" says *why* it was not checked.
  if grep -q "database does not exist" /tmp/security-review-depcheck.log 2>/dev/null; then
    printf '%s' " — no NVD database: dependency-check runs with --noupdate and none is mounted. Seed one (an NVD API key is required for a first download; see docs/dependencies.md) or the scanner cannot run."
  fi
}

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

_runtime_isolation_args() {
  # Rootless podman maps the image's user to a subuid that cannot write a
  # host-owned bind mount; without this the update writes nothing and the scan
  # then reports an absent database. Same defect the ZAP runner hit.
  if [[ "$container_runtime" == "podman" ]]; then
    printf '%s\n' "--userns=keep-id"
  fi
}

if [[ $nvd_status -eq 1 ]]; then
  db_state="$(_db_state)"
  case "$db_state" in
    absent)
      printf '{"scanner":"dependency-check","status":"error","mode":"status","data_dir":"%s","message":"no NVD database at %s — run: make security-seed-nvd"}\n' "$data_dir" "$data_dir"
      exit 4
      ;;
    stale:*)
      printf '{"scanner":"dependency-check","status":"error","mode":"status","data_dir":"%s","age_days":%s,"max_age_days":%s,"message":"NVD database is %s day(s) old, past the %s-day floor — run: make security-seed-nvd"}\n' \
        "$data_dir" "${db_state#stale:}" "$max_db_age_days" "${db_state#stale:}" "$max_db_age_days"
      exit 4
      ;;
    *)
      printf '{"scanner":"dependency-check","status":"ok","mode":"status","data_dir":"%s","age_days":%s,"max_age_days":%s,"message":"NVD database is %s day(s) old, within the %s-day floor"}\n' \
        "$data_dir" "${db_state#fresh:}" "$max_db_age_days" "${db_state#fresh:}" "$max_db_age_days"
      exit 0
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# --update-nvd: the ONLY mode that talks to NVD.
#
# Split out from scanning on purpose. Updating inline would make every scan
# depend on NVD being reachable and on the rate limit at that moment, so a
# transient network fault would read as a security finding. It would also turn a
# one-minute scan into a multi-GB download. Seeding separately keeps a scan's
# verdict a function of the tree and the database, both of which are stable.
# ---------------------------------------------------------------------------
if [[ $update_nvd -eq 1 ]]; then
  mkdir -p "$data_dir"
  if [[ -z "$nvd_api_key" ]]; then
    printf '{"scanner":"dependency-check","status":"error","mode":"update","runtime":"%s","report_path":"","message":"%s"}\n' \
      "${container_runtime:-none}" \
      "NVD_API_KEY is not set. Add it to agent-coordinator/.secrets.yaml (gitignored), then export it — see skills/security-review/docs/dependencies.md. NVD throttles unauthenticated downloads so hard that a first seed is not practical without one."
    exit 4
  fi
  if [[ $dry_run -eq 1 ]]; then
    printf '{"scanner":"dependency-check","status":"ok","mode":"update","runtime":"%s","report_path":"","message":"dry-run: would refresh the NVD database into %s"}\n' \
      "${container_runtime:-none}" "$data_dir"
    exit 0
  fi
  if [[ -z "$container_runtime" ]]; then
    printf '{"scanner":"dependency-check","status":"error","mode":"update","runtime":"none","report_path":"","message":"no container runtime available to refresh the NVD database"}\n'
    exit 4
  fi

  set +e
  # --nvdApiKey is passed as an argument because that is the only interface the
  # tool exposes; the value comes from the environment, so it is never typed on
  # a command line or stored in shell history.
  "$container_runtime" run --rm $(_runtime_isolation_args) \
    -v "$data_dir":"$DC_CONTAINER_DATA_DIR" \
    "$(scanner_image DEPENDENCY_CHECK)" \
    --updateonly \
    --nvdApiKey "$nvd_api_key" \
    --data "$DC_CONTAINER_DATA_DIR" >/tmp/security-review-depcheck-update.log 2>&1
  update_rc=$?
  set -e

  db_state="$(_db_state)"
  if [[ $update_rc -eq 0 && "$db_state" == fresh:* ]]; then
    printf '{"scanner":"dependency-check","status":"ok","mode":"update","runtime":"%s","report_path":"","message":"NVD database refreshed into %s (age %s day(s))"}\n' \
      "$container_runtime" "$data_dir" "${db_state#fresh:}"
    exit 0
  fi
  printf '{"scanner":"dependency-check","status":"error","mode":"update","runtime":"%s","report_path":"","message":"NVD refresh failed (exit %s, database %s); see /tmp/security-review-depcheck-update.log"}\n' \
    "$container_runtime" "$update_rc" "$db_state"
  exit 4
fi

mkdir -p "$data_dir"

# The freshness floor, evaluated before anything runs. A scan against an absent
# or stale CVE database produces a clean-looking report with no findings, which
# is indistinguishable from a genuinely clean scan — the exact failure this
# repo's gates keep hitting. Refuse to call it a check, and say which of the two
# it is so the remedy is obvious.
db_state="$(_db_state)"
if [[ $dry_run -eq 0 ]]; then
  case "$db_state" in
    absent)
      printf '{"scanner":"dependency-check","status":"error","mode":"%s","runtime":"%s","report_path":"%s","message":"%s"}\n' \
        "${container_runtime:-native}" "${container_runtime:-none}" "$report_path" \
        "no NVD database at $data_dir — dependency-check scans with --noupdate and has nothing to match against. Seed it with: make security-seed-nvd (needs NVD_API_KEY; see skills/security-review/docs/dependencies.md)"
      exit 4
      ;;
    stale:*)
      printf '{"scanner":"dependency-check","status":"error","mode":"%s","runtime":"%s","report_path":"%s","message":"%s"}\n' \
        "${container_runtime:-native}" "${container_runtime:-none}" "$report_path" \
        "NVD database at $data_dir is ${db_state#stale:} day(s) old, past the ${max_db_age_days}-day floor. A scan against stale CVE data reports no findings whether or not any exist, so this is NOT CHECKED rather than a pass. Refresh with: make security-seed-nvd"
      exit 4
      ;;
  esac
fi

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
    if [[ "$(_classify_scan_rc "$native_rc")" == "ok" ]]; then
      status="ok"
      message="native dependency-check completed$(_degraded_note "$native_rc")"
    elif [[ -n "$container_runtime" ]]; then
      mode="${container_runtime}-fallback"
      set +e
      "$container_runtime" run --rm $(_runtime_isolation_args) \
        -v "$repo":/src \
        -v "$out_dir":/report \
        -v "$data_dir":"$DC_CONTAINER_DATA_DIR" \
        "$(scanner_image DEPENDENCY_CHECK)" \
        --scan /src \
        --project "$project" \
        --format JSON \
        --out /report \
        "${_SCAN_EXCLUDES[@]}" \
        --noupdate >/tmp/security-review-depcheck.log 2>&1
      runtime_rc=$?
      set -e
      if [[ "$(_classify_scan_rc "$runtime_rc")" == "ok" ]]; then
        status="ok"
        message="native dependency-check failed (exit $native_rc); $container_runtime fallback completed$(_degraded_note "$runtime_rc")"
      else
        status="error"
        message="native dependency-check failed (exit $native_rc); $container_runtime fallback failed (exit $runtime_rc)$(_nvd_hint)"
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
    "$container_runtime" run --rm $(_runtime_isolation_args) \
      -v "$repo":/src \
      -v "$out_dir":/report \
      -v "$data_dir":"$DC_CONTAINER_DATA_DIR" \
      "$(scanner_image DEPENDENCY_CHECK)" \
      --scan /src \
      --project "$project" \
      --format JSON \
      --out /report \
      "${_SCAN_EXCLUDES[@]}" \
      --noupdate >/tmp/security-review-depcheck.log 2>&1
    rc=$?
    set -e
    if [[ "$(_classify_scan_rc "$rc")" == "ok" ]]; then
      status="ok"
      message="$container_runtime dependency-check completed$(_degraded_note "$rc")"
    else
      status="error"
      message="$container_runtime dependency-check failed to run (exit $rc)$(_nvd_hint)"
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
