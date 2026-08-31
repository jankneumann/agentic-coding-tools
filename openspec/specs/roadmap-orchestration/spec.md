# roadmap-orchestration Specification

## Purpose
TBD - created by archiving change roadmap-openspec-orchestration. Update Purpose after archive.
## Requirements
### Requirement: Proposal Decomposition into Roadmap Changes

The system SHALL provide a `plan-roadmap` workflow that decomposes long markdown proposals into prioritized OpenSpec change candidates with explicit dependencies and acceptance outcomes. The workflow SHALL additionally provide a replan mode, `/plan-roadmap --replan <roadmap-id>`, driven by `<workspace>/replan-request.json`. In replan mode the deterministic helper `decomposer.py replan-scope <workspace>` SHALL emit the affected subgraph: every `replan_required` item plus its transitive dependents, excluding any item in a preserved status (`completed`, `superseded`, `in_progress`), and nothing else. A preserved item SHALL also act as a traversal barrier, so dependents reachable only through one are outside the scope. The host SHALL re-decompose only that subgraph against the source proposal and the failed item's learning entry; items in a preserved status, and all existing `learnings/` entries, SHALL be preserved verbatim. On success the workflow SHALL set the re-decomposed items to `approved`, delete `replan-request.json`, and pass `decomposer.py validate`.

#### Scenario: Decompose markdown proposal into roadmap candidates
WHEN a user provides a long markdown proposal to `plan-roadmap`
THEN the workflow SHALL extract candidate capabilities, constraints, and phases
AND it SHALL emit a roadmap artifact conforming to `contracts/roadmap.schema.json`
AND each candidate SHALL include effort estimate and rationale.

#### Scenario: Reject decomposition when proposal input is insufficient
WHEN the input markdown omits required implementation intent (no actionable capabilities or constraints)
THEN `plan-roadmap` SHALL fail with a structured validation error
AND it SHALL provide guidance for minimum required proposal sections.

#### Scenario: Seed OpenSpec change scaffolds from approved candidates
WHEN the user approves selected roadmap candidates
THEN `plan-roadmap` SHALL create draft OpenSpec change directories for each approved candidate
AND each created change SHALL include a proposal scaffold with a `parent_roadmap` field linking back to the roadmap change-id and item-id.

#### Scenario: Merge undersized roadmap items during decomposition
WHEN decomposition produces candidate items that are smaller than a single implementable OpenSpec change
THEN `plan-roadmap` SHALL merge them with adjacent items
AND it SHALL record the merge rationale in the merged item's description.

#### Scenario: Split oversized roadmap items during decomposition
WHEN a candidate item exceeds single-change scope (spans multiple independent capabilities or systems)
THEN `plan-roadmap` SHALL split it into separate items
AND it SHALL add dependency edges between the resulting items where ordering matters.

#### Scenario: Replan scope is the affected subgraph only
WHEN `decomposer.py replan-scope <workspace>` runs against a roadmap where `ri-03` failed with a replan signal and `ri-04`, `ri-06` depend on it while `ri-05` is completed
THEN the output SHALL list exactly `ri-04` and `ri-06` (and their transitive dependents that are not in a preserved status)
AND it SHALL NOT list `ri-05` or any completed item.

#### Scenario: Replan preserves completed items and learnings
WHEN `/plan-roadmap --replan <roadmap-id>` completes
THEN every item that was `completed`, `superseded`, or `in_progress` SHALL be byte-identical to its pre-replan entry
AND every file under `learnings/` SHALL be unchanged
AND `replan-request.json` SHALL no longer exist
AND `decomposer.py validate` SHALL exit 0.

#### Scenario: Replan without a request file is refused
WHEN `/plan-roadmap --replan <roadmap-id>` is invoked and `<workspace>/replan-request.json` does not exist
THEN the workflow SHALL exit with a structured error naming the missing file
AND the roadmap SHALL be unchanged.

### Requirement: Adaptive Roadmap Execution

