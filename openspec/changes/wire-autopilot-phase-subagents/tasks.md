# Tasks — Wire Autopilot Per-Phase Sub-Agent Dispatch

## Phase 1 — Contracts (`wp-contracts`)

Lay down the schemas and migration before implementation packages
diverge. Tier B (CI). All implementation packages depend on this phase.

- [ ] 1.1 Write tests asserting the SQL migration is well-formed and applies
  cleanly against a fresh schema
  **Spec scenarios**: agent-coordinator-spec → "Migration applies without backfill"
  **Contracts**: `contracts/db/0NN_add_phase_archetype.sql`
  **Design decisions**: D8 (dedicated column over JSONB key)
  **Dependencies**: None

- [ ] 1.2 Author the SQL migration `contracts/db/0NN_add_phase_archetype.sql`
  with `ALTER TABLE agent_sessions ADD COLUMN phase_archetype TEXT`
  **Spec scenarios**: agent-coordinator-spec → "Migration applies without backfill"
  **Design decisions**: D8
  **Dependencies**: 1.1

- [ ] 1.3 Write a JSON schema for the extended `POST /status/report` payload at
  `contracts/events/status-report.schema.json` covering the `phase_archetype`
  field as optional `string | null`
  **Spec scenarios**: agent-coordinator-spec → "Status report with phase_archetype is persisted", "Status report without phase_archetype is accepted"
  **Design decisions**: D6
  **Dependencies**: None

- [ ] 1.4 Add an OpenAPI fragment to `contracts/openapi/discovery-agents.yaml`
  describing the `phase_archetype` field on the `GET /discovery/agents`
  response, with example values from `archetypes.yaml`
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery"
  **Design decisions**: D8
  **Dependencies**: 1.3

## Phase 2 — Skills autopilot wiring (`wp-skills-autopilot`)

Build the helpers, the runner CLI entry, and rewrite the SKILL.md
phase blocks. Depends on `wp-contracts`.

- [ ] 2.1 Write unit tests for `phase_agent.build_phase_dispatch_kwargs` —
  returns dict with required keys; cache file is written; cache file is
  schema-correct
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D3 (dict return), D2 (system_prompt folding)
  **Dependencies**: None

- [ ] 2.2 Implement `phase_agent.build_phase_dispatch_kwargs(phase, change_id)`
  in `skills/autopilot/scripts/phase_agent.py`. Pure function calling
  `_build_options` + `_build_prompt` + cache write. Folds `system_prompt`
  into prompt with `\n\n---\n\n` separator
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D2, D3
  **Dependencies**: 2.1

- [ ] 2.3 Write unit tests for `phase_agent.apply_phase_outcome` — idempotent;
  loop-state.json fields update correctly; cache mismatch writes null
  archetype
  **Spec scenarios**: skill-workflow-spec → "apply_phase_outcome updates loop state and is idempotent", "apply_phase_outcome with mismatched cache writes null archetype"
  **Design decisions**: D4 (cache file), Q1 (idempotency)
  **Dependencies**: 2.1

- [ ] 2.4 Implement `phase_agent.apply_phase_outcome(change_id, phase, outcome,
  handoff_id)`. Loads loop-state.json, validates cache phase matches arg,
  updates `last_handoff_id` / `handoff_ids` / `phase_archetype`, saves
  **Spec scenarios**: skill-workflow-spec → "apply_phase_outcome updates loop state and is idempotent"
  **Design decisions**: D4
  **Dependencies**: 2.3

- [ ] 2.5 Write CLI integration test for `runner.py` — both `build-dispatch`
  and `apply-outcome` subcommands work from shell, JSON output is parseable
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D3
  **Dependencies**: 2.1, 2.3

- [ ] 2.6 Create `skills/autopilot/scripts/runner.py` with argparse-based CLI
  exposing `build-dispatch` and `apply-outcome` subcommands wrapping the
  helpers
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D3
  **Dependencies**: 2.5

- [ ] 2.7 Write tests for `autopilot._resolve_phase_archetype_for_state_only`
  — INIT records archetype despite no sub-agent dispatch
  **Spec scenarios**: skill-workflow-spec → "INIT phase records archetype despite being state-only"
  **Design decisions**: D7
  **Dependencies**: None

- [ ] 2.8 Implement `autopilot._resolve_phase_archetype_for_state_only(state, phase)`
  and call it at INIT phase entry inside `run_loop`. SUBMIT_PR similarly
  **Spec scenarios**: skill-workflow-spec → "INIT phase records archetype despite being state-only"
  **Design decisions**: D7
  **Dependencies**: 2.7

- [ ] 2.9 Write a snapshot test for the joined system_prompt + phase prompt
  rendering — verify the `\n\n---\n\n` separator appears and the
  system_prompt is clearly delimited from the task prompt
  **Spec scenarios**: skill-workflow-spec → "Production autopilot run dispatches harness Agent with resolved model"
  **Design decisions**: D2 (folding semantics)
  **Dependencies**: 2.1

- [ ] 2.10 Update `skills/autopilot/SKILL.md`: replace each "Invoke
  /implement-feature" / "/iterate-on-implementation" / "/validate-feature"
  prose block with an explicit 3-step dispatch (build kwargs → call Agent →
  apply outcome). Keep an explicit "if dispatch fails or no archetype
  resolves, fall through to inline `/<skill>`" fallback per D5
  **Spec scenarios**: skill-workflow-spec → "Production autopilot run dispatches harness Agent with resolved model", "Harness Agent tool not exposed, fallback to inline path"
  **Design decisions**: D1, D5
  **Dependencies**: 2.6, 2.8

## Phase 3 — Coordinator status reporter and discovery (`wp-coordinator-status-discovery`)

