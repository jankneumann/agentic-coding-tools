#!/usr/bin/env bash
# Install git pre-commit hooks via the pre-commit framework.
#
# Idempotent: safe to re-run. First run creates skills/.venv and installs
# pre-commit (pinned in skills/pyproject.toml dev extra). Subsequent runs
# are no-ops if already in-sync.
#
# Usage:
#   ./install-hooks.sh
#
# Exit codes:
#   0  install succeeded (or was already installed)
#   1  `uv` not on PATH — install uv per CLAUDE.md Python Environment section

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="${SCRIPT_DIR}/skills"
VENV_BIN="${SKILLS_DIR}/.venv/bin"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: 'uv' not found on PATH." >&2
  echo "Install uv first — see CLAUDE.md § Python Environment." >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "[install-hooks] Syncing skills venv (includes pre-commit dev extra)..."
(cd "${SKILLS_DIR}" && uv sync --all-extras)

echo "[install-hooks] Wiring .git/hooks/pre-commit via pre-commit framework..."
"${VENV_BIN}/pre-commit" install

echo "[install-hooks] Done. The AGENTS.md ≡ CLAUDE.md invariant is now enforced on commit."
