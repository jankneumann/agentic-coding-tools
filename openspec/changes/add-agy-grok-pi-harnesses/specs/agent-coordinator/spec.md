# agent-coordinator — delta for add-agy-grok-pi-harnesses

Updates runtime/transport documentation and the status-reporting code-path description to name
the current harness roster instead of the retired Gemini CLI.

## MODIFIED Requirements

### Requirement: Skill Integration Usage Patterns

The agent-coordinator documentation SHALL include usage patterns showing how workflow skills integrate with coordinator capabilities across both local CLI and Web/Cloud execution contexts.

#### Scenario: Documentation covers runtime and transport matrix
- **WHEN** a user reads agent-coordinator documentation
- **THEN** there SHALL be a matrix describing:
  - Claude Code, Codex, antigravity, grok, and pi CLI runtimes using MCP transport
  - Web/Cloud runtimes using HTTP API transport
  - standalone fallback behavior when coordinator is unavailable
- **AND** the matrix SHALL NOT list the retired Gemini CLI runtime

#### Scenario: Documentation maps skills to capabilities
- **WHEN** a user reviews skill integration documentation
- **THEN** it SHALL identify which skills consume lock, work queue, handoff, memory, and guardrail capabilities
- **AND** explain capability-gated behavior when only a subset is available

#### Scenario: Documentation covers setup for CLI and Web/Cloud
- **WHEN** a user wants to enable coordination
- **THEN** documentation SHALL reference `/setup-coordinator`
- **AND** include manual configuration guidance for MCP (CLI) and HTTP API (Web/Cloud) paths

### Requirement: Status Reporting

The coordinator SHALL accept status reports from agents via both Claude Code hooks and HTTP API.

- A new `POST /status/report` endpoint SHALL accept: `agent_id`, `change_id`, `phase`, `message`, `needs_human` (boolean), `event_type` (optional, default: `"phase_transition"`), `metadata` (optional JSON).
- The endpoint SHALL update the agent's heartbeat timestamp as a side effect.
- If `needs_human` is true, the event SHALL be classified as `high` urgency.
- The endpoint SHALL emit a `coordinator_status` NOTIFY event for all status reports.
- Special `event_type` values have semantic meaning for the autopilot:
  - `gate_check` — signals that a human has confirmed an escalation is resolved. The autopilot's `gate_check_fn` SHALL query for recent `gate_check` events for its `change_id` and re-evaluate the escalation condition if found.
  - `phase_skip` — signals that a human wants to bypass the current phase. The autopilot's `gate_check_fn` SHALL query for recent `phase_skip` events and return `True` (resolved) if found, causing the loop to exit ESCALATE and proceed to the next phase.
- A `report_status.py` Claude Code hook script SHALL:
  - Fire on `Stop` and `SubagentStop` events.
  - Read `loop-state.json` if present to extract `current_phase` and `findings_trend`.
  - If `loop-state.json` is missing or contains invalid JSON, report `phase: "UNKNOWN"` and log a warning to stderr.
  - Compare `current_phase` against `.status-cache.json` — only report if phase has changed.
  - Call `POST /status/report` with extracted data.
  - Run the HTTP call with a hard 5-second timeout (`subprocess` or `httpx` with `timeout=5.0`). If the coordinator is unreachable or the call times out, log to stderr and exit 0 (do NOT block Claude Code).
  - Exit 0 in all cases (success, timeout, error) — the hook MUST NOT block the agent.
  - Update `.status-cache.json` with the reported phase on success.
- The autopilot's `run_loop()` SHALL accept an optional `status_fn` callback with signature `(state: LoopState, event_type: str, message: str, urgent: bool) -> None`.
- If `status_fn` raises an exception or exceeds 5 seconds, the exception SHALL be caught and logged. The loop SHALL NOT crash or change behavior due to `status_fn` failures. The error SHALL be included as `error_details` in the next heartbeat.
- **Two code paths** (both produce equivalent `coordinator_status` NOTIFY events):
  - **Path A (in-band callback)**: `run_loop()` calls `status_fn` at phase transitions. The callback delegates to `report_status` MCP tool (local) or `POST /status/report` (HTTP). Works for all agents in the roster (Claude Code, Codex, antigravity, grok, pi).
  - **Path B (out-of-band hook)**: Claude Code `Stop` hook fires `report_status.py`, which reads `loop-state.json` independently and POSTs to `/status/report`. Claude Code-specific; provides implicit heartbeat.

#### Scenario: Claude Code hook reports phase transition

WHEN a Claude Code `Stop` hook fires
AND `loop-state.json` exists with `current_phase` different from cached phase
THEN `report_status.py` SHALL call `POST /status/report` with the new phase
AND the coordinator emits a `coordinator_status` NOTIFY event.

#### Scenario: Codex agent reports status via HTTP

WHEN a Codex agent calls `POST /status/report` with `{"agent_id": "codex-1", "phase": "IMPL_REVIEW", "needs_human": false}`
THEN the coordinator stores the status and updates the heartbeat
AND emits a `coordinator_status` NOTIFY event with urgency `medium`.

#### Scenario: New-roster agent reports status via HTTP

WHEN a grok agent calls `POST /status/report` with `{"agent_id": "grok-1", "phase": "IMPL_REVIEW", "needs_human": false}`
THEN the coordinator stores the status and updates the heartbeat
AND emits a `coordinator_status` NOTIFY event with urgency `medium`.