Closes deferred D-1 and D-2. Depends on `wp-contracts`. Can run in
parallel with Phase 2.

- [ ] 3.1 Write tests for the SQL migration application against a real Postgres
  test container — verifies the column is added without altering existing
  data
  **Spec scenarios**: agent-coordinator-spec → "Migration applies without backfill"
  **Contracts**: `contracts/db/0NN_add_phase_archetype.sql`
  **Design decisions**: D8
  **Dependencies**: 1.2

- [ ] 3.2 Apply the migration into `agent-coordinator/database/migrations/`
  with the next available sequence number; verify it loads at coordinator
  startup
  **Spec scenarios**: agent-coordinator-spec → "Migration applies without backfill"
  **Design decisions**: D8
  **Dependencies**: 3.1

- [ ] 3.3 Write tests for `AgentInfo.phase_archetype` round-trip via
  `DiscoveryService.heartbeat` and `GET /discovery/agents`
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery", "AgentInfo without phase_archetype defaults to None"
  **Contracts**: `contracts/openapi/discovery-agents.yaml`
  **Design decisions**: D8
  **Dependencies**: 1.4

- [ ] 3.4 Extend `AgentInfo` dataclass with `phase_archetype: str | None = None`;
  extend `DiscoveryService.heartbeat` to accept and persist; surface the
  field in `GET /discovery/agents` response
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery"
  **Design decisions**: D8
  **Dependencies**: 3.2, 3.3

- [ ] 3.5 Write tests for `report_status.py` reading `phase_archetype` from
  `loop-state.json` and including it in the POST body
  **Spec scenarios**: agent-coordinator-spec → "report_status.py reads phase_archetype from loop-state.json", "report_status.py handles missing phase_archetype gracefully"
  **Contracts**: `contracts/events/status-report.schema.json`
  **Design decisions**: D6
  **Dependencies**: 1.3

- [ ] 3.6 Modify `agent-coordinator/scripts/report_status.py` to read
  `state.phase_archetype` from `loop-state.json` (line ~97-100) and add to
  POST body (line ~118-128). Pass through to `coordination_api.report_status`
  endpoint
  **Spec scenarios**: agent-coordinator-spec → "report_status.py reads phase_archetype from loop-state.json"
  **Design decisions**: D6
  **Dependencies**: 3.5

- [ ] 3.7 Write tests for `coordination_api.report_status` accepting the new
  field and forwarding it through the event bus to discovery persistence
  **Spec scenarios**: agent-coordinator-spec → "Status report with phase_archetype is persisted"
  **Design decisions**: D6, D8
  **Dependencies**: 3.4, 3.6

- [ ] 3.8 Verify `coordination_api.report_status` already forwards
  `phase_archetype` through the event bus (per archived change). If a gap
  exists between event bus and discovery write, close it
  **Spec scenarios**: agent-coordinator-spec → "Status report with phase_archetype is persisted"
  **Design decisions**: D6, D8
  **Dependencies**: 3.7

## Phase 4 — Integration validation (`wp-integration`)

Final cross-package verification. Depends on Phase 2 and Phase 3.

- [ ] 4.1 Write end-to-end test `skills/tests/autopilot/test_phase_dispatch_e2e.py`
  using a mocked harness `Agent(...)` runner. Run autopilot through one full
  loop. Assert: every non-terminal phase's `LoopState.phase_archetype` matches
  `archetypes.yaml::phase_mapping`; every dispatch was called with the
  resolved model; cache file is reset between phases
  **Spec scenarios**: skill-workflow-spec → "All 13 non-terminal phases dispatch with resolved archetype", "Production autopilot run dispatches harness Agent with resolved model"
  **Design decisions**: D1, D3, D4, D7
  **Dependencies**: 2.10, 3.4

- [ ] 4.2 Write end-to-end test `agent-coordinator/tests/test_phase_archetype_persistence.py`
  asserting full round-trip: autopilot writes `phase_archetype` to loop-state →
  report_status.py POSTs → coordinator persists → `GET /discovery/agents`
  returns the value. Use FastAPI TestClient (in-process) per archived test
  pattern
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery", "Status report with phase_archetype is persisted"
  **Design decisions**: D6, D8
  **Dependencies**: 3.4, 3.6, 3.7

- [ ] 4.3 Write inline-fallback regression test — when `Agent(...)` is not
  exposed (mocked absence), SKILL.md dispatch falls through; LoopState
  records `phase_archetype = None`; warning is emitted
  **Spec scenarios**: skill-workflow-spec → "Harness Agent tool not exposed, fallback to inline path", "Coordinator unreachable, autopilot continues"
  **Design decisions**: D5
  **Dependencies**: 2.10

- [ ] 4.4 Author `skills/autopilot/scripts/audit_log_validator.py` — reads a
  coordinator audit log file (or queries the audit endpoint), counts model
  calls per archetype, and asserts opus-vs-sonnet distribution matches
  `phase_mapping` over a real run. Used for the manual rollout validation
  step in the proposal's Rollout section
  **Spec scenarios**: skill-workflow-spec → "Production autopilot run dispatches harness Agent with resolved model"
  **Design decisions**: G2, G3 (proposal goals)
  **Dependencies**: 4.1

- [ ] 4.5 Run `bash skills/install.sh --mode rsync --deps none --python-tools none`
  to sync runtime skill copies (`.claude/skills/`, `.agents/skills/`)
  **Dependencies**: 2.10

- [ ] 4.6 Update `docs/autopilot-phase-archetype-resolution.md` with the
  production-path execution diagram from `design.md` plus the manual
  validation steps
  **Spec scenarios**: skill-workflow-spec → "Production autopilot run dispatches harness Agent with resolved model"
  **Dependencies**: 4.4
