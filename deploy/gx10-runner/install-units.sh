#!/usr/bin/env bash
# Copy the GX10 runner kit into a user's home and PRINT the commands that enable it (D7).
#
# Usage: install-units.sh [--prefix DIR]
#
# --prefix defaults to the `ghrunner` home directory. This script only copies files beneath
# the prefix. It never runs systemctl, loginctl or podman: those are operator steps (O1, O4)
# and are printed for the operator to run, as `ghrunner`.
set -euo pipefail

kit="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prefix=""
instances="${GX10_INSTANCES:-8}"

while (( $# )); do
  case "$1" in
    --prefix) prefix="${2:?--prefix needs a directory}"; shift 2 ;;
    --prefix=*) prefix="${1#--prefix=}"; shift ;;
    --instances) instances="${2:?--instances needs a number}"; shift 2 ;;
    -h|--help) sed -n '2,9p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "install-units.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$instances" =~ ^[0-9]+$ && "$instances" -ge 1 ]] || { echo "invalid --instances" >&2; exit 2; }

if [[ -z "$prefix" ]]; then
  prefix="$(getent passwd ghrunner | cut -d: -f6 || true)"
  [[ -n "$prefix" ]] || { echo "install-units.sh: no ghrunner user; pass --prefix DIR" >&2; exit 2; }
fi

unit_dir="$prefix/.config/systemd/user"
lib_dir="$prefix/.local/lib/gx10-runner"
conf_dir="$prefix/.config/gx10-runner"
mkdir -p "$unit_dir" "$lib_dir" "$conf_dir"
chmod 700 "$conf_dir"

install -m 0644 "$kit/systemd/gx10-runner@.service" "$unit_dir/gx10-runner@.service"
install -m 0755 "$kit/mint-jitconfig.sh" "$lib_dir/mint-jitconfig.sh"
install -m 0755 "$kit/cleanup-runner.sh" "$lib_dir/cleanup-runner.sh"
if [[ ! -e "$conf_dir/env" ]]; then
  install -m 0600 "$kit/gx10-runner.env.example" "$conf_dir/env"
  echo "Wrote $conf_dir/env from the example: edit GX10_RUNNER_REPO and GX10_RUNNER_IMAGE."
fi

cat <<MSG

Files installed under: $prefix
Nothing was enabled or started. As the operator, run (the unit commands target ghrunner's
user manager, not yours):

  sudo loginctl enable-linger ghrunner
  sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/\$(id -u ghrunner) systemctl --user daemon-reload
  sudo -u ghrunner XDG_RUNTIME_DIR=/run/user/\$(id -u ghrunner) systemctl --user enable --now gx10-runner@{1..$instances}

Token (mode 0600, read through LoadCredential=):  $conf_dir/token
MSG
