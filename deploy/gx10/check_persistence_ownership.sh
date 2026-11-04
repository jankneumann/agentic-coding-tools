#!/usr/bin/env bash
# Fail closed unless every coordinator bind mount is owned by the uid that
# writes it. A read_only container whose one writable path is owned by the
# wrong user starts fine and fails on the first write, which surfaces as an
# unrelated 500 much later.
set -euo pipefail

status=0
check() {
  local path="$1" want_uid="$2" want_gid="$3"
  if [[ ! -d "$path" ]]; then
    echo "missing: $path (run: make ownership)" >&2
    status=1
    return
  fi
  local got
  got="$(stat -c '%u:%g' "$path")"
  if [[ "$got" != "$want_uid:$want_gid" ]]; then
    echo "wrong owner: $path is $got, expected $want_uid:$want_gid" >&2
    status=1
  fi
}

check /srv/aca/coordinator-postgres 999 999
check /srv/aca/coordinator-workdir 10001 10001
exit "$status"
