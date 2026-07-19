#!/usr/bin/env bash
# Migrate the coordinator database from Railway (or any source Postgres) into a
# local Postgres, then verify the copy by comparing per-table row counts.
#
# This performs a full logical copy (schema + data + the schema_migrations
# tracking table) with pg_dump -Fc | pg_restore --clean --if-exists, so the
# local database becomes an exact replica. Because it restores with --clean,
# it safely replaces any schema the local stack pre-created via its
# docker-entrypoint-initdb.d migrations or the app's startup migration runner.
#
# Usage:
#   scripts/migrate_railway_to_local.sh \
#     --source "postgresql://user:pass@host:port/railway" \
#     --target "postgresql://postgres:postgres@localhost:54322/postgres"
#
#   # or via env vars
#   SOURCE_DSN=... TARGET_DSN=... scripts/migrate_railway_to_local.sh
#
# Options:
#   --source DSN     Source (Railway) connection string. Env: SOURCE_DSN
#   --target DSN     Target (local) connection string.   Env: TARGET_DSN
#   --dump-file PATH Where to write the dump (default: a temp file, kept on failure)
#   --data-only      Copy data only; do NOT touch the target schema (advanced —
#                    requires the target schema to already match the source)
#   --force          Skip the "target must be local" safety guard
#   --dry-run        Preflight + show what would happen, make no changes
#   -h, --help       Show this help
#
# Exit codes: 0 success, 1 usage/preflight error, 2 verification mismatch.
set -euo pipefail

SOURCE_DSN="${SOURCE_DSN:-}"
TARGET_DSN="${TARGET_DSN:-}"
DUMP_FILE=""
DATA_ONLY=0
FORCE=0
DRY_RUN=0

log()  { printf '  %s\n' "$*"; }
section() { printf '\n=== %s ===\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit "${2:-1}"; }

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --source)    SOURCE_DSN="${2:?--source needs a value}"; shift 2 ;;
    --target)    TARGET_DSN="${2:?--target needs a value}"; shift 2 ;;
    --dump-file) DUMP_FILE="${2:?--dump-file needs a value}"; shift 2 ;;
    --data-only) DATA_ONLY=1; shift ;;
    --force)     FORCE=1; shift ;;
    --dry-run)   DRY_RUN=1; shift ;;
    -h|--help)   usage ;;
    *)           die "unknown argument: $1" ;;
  esac
done

# ── Preflight ────────────────────────────────────────────────────────────────
section "Preflight"
for tool in pg_dump pg_restore psql; do
  command -v "$tool" >/dev/null 2>&1 || die "'$tool' not found on PATH (install the postgresql client)"
done
[ -n "$SOURCE_DSN" ] || die "source DSN is required (--source or SOURCE_DSN)"
[ -n "$TARGET_DSN" ] || die "target DSN is required (--target or TARGET_DSN)"

# Direction-safety guard: refuse to write to a non-local target unless --force.
# This prevents accidentally restoring *onto* Railway (wrong direction).
target_host="$(printf '%s' "$TARGET_DSN" | sed -E 's#^[a-zA-Z]+://[^@]*@?([^:/?]+).*#\1#')"
case "$target_host" in
  localhost|127.0.0.1|::1|*.railway.internal|postgres) : ;;
  *)
    if [ "$FORCE" -ne 1 ]; then
      die "target host '$target_host' does not look local. Refusing to write to it.
     Pass --force if you really mean to restore into a remote database."
    fi
    log "WARNING: target host '$target_host' is non-local; proceeding due to --force"
    ;;
esac

log "Checking source reachability..."
psql "$SOURCE_DSN" -tAc 'SELECT 1' >/dev/null 2>&1 || die "cannot connect to source DSN"
log "Checking target reachability..."
psql "$TARGET_DSN" -tAc 'SELECT 1' >/dev/null 2>&1 || die "cannot connect to target DSN"
log "Source and target both reachable."

# Exact per-table row counts for the public schema, returned as
# "<table>\t<count>" lines. Uses query_to_xml so every table is counted in a
# single round-trip (n_live_tup would only be an estimate).
exact_counts() {
  psql "$1" -tAF $'\t' <<'SQL'
SELECT format('%s', c.relname), format('%s', (xpath('/row/c/text()',
  query_to_xml(format('SELECT count(*) AS c FROM public.%I', c.relname),
  false, true, '')))[1]::text)::bigint
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;
SQL
}

