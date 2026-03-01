#!/usr/bin/env bash
# start-worktree-api.sh — Start API from a worktree branch for validation
#
# Usage: ./start-worktree-api.sh <worktree-path> [--admin-key KEY] [--port PORT]
#
# Environment variables:
#   MAIN_REPO_PATH  - Main repository root (default: derived from worktree git config)
#   VENV_PATH       - Python venv activate script (default: $MAIN_REPO/.venv/bin/activate)
#   ADMIN_API_KEY   - Admin key for the API (default: test-validate-key)
#   API_PORT        - Port to start API on (default: 8000)
#
# Handles:
# 1. Stopping any existing API on the target port
# 2. Verifying .env symlink exists in the worktree
# 3. Starting uvicorn from the worktree with ADMIN_API_KEY set
# 4. Waiting for health check
#
# Returns the PID of the started process

set -euo pipefail

WORKTREE_PATH="${1:?Usage: start-worktree-api.sh <worktree-path>}"
ADMIN_KEY="${ADMIN_API_KEY:-test-validate-key}"
PORT="${API_PORT:-8000}"

# Resolve main repo: use env var, or derive from worktree's git common dir
if [[ -n "${MAIN_REPO_PATH:-}" ]]; then
  MAIN_REPO="$MAIN_REPO_PATH"
else
  GIT_COMMON=$(git -C "$WORKTREE_PATH" rev-parse --git-common-dir 2>/dev/null || true)
  if [[ -n "$GIT_COMMON" && "$GIT_COMMON" != ".git" ]]; then
    MAIN_REPO="${GIT_COMMON%%/.git*}"
  else
    MAIN_REPO=$(git -C "$WORKTREE_PATH" rev-parse --show-toplevel 2>/dev/null || echo "$WORKTREE_PATH")
  fi
fi

VENV_ACTIVATE="${VENV_PATH:-${MAIN_REPO}/.venv/bin/activate}"
LOG_FILE="/tmp/validate-feature-api-$(date +%s).log"

# Parse extra args
shift
while [[ $# -gt 0 ]]; do
  case $1 in
    --admin-key) ADMIN_KEY="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# 1. Check worktree exists
if [[ ! -d "$WORKTREE_PATH" ]]; then
  echo "ERROR: Worktree not found: $WORKTREE_PATH"
  exit 1
fi

# 2. Check .env
if [[ ! -f "$WORKTREE_PATH/.env" ]]; then
  echo "WARNING: No .env in worktree. Creating symlink..."
  if [[ -f "$MAIN_REPO/.env" ]]; then
    ln -s "$MAIN_REPO/.env" "$WORKTREE_PATH/.env"
  else
    echo "ERROR: No .env found at $MAIN_REPO/.env — set MAIN_REPO_PATH to the repo containing .env"
    exit 1
  fi
fi

# 3. Stop existing API on port
EXISTING_PID=$(lsof -ti ":$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)
if [[ -n "$EXISTING_PID" ]]; then
  EXISTING_CWD=$(lsof -p "$EXISTING_PID" -Fn 2>/dev/null | grep "^n/" | head -1 | cut -c2-)
  echo "Stopping existing API (PID $EXISTING_PID, cwd: $EXISTING_CWD)"
  kill "$EXISTING_PID" 2>/dev/null || true
  sleep 2
fi

# 4. Start from worktree
echo "Starting API from: $WORKTREE_PATH"
echo "  Port: $PORT"
echo "  Log: $LOG_FILE"
echo "  Admin key: ${ADMIN_KEY:0:8}..."

cd "$WORKTREE_PATH"
source "$VENV_ACTIVATE"
ADMIN_API_KEY="$ADMIN_KEY" LOG_LEVEL=DEBUG nohup uvicorn src.api.app:app --host 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &
API_PID=$!
echo "  PID: $API_PID"

# 5. Wait for health
echo "Waiting for health check..."
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/health" 2>/dev/null || true)
  if [[ "$code" == "200" ]]; then
    echo "  API ready after ${i}s"
    echo ""
    echo "API_PID=$API_PID"
    echo "LOG_FILE=$LOG_FILE"
    exit 0
  fi
  sleep 1
done

echo "ERROR: API did not start within 20s"
echo "Check log: $LOG_FILE"
exit 1