The system SHALL provide an `autopilot-roadmap` workflow that executes roadmap items iteratively and updates pending items using implementation evidence. When an item fails, `CheckpointManager.fail_item(checkpoint, roadmap, item_id, reason, *, replan=False)` SHALL transition the failed item's dependents to `blocked` by default and to `replan_required` only when the failing item's outcome payload carries an explicit `replan: true` signal; the workflow SHALL NOT infer hard-versus-workaroundable from the failure text. For every item in `replan_required`, the orchestrator SHALL evaluate `Gate.REPLAN_REQUIRED` through an injected `GateEvaluator` (default `approval_gate.build_default_gate()`); on `proceed` it SHALL write a `ReplanRequest` conforming to `contracts/events/replan-request.schema.json` to `<workspace>/replan-request.json` and finish the run with status `replan_requested`; on `blocked` the items SHALL stay `replan_required`, the decision SHALL be recorded in the checkpoint, and the run SHALL continue with other ready items. The orchestrator SHALL make no LLM or network call to perform the replan itself; the host executes `/plan-roadmap --replan <roadmap-id>`.

#### Scenario: Learning feedback updates remaining roadmap items
WHEN a roadmap item completes implementation and review
THEN `autopilot-roadmap` SHALL persist a learning entry to `learnings/<item-id>.md` conforming to `contracts/learning-log.schema.json`
AND it SHALL update the root `learning-log.md` index with a one-line summary
AND before the next item begins it SHALL ingest prior learning entries (direct dependencies + most recent 3)
AND it SHALL update pending item recommendations accordingly.

#### Scenario: Resume from persisted checkpoint after interruption
WHEN roadmap execution stops before completion
THEN `autopilot-roadmap` SHALL resume from the last successful checkpoint conforming to `contracts/checkpoint.schema.json`
AND it SHALL skip phases already marked complete unless forced by user input.

#### Scenario: Abort item execution when prerequisite roadmap dependency is incomplete
WHEN a roadmap item is selected for execution
AND one or more of its dependency items are not complete
THEN `autopilot-roadmap` SHALL block execution of that item
AND it SHALL emit a dependency-blocked status with missing dependency IDs.

#### Scenario: Handle individual roadmap item implementation failure
WHEN a roadmap item fails implementation (tests fail, review rejects, or design dead-end)
THEN `autopilot-roadmap` SHALL mark the item as `failed` in `roadmap.yaml` with a structured failure reason
AND it SHALL persist a learning entry recording the failure details, root cause, and recommendations
AND it SHALL transition dependent items in `approved` or `candidate` status to `blocked`
AND it SHALL proceed to the next eligible item rather than halting the entire roadmap.

#### Scenario: Explicit replan signal produces replan_required
WHEN a roadmap item fails and its outcome payload contains `replan: true`
THEN `fail_item(..., replan=True)` SHALL transition dependents in `approved` or `candidate` status to `replan_required` instead of `blocked`
AND each such dependent SHALL record the failed item id in `blocked_by`
AND the failed item itself SHALL still be marked `failed`.

#### Scenario: Replan gate proceeds and emits a request
WHEN at least one item is in `replan_required` after a failure is recorded
AND `Gate.REPLAN_REQUIRED` evaluates to `proceed`
THEN the orchestrator SHALL write `<workspace>/replan-request.json` listing the `replan_required` item ids, the failed item id, and the gate decision
AND the run summary status SHALL be `replan_requested`
AND no item in `replan_required` SHALL be dispatched.

#### Scenario: Replan gate blocked leaves items parked
WHEN `Gate.REPLAN_REQUIRED` evaluates to `blocked` (posture `block`, timeout default block, or coordinator unreachable)
THEN no `replan-request.json` SHALL be written
AND the affected items SHALL remain `replan_required`
AND the decision SHALL be persisted in the checkpoint's `gate_decisions`
AND the orchestrator SHALL continue with other ready items.

#### Scenario: Orchestrator never performs the replan itself
WHEN a replan request is emitted
THEN `skills/autopilot-roadmap/scripts/` SHALL contain no import of an LLM SDK and no network call to perform re-decomposition
AND the host-assisted invariant test SHALL continue to pass.

### Requirement: Usage-Limit-Aware Multi-Vendor Scheduling

The system SHALL apply explicit policy when vendor session/rate limits are encountered during roadmap execution.

#### Scenario: Wait policy selected under budget constraints
WHEN the preferred vendor hits a usage/session limit
AND active policy is `wait_if_budget_exceeded`
THEN `autopilot-roadmap` SHALL pause execution until the known reset window
AND it SHALL persist pause reason, blocked vendor, and expected resume timestamp in `checkpoint.json`.

#### Scenario: Switch policy selected when time saved exceeds configured threshold
WHEN the preferred vendor hits a usage/session limit
AND active policy is `switch_if_time_saved`
AND configured policy constraints allow alternate vendor cost
THEN `autopilot-roadmap` SHALL dispatch eligible work to an alternate vendor
AND it SHALL persist expected and observed cost/latency deltas in `checkpoint.json`.

