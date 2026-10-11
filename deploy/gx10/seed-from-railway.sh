#!/usr/bin/env bash
# Carry the Railway coordinator's database over to GX-10.
#
#   seed-from-railway.sh dump <out.dump>       anywhere with network access
#   seed-from-railway.sh check <out.dump>      compare migration checksums
#   seed-from-railway.sh restore <out.dump>    on GX-10, as root, BEFORE the
#                                              coordinator API's first start
#
# `dump` reads the source DSN from RAILWAY_COORD_DSN_FILE (a 0600 file holding
# the Postgres DATABASE_PUBLIC_URL), never from argv or the environment, so
# the password stays out of the process table and shell history. The dump is
# a full schema+data copy *including* schema_migrations: on first start the
# GX-10 API then applies only migrations newer than Railway's.
#
# The dump holds every agent's memory, audit trail and handoffs. It is written
# 0600 and should be deleted once the restore is verified.
set -euo pipefail

ROOT_DIR="${COORD_ROOT_DIR:-/opt/agentic-coding-tools}"
MIGRATIONS="${COORD_MIGRATIONS_DIR:-$ROOT_DIR/agent-coordinator/database/migrations}"
PODMAN="${COORD_PODMAN_BIN:-/usr/bin/podman}"
CONTAINER="${COORD_POSTGRES_CONTAINER:-aca-gx10-coord_coordinator-postgres_1}"
DB_USER="${COORD_DB_USER:-coordinator}"
DB_NAME="${COORD_DB_NAME:-coordinator}"

usage() { sed -n '2,8p' "$0" >&2; exit 2; }
[[ $# -eq 2 ]] || usage
cmd="$1" dump="$2"

case "$cmd" in
dump)
  dsn_file="${RAILWAY_COORD_DSN_FILE:?point RAILWAY_COORD_DSN_FILE at a 0600 file holding the DSN}"
  [[ "$(stat -c %a "$dsn_file")" == 600 ]] || { echo "$dsn_file must be mode 0600" >&2; exit 1; }
  umask 077
  # Custom format: compressed, and pg_restore can reorder and filter it.
  # --no-owner/--no-privileges: Railway's roles do not exist on GX-10.
  # Split the URL into libpq variables: a password in argv is world-readable
  # in /proc, one in this process's environment is not.
  eval "$(python3 -I - "$dsn_file" <<'PY'
import shlex, sys
from urllib.parse import unquote, urlsplit
u = urlsplit(open(sys.argv[1]).read().strip())
for k, v in (("PGHOST", u.hostname), ("PGPORT", u.port), ("PGUSER", u.username),
             ("PGPASSWORD", u.password), ("PGDATABASE", u.path.lstrip("/"))):
    print(f"export {k}={shlex.quote(unquote(str(v or '')))}")
PY
)"
  pg_dump --format=custom --no-owner --no-privileges --file="$dump.partial"
  mv "$dump.partial" "$dump"
  pg_restore --list "$dump" >/dev/null   # proves the archive is readable
  echo "dumped: $dump ($(du -h "$dump" | cut -f1))"
  ;;

check)
  # The runner SKIPS (with only a warning) a migration whose recorded checksum
  # differs from the file on disk -- a silently half-migrated database. Refuse
  # to proceed unless every migration Railway applied is byte-identical here.
  rows="$(pg_restore --data-only --table=schema_migrations --file=- "$dump" \
    | awk '/^COPY .*schema_migrations/{on=1;next} /^\\\.$/{on=0} on')"
  [[ -n "$rows" ]] || { echo "no schema_migrations rows in $dump" >&2; exit 1; }
  bad=0 applied=0
  while IFS=$'\t' read -r -a cols; do
    file="" sum=""
    for c in "${cols[@]}"; do
      [[ "$c" =~ ^[0-9]{3}_.+\.sql$ ]] && file="$c"
      [[ "$c" =~ ^[0-9a-f]{64}$ ]] && sum="$c"
    done
    [[ -n "$file" ]] || continue
    applied=$((applied + 1))
    if [[ ! -f "$MIGRATIONS/$file" ]]; then
      echo "MISSING here: $file (applied on Railway)"; bad=1
    elif [[ "$(sha256sum <"$MIGRATIONS/$file" | cut -d' ' -f1)" != "$sum" ]]; then
      echo "CHANGED since Railway applied it: $file"; bad=1
    fi
  done <<<"$rows"
  pending="$(comm -13 <(printf '%s\n' "$rows" | grep -oE '[0-9]{3}_[^[:space:]]+\.sql' | sort) \
    <(ls "$MIGRATIONS" | grep -E '^[0-9]{3}_.+\.sql$' | sort))"
  echo "applied on Railway: $applied"
  echo "will apply on first GX-10 start: ${pending:-none}" | tr '\n' ' '; echo
  exit "$bad"
  ;;

restore)
  [[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
  "$0" check "$dump"
  exec_psql() { "$PODMAN" exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" "$@"; }
  # An API that already started has migrated an empty schema; restoring on top
  # would collide object by object. Refuse rather than half-merge.
  if [[ "$(exec_psql -tAc "SELECT to_regclass('public.schema_migrations') IS NOT NULL")" == t ]]; then
    echo "$DB_NAME already has a schema; restore needs a fresh database" >&2; exit 1
  fi
  # Cluster-level roles are not in a pg_dump; the RLS policies name them.
  exec_psql -c "DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
  END \$\$;"
  "$PODMAN" exec -i "$CONTAINER" pg_restore --exit-on-error --single-transaction \
    --no-owner --no-privileges -U "$DB_USER" -d "$DB_NAME" <"$dump"
  exec_psql -tAc "SELECT count(*) || ' migrations recorded' FROM schema_migrations"
  ;;

*) usage ;;
esac