section "Source tables (exact row counts)"
SRC_COUNTS="$(exact_counts "$SOURCE_DSN")" || die "failed to read source row counts"
printf '%s\n' "$SRC_COUNTS" | awk -F'\t' '{printf "  %-28s %s\n", $1, $2}'
SRC_TOTAL="$(printf '%s\n' "$SRC_COUNTS" | awk -F'\t' '{s+=$2} END{print s+0}')"
log "source total rows: $SRC_TOTAL"

if [ "$DRY_RUN" -eq 1 ]; then
  section "Dry run"
  log "Would dump source and restore into target ($target_host)."
  log "Mode: $([ "$DATA_ONLY" -eq 1 ] && echo data-only || echo 'full (schema + data, --clean)')."
  log "No changes made."
  exit 0
fi

# ── Dump ─────────────────────────────────────────────────────────────────────
KEEP_DUMP=1
if [ -z "$DUMP_FILE" ]; then
  DUMP_FILE="$(mktemp -t coordinator-migrate-XXXXXX.dump)"
  KEEP_DUMP=0
fi
section "Dump"
log "Dumping source → $DUMP_FILE"
DUMP_FLAGS=(--format=custom --no-owner --no-privileges --verbose)
if [ "$DATA_ONLY" -eq 1 ]; then
  # Exclude the app's migration tracker so it isn't duplicated into a schema
  # the target already tracks.
  DUMP_FLAGS+=(--data-only --exclude-table-data=schema_migrations)
fi
pg_dump "${DUMP_FLAGS[@]}" --file="$DUMP_FILE" "$SOURCE_DSN" 2> >(sed 's/^/  pg_dump: /' >&2)
log "Dump complete ($(du -h "$DUMP_FILE" | cut -f1))."

# ── Restore ──────────────────────────────────────────────────────────────────
section "Restore"
log "Restoring into target ($target_host)"
RESTORE_FLAGS=(--no-owner --no-privileges --verbose)
if [ "$DATA_ONLY" -eq 1 ]; then
  RESTORE_FLAGS+=(--data-only --disable-triggers)
else
  # --clean --if-exists replaces any pre-existing objects the local stack
  # created (initdb / startup migrations) so the restore is an exact replica.
  RESTORE_FLAGS+=(--clean --if-exists)
fi
# pg_restore exits non-zero on ignorable warnings (e.g. DROP of a missing
# object). Capture status and let verification be the source of truth.
set +e
pg_restore "${RESTORE_FLAGS[@]}" --dbname="$TARGET_DSN" "$DUMP_FILE" 2> >(sed 's/^/  pg_restore: /' >&2)
restore_status=$?
set -e
[ "$restore_status" -eq 0 ] || log "pg_restore exited $restore_status (often ignorable warnings — verifying below)"

# ── Verify ───────────────────────────────────────────────────────────────────
section "Verify (target vs source row counts)"
psql "$TARGET_DSN" -c 'ANALYZE' >/dev/null 2>&1 || true
TGT_COUNTS="$(exact_counts "$TARGET_DSN")" || die "failed to read target row counts"
mismatch=0
while IFS=$'\t' read -r tbl src_n; do
  [ -n "$tbl" ] || continue
  tgt_n="$(printf '%s\n' "$TGT_COUNTS" | awk -F'\t' -v t="$tbl" '$1==t{print $2}')"
  tgt_n="${tgt_n:-<missing>}"
  if [ "$src_n" = "$tgt_n" ]; then
    printf '  [ok]   %-28s %s\n' "$tbl" "$src_n"
  else
    printf '  [DIFF] %-28s source=%s target=%s\n' "$tbl" "$src_n" "$tgt_n"
    mismatch=1
  fi
done <<< "$SRC_COUNTS"

if [ "$KEEP_DUMP" -eq 0 ] && [ "$mismatch" -eq 0 ]; then
  rm -f "$DUMP_FILE"
else
  log "dump retained at: $DUMP_FILE"
fi

section "Result"
if [ "$mismatch" -ne 0 ]; then
  die "row counts differ between source and target — review the pg_restore log above" 2
fi
log "All table row counts match. Migration verified."
log "Next: start the coordinator against the target DSN and hit /health, /ready."