#### Scenario: Cascading vendor failures with recursive policy evaluation
WHEN the preferred vendor hits a usage/session limit
AND the system switches to an alternate vendor per policy
AND the alternate vendor also fails or hits limits
THEN `autopilot-roadmap` SHALL apply the same policy evaluation recursively across remaining eligible vendors
AND it SHALL track cumulative switch attempts against `max_switch_attempts_per_item` from `roadmap.yaml` policy
AND when max attempts are exhausted it SHALL transition to fail-closed behavior.

#### Scenario: Fail closed when no eligible vendor exists
WHEN the preferred vendor is limited
AND no alternate vendor satisfies capability and policy constraints (or max switch attempts exceeded)
THEN `autopilot-roadmap` SHALL transition the current item to `blocked` in `roadmap.yaml`
AND it SHALL record required operator action to continue
AND it SHALL persist the full vendor switch history in `checkpoint.json` for audit.

### Requirement: Progressive Context Management

Roadmap workflows SHALL externalize planning/execution context to durable artifacts so progress does not depend on one model context window.

#### Scenario: Progressive context reload per phase
WHEN a roadmap phase starts
THEN the workflow SHALL load only required artifacts: roadmap item, checkpoint, and relevant learning entries (direct dependencies + most recent 3)
AND it SHALL avoid requiring full historical chat transcript
AND total loaded learning entries SHALL NOT exceed the dependency fan-in plus a configurable recency window (default 3).

#### Scenario: Learning log compaction for long roadmaps
WHEN the root `learning-log.md` index exceeds 50 entries
THEN the workflow SHALL run a compaction pass that summarizes older entries into `learnings/_archive.md`
AND it SHALL remove individual entry files no longer referenced by pending roadmap items
AND compaction SHALL preserve all entries referenced by items with status `in_progress`, `blocked`, or `replan_required`.

#### Scenario: Coordinator-backed context fallback
WHEN coordinator context APIs are available
THEN the workflow SHALL publish phase summaries to coordinator memory
AND when coordinator APIs are unavailable it SHALL continue using on-disk artifacts with equivalent content.

#### Scenario: Artifact corruption detected during load
WHEN a required roadmap artifact is malformed or missing required fields per its JSON Schema contract
THEN the workflow SHALL stop execution for that phase
AND it SHALL report a recoverable artifact-validation error with repair instructions referencing the relevant schema file.

### Requirement: Artifact Observability

Roadmap workflows SHALL emit structured log events to support debugging, auditing, and operational monitoring of long-running orchestration.

#### Scenario: Structured logging for item state transitions
WHEN a roadmap item transitions between states (e.g., `approved` → `in_progress`, `in_progress` → `completed`)
THEN the workflow SHALL emit a structured log event containing: item_id, from_state, to_state, timestamp, and triggering_action.

#### Scenario: Structured logging for policy decisions
WHEN the policy engine evaluates a vendor limit event
THEN the workflow SHALL emit a structured log event containing: decision (wait/switch/fail-closed), vendor, reason, cost_delta (if applicable), and latency_delta (if applicable).

#### Scenario: Structured logging for checkpoint operations
WHEN a checkpoint is saved, restored, or advanced
THEN the workflow SHALL emit a structured log event containing: operation (save/restore/advance), item_id, phase, and timestamp.

#### Scenario: Publish observability events to coordinator audit log
WHEN coordinator audit APIs are available (`CAN_GUARDRAILS=true`)
THEN the workflow SHALL publish item transitions and policy decisions to the coordinator audit log
AND when coordinator APIs are unavailable it SHALL continue with file-based logging only.

### Requirement: Artifact Sanitization

All roadmap artifact writers SHALL sanitize content before persisting to prevent secret exposure in durable, potentially committed state.

#### Scenario: Redact sensitive content from learning entries
WHEN writing a learning entry to `learnings/<item-id>.md`
THEN the writer SHALL pass the content through a sanitization utility
AND the utility SHALL reject or redact: credentials, API keys, tokens, raw vendor prompts/responses, environment variable values
AND it SHALL preserve: structured summaries, decision rationale, cost/latency metrics, capability observations.

#### Scenario: Validate sanitization on checkpoint writes
WHEN writing `checkpoint.json`
THEN the writer SHALL ensure vendor_state and pause_state contain only structured metadata
AND it SHALL NOT include raw error responses, authentication headers, or session tokens.

