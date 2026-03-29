#!/usr/bin/env bash
# gemini_wrapper.sh — Run Gemini CLI with coordinator status reporting.
#
# Gemini CLI has no lifecycle hooks, so this wrapper:
#   1. Registers the agent with the coordinator on startup
#   2. Runs the Gemini CLI command
#   3. Reports status after each invocation
#   4. Deregisters on exit
#
# Usage:
#   ./gemini_wrapper.sh "Implement the auth module"
#   ./gemini_wrapper.sh -p "Fix the failing test"
#   echo "prompt" | ./gemini_wrapper.sh
#
# Environment:
#   COORDINATOR_URL  — Coordinator HTTP API (default: http://localhost:8081)
#   AGENT_ID         — Agent identifier (default: gemini-1)
#   AGENT_TYPE       — Agent type (default: gemini)
#   CHANGE_ID        — OpenSpec change-id (optional, for status context)
#
# The wrapper passes all arguments through to `gemini`. Use `-y` for
# auto-approve mode in CI/automation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_URL="${COORDINATOR_URL:-http://localhost:8081}"
AGENT_ID="${AGENT_ID:-gemini-1}"
AGENT_TYPE="${AGENT_TYPE:-gemini}"

# --- Registration ---
_register() {
    python3 "${SCRIPT_DIR}/register_agent.py" 2>/dev/null || true
}

_deregister() {
    python3 "${SCRIPT_DIR}/deregister_agent.py" 2>/dev/null || true
}

_report_status() {
    local phase="${1:-UNKNOWN}"
    local message="${2:-}"
    local needs_human="${3:-false}"

    # Use report_status.py if available (reads loop-state.json etc.)
    if [ -f "${SCRIPT_DIR}/report_status.py" ]; then
        python3 "${SCRIPT_DIR}/report_status.py" 2>/dev/null || true
        return
    fi

    # Fallback: direct HTTP POST
    curl -sf -X POST "${COORDINATOR_URL}/status/report" \
        -H "Content-Type: application/json" \
        -d "{
            \"agent_id\": \"${AGENT_ID}\",
            \"change_id\": \"${CHANGE_ID:-}\",
            \"phase\": \"${phase}\",
            \"message\": \"${message}\",
            \"needs_human\": ${needs_human},
            \"event_type\": \"phase_transition\"
        }" --max-time 5 >/dev/null 2>&1 || true
}

# --- Cleanup on exit ---
trap '_report_status "SESSION_END" "Gemini session ended"; _deregister' EXIT

# --- Main ---
export AGENT_ID AGENT_TYPE

_register
_report_status "SESSION_START" "Gemini session started"

# Run gemini with all passed arguments
# Exit code is preserved so the caller knows if gemini succeeded
gemini_exit=0
gemini "$@" || gemini_exit=$?

if [ $gemini_exit -eq 0 ]; then
    _report_status "COMPLETED" "Gemini task completed successfully"
else
    _report_status "FAILED" "Gemini task failed with exit code ${gemini_exit}" "true"
fi

exit $gemini_exit
