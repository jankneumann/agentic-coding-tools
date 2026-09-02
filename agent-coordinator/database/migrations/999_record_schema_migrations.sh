#!/usr/bin/env bash
# Record a successful raw-SQL bootstrap for the runtime migration runner.
# Docker initdb executes this file only after every lexically earlier SQL file.

set -Eeuo pipefail

export LC_ALL=C

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
migrations_dir="${COORDINATOR_MIGRATIONS_DIR:-$script_dir}"
psql_bin="${PSQL_BIN:-psql}"
database_user="${POSTGRES_USER:-postgres}"
database_name="${POSTGRES_DB:-$database_user}"

shopt -s nullglob
migration_paths=("$migrations_dir"/*.sql)
if ((${#migration_paths[@]} == 0)); then
  echo "No SQL migrations found in $migrations_dir" >&2
  exit 1
fi

{
  printf '%s\n' 'BEGIN;'
  printf '%s\n' 'CREATE TABLE IF NOT EXISTS schema_migrations ('
  printf '%s\n' '  filename TEXT PRIMARY KEY,'
  printf '%s\n' '  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),'
  printf '%s\n' '  checksum TEXT NOT NULL'
  printf '%s\n' ');'

  for migration_path in "${migration_paths[@]}"; do
    filename="${migration_path##*/}"
    if [[ ! "$filename" =~ ^[0-9]+_[A-Za-z0-9._-]+\.sql$ ]]; then
      echo "Unsafe SQL migration filename: $filename" >&2
      exit 1
    fi
    checksum="$(sha256sum "$migration_path")"
    checksum="${checksum%% *}"
    if [[ ! "$checksum" =~ ^[0-9a-f]{64}$ ]]; then
      echo "Could not compute SHA-256 for $filename" >&2
      exit 1
    fi
    printf '%s\n' \
      "INSERT INTO schema_migrations (filename, checksum)" \
      "VALUES ('$filename', '$checksum')" \
      "ON CONFLICT (filename) DO UPDATE SET checksum = EXCLUDED.checksum;"
  done

  printf '%s\n' 'COMMIT;'
} | "$psql_bin" -X -v ON_ERROR_STOP=1 --username "$database_user" --dbname "$database_name"
