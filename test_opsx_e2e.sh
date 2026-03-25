#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/test_opsx_e2e.sh [options]

Creates a disposable OpenSpec canary change in a temporary repository copy,
generates minimal valid artifacts, validates strictly, and optionally archives.

Options:
  --change-id <id>     Use an explicit change id
  --no-archive         Skip archive step
  --keep-workdir       Keep temporary copy for inspection
  -h, --help           Show this help
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

CHANGE_ID=""
DO_ARCHIVE=1
KEEP_WORKTREE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --change-id)
      CHANGE_ID="${2:-}"
      shift 2
      ;;
    --no-archive)
      DO_ARCHIVE=0
      shift
      ;;
    --keep-workdir)
      KEEP_WORKTREE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

require_cmd git
require_cmd openspec
require_cmd find
require_cmd rsync

ROOT_DIR="$(git rev-parse --show-toplevel)"
if [[ -z "$CHANGE_ID" ]]; then
  CHANGE_ID="e2e-opsx-smoke-$(date +%Y%m%d-%H%M%S)"
fi

WORKTREE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/opsx-e2e.XXXXXX")"
RUN_DIR="$WORKTREE_DIR/repo"
mkdir -p "$RUN_DIR"

echo "Creating temporary repository copy: $RUN_DIR"
rsync -a \
  --exclude '.venv' \
  --exclude 'node_modules' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  "$ROOT_DIR/" "$RUN_DIR/"

cleanup() {
  if [[ "$KEEP_WORKTREE" -eq 1 ]]; then
    echo "Keeping temporary copy for inspection: $WORKTREE_DIR"
    return
  fi
  rm -rf "$WORKTREE_DIR"
}
trap cleanup EXIT

cd "$RUN_DIR"

echo "Creating canary change: $CHANGE_ID"
openspec new change "$CHANGE_ID" --schema feature-workflow

CHANGE_DIR="openspec/changes/$CHANGE_ID"
mkdir -p "$CHANGE_DIR"

SPEC_FILE=""
if [[ -d "$CHANGE_DIR/specs" ]]; then
  SPEC_FILE="$(find "$CHANGE_DIR/specs" -type f -name spec.md | head -n 1 || true)"
fi
if [[ -z "$SPEC_FILE" ]]; then
  SPEC_FILE="$CHANGE_DIR/specs/opsx-e2e/spec.md"
  mkdir -p "$(dirname "$SPEC_FILE")"
fi

cat > "$CHANGE_DIR/proposal.md" <<EOF
# Change: OpenSpec E2E Canary $CHANGE_ID

## Why

Validate OpenSpec 1.0 workflow commands and artifact lifecycle without implementing a real feature.

## What Changes

Create a disposable docs-only canary change to exercise artifact generation, status checks, strict validation, and archive.

## Impact

- Affected specs: opsx-e2e
- Breaking changes: None
EOF

cat > "$SPEC_FILE" <<'EOF'
## ADDED Requirements

### Requirement: OpenSpec E2E Canary

The system SHALL support a docs-only disposable OpenSpec canary change for validating workflow mechanics.

#### Scenario: Validate canary lifecycle
- **WHEN** a canary change is created and minimal artifacts are populated
- **THEN** `openspec validate <change-id> --strict` succeeds
- **AND** the change can be archived cleanly
EOF

cat > "$CHANGE_DIR/tasks.md" <<'EOF'
## 1. Canary Scope

- [x] 1.1 Create proposal artifact
- [x] 1.2 Create spec delta artifact
- [x] 1.3 Create tasks artifact
- [x] 1.4 Generate plan and implementation findings artifacts
- [x] 1.5 Generate validation and architecture impact artifacts
EOF

cat > "$CHANGE_DIR/plan-findings.md" <<EOF
# Plan Findings: $CHANGE_ID

## Iteration 1 ($(date +%Y-%m-%d))
| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | completeness | low | Canary artifact set created for e2e validation | No action needed |
EOF

cat > "$CHANGE_DIR/impl-findings.md" <<EOF
# Implementation Findings: $CHANGE_ID

## Iteration 1 ($(date +%Y-%m-%d))
| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | workflow | low | Disposable change does not modify product code | Expected for canary |
EOF

cat > "$CHANGE_DIR/validation-report.md" <<'EOF'
# Validation Report

## Summary
- Result: pass
- Scope: OpenSpec canary lifecycle only

## Phases
- deploy: skip
- smoke: skip
- e2e: skip
- spec: pass
- logs: skip
- ci: skip
EOF

cat > "$CHANGE_DIR/architecture-impact.md" <<'EOF'
# Architecture Impact

No architecture changes expected. Canary validates workflow mechanics only.
EOF

echo "Status check"
openspec status --change "$CHANGE_ID"

echo "Strict validation"
openspec validate "$CHANGE_ID" --strict

if [[ "$DO_ARCHIVE" -eq 1 ]]; then
  echo "Archiving canary change"
  openspec archive "$CHANGE_ID" --yes
else
  echo "Skipping archive (--no-archive)"
fi

echo "OpenSpec E2E canary completed successfully: $CHANGE_ID"
echo "Execution directory: $RUN_DIR"
