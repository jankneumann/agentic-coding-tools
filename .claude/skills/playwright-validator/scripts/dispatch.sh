#!/usr/bin/env bash
# dispatch.sh — invocation shim used by validate-feature --phase gen-eval
# when a frontend-descriptor is detected.
#
# Usage:
#   bash skills/playwright-validator/scripts/dispatch.sh <change-id> [extra args...]
#
# Behavior:
#   - Resolves repo root (walks up from this file looking for .git or openspec/).
#   - Activates skills/.venv if present so the CLI's deps (jsonschema, pyyaml)
#     are guaranteed.
#   - Invokes scripts/cli.py with the change-id + any forwarded args.
#
# Exit codes propagate the CLI's:
#   0   — all scenarios passed
#   1   — Playwright tests failed (findings emitted)
#   2   — pipeline error
#   64  — invalid change-id
#   127 — Playwright CLI missing (no findings emitted)

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: dispatch.sh <change-id> [args...]" >&2
    exit 64
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Walk up looking for openspec/ as the repo-root marker.
REPO_ROOT="$SCRIPT_DIR"
while [[ "$REPO_ROOT" != "/" && ! -d "$REPO_ROOT/openspec" ]]; do
    REPO_ROOT="$(dirname "$REPO_ROOT")"
done

if [[ "$REPO_ROOT" == "/" ]]; then
    echo "dispatch.sh: cannot find repo root (no openspec/ directory)" >&2
    exit 2
fi

PYTHON="${PYTHON:-python3}"
if [[ -x "$REPO_ROOT/skills/.venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/skills/.venv/bin/python"
fi

exec "$PYTHON" "$SCRIPT_DIR/cli.py" "$@"
