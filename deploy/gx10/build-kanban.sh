#!/usr/bin/env bash
# Build the kanban board for the analyzer's Caddy to serve under /kanban/.
#
#   build-kanban.sh            build HEAD into releases/<sha>, switch `current`
#
# The board is static: no container runs it. Caddy mounts $KANBAN_DIR
# read-only and serves $KANBAN_DIR/current, a RELATIVE symlink resolved inside
# the container at request time -- so a rebuild switches atomically with no
# Caddy restart. (Bind-mounting a release directory directly would pin its
# inode: a swapped directory stays invisible until the container is recreated.)
#
# The bundle carries NO coordinator key. Caddy injects it server-side; the
# build sets VITE_COORDINATOR_AUTH=proxy so the board sends no Authorization
# header, which would otherwise replace the browser's basic_auth credentials.
set -euo pipefail

ROOT_DIR="${COORD_ROOT_DIR:-/opt/agentic-coding-tools}"
IMAGES_ENV="${GX10_IMAGES_ENV:-/etc/aca/gx10-images.env}"
KANBAN_DIR="${GX10_KANBAN_DIR:-/srv/aca/kanban}"
PODMAN="${COORD_PODMAN_BIN:-/usr/bin/podman}"
KEEP="${GX10_KANBAN_KEEP:-3}"
BASE=/kanban/

# shellcheck disable=SC1090
[[ -r "$IMAGES_ENV" ]] && source "$IMAGES_ENV"
: "${GX10_NODE_IMAGE:?set a reviewed node tag@sha256 digest in $IMAGES_ENV}"
[[ "$GX10_NODE_IMAGE" == *@sha256:* ]] || { echo "GX10_NODE_IMAGE is not digest-pinned" >&2; exit 1; }

sha="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
release="$KANBAN_DIR/releases/$sha"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# `git archive`, not the checkout: exactly the committed tree, so an untracked
# .env.local holding a developer's key can never reach the bundle.
git -C "$ROOT_DIR" archive HEAD apps/kanban-viz | tar -x -C "$work"

"$PODMAN" run --rm \
  -v "$work/apps/kanban-viz:/src:rw" -w /src \
  -e VITE_COORDINATOR_URL=/kanban/api \
  -e VITE_COORDINATOR_AUTH=proxy \
  -e VITE_COORDINATOR_API_KEY= \
  "$GX10_NODE_IMAGE" \
  sh -c "npm ci --no-audit --no-fund && npm run build -- --base $BASE"

dist="$work/apps/kanban-viz/dist"
# Without the base, index.html requests /assets/... and Caddy hands that path
# to the analyzer API: a blank page with no error anywhere obvious.
grep -q "src=\"${BASE}assets/" "$dist/index.html" \
  || { echo "built index.html does not load assets from $BASE" >&2; exit 1; }
if grep -rqE 'Bearer [A-Za-z0-9_-]{16,}' "$dist"; then
  echo "bundle contains what looks like a baked bearer key; refusing" >&2; exit 1
fi

install -d -m 0755 "$KANBAN_DIR/releases"
rm -rf "$release.new" && cp -r "$dist" "$release.new"
find "$release.new" -type d -exec chmod 0755 {} + && find "$release.new" -type f -exec chmod 0644 {} +
rm -rf "$release" && mv "$release.new" "$release"

ln -sfn "releases/$sha" "$KANBAN_DIR/current.new"
mv -T "$KANBAN_DIR/current.new" "$KANBAN_DIR/current"
echo "kanban: $KANBAN_DIR/current -> releases/$sha"

# Keep the newest $KEEP releases, never the live one.
ls -1t "$KANBAN_DIR/releases" | tail -n +"$((KEEP + 1))" | while read -r old; do
  [[ "$old" == "$sha" ]] || rm -rf "${KANBAN_DIR:?}/releases/$old"
done
