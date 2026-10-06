#!/usr/bin/env bash
# Refuse to run when the installed unit differs from the reviewed one.
#
# Three rounds of analyzer fixes had no effect because /etc/systemd/system held
# an older copy than the repo. The repo was right the whole time. This turns
# that silent divergence into a loud refusal.
set -euo pipefail

unit="${1:?unit name required}"
repo_unit="${COORD_UNIT_SOURCE:-/opt/agentic-coding-tools/deploy/gx10/systemd/$unit}"
installed="${COORD_UNIT_INSTALLED:-/etc/systemd/system/$unit}"

[[ -f "$repo_unit" ]] || { echo "no reviewed unit at $repo_unit" >&2; exit 1; }
[[ -f "$installed" ]] || { echo "no installed unit at $installed" >&2; exit 1; }

if ! cmp -s "$repo_unit" "$installed"; then
  cat >&2 <<MSG
$unit in /etc/systemd/system differs from the reviewed copy in the repo.
systemd is running the installed file, not the one you edited. Run:

  sudo make -C /opt/agentic-coding-tools/deploy/gx10 install

then retry.
MSG
  exit 1
fi
