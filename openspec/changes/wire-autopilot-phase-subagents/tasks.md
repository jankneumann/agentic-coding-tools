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

- [x] 2.1 Write unit tests for `phase_agent.build_phase_dispatch_kwargs` —
  returns dict with required keys; cache file is written; cache file is
  schema-correct
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D3 (dict return), D2 (system_prompt folding)
  **Dependencies**: None

- [x] 2.2 Implement `phase_agent.build_phase_dispatch_kwargs(phase, change_id)`
  in `skills/autopilot/scripts/phase_agent.py`. Pure function calling
  `_build_options` + `_build_prompt` + cache write. Folds `system_prompt`
  into prompt with `\n\n---\n\n` separator
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D2, D3
  **Dependencies**: 2.1

- [x] 2.3 Write unit tests for `phase_agent.apply_phase_outcome` — idempotent;
  loop-state.json fields update correctly; cache mismatch writes null
  archetype
  **Spec scenarios**: skill-workflow-spec → "apply_phase_outcome updates loop state and is idempotent", "apply_phase_outcome with mismatched cache writes null archetype"
  **Design decisions**: D4 (cache file), Q1 (idempotency)
  **Dependencies**: 2.1

- [x] 2.4 Implement `phase_agent.apply_phase_outcome(change_id, phase, outcome,
  handoff_id)`. Loads loop-state.json, **first checks the replay rule**
  (`state.last_handoff_id == handoff_id AND state.previous_phase == phase`)
  and short-circuits to a no-op preserving phase_archetype if matched.
  When NOT in replay, validates cache change_id+phase+checksum, updates
  `last_handoff_id` / `handoff_ids` / `phase_archetype`, atomically
  deletes the cache, saves
  **Spec scenarios**: skill-workflow-spec → "apply_phase_outcome updates loop state and is idempotent under replay"
  **Design decisions**: D4 (cache file lifecycle + replay rule)
  **Dependencies**: 2.3

- [x] 2.5 Write CLI integration test for `runner.py` — both `build-dispatch`
  and `apply-outcome` subcommands work from shell, JSON output is parseable
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs returns dispatch-ready dict"
  **Design decisions**: D3
  **Dependencies**: 2.1, 2.3

- [x] 2.6 Create `skills/autopilot/scripts/runner.py` with argparse-based CLI
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
  rendering. The test SHALL include a phase prompt that itself contains
  `\n---\n` (markdown rule inside task instructions) and assert via
  regex that (a) exactly one occurrence of the literal SEPARATOR
  `"\n\n---\n\n"` appears between the system prompt and the phase prompt,
  (b) all key task-instruction tokens (`change_id`, `submit`, `complete`)
  from the phase prompt survive the fold unchanged
  **Spec scenarios**: skill-workflow-spec → "Joined prompt preserves phase task instructions even when phase prompt contains '---'"
  **Design decisions**: D2 (folding semantics + separator clash mitigation)
  **Dependencies**: 2.1

- [ ] 2.9a Write tests for path-traversal rejection in
  `build_phase_dispatch_kwargs`: verify ValueError is raised for inputs
  like `"../../etc/passwd"`, `"foo/bar"`, empty string, strings longer
  than 128 chars, and strings with non-ASCII characters
  **Spec scenarios**: skill-workflow-spec → "build_phase_dispatch_kwargs rejects path-traversal change_id"
  **Design decisions**: D4 (cache file path validation)
  **Dependencies**: 2.1

- [ ] 2.9b Write the per-phase token-budget CI gate at
  `skills/autopilot/scripts/token_budget_check.py`. Iterates over all
  7 sub-agent-dispatching phases (PLAN_ITERATE, PLAN_REVIEW, IMPLEMENT,
  IMPL_ITERATE, IMPL_REVIEW, VALIDATE, VAL_REVIEW), computes the joined
  prompt size, compares against the resolved model's context window:
  fails (exit 1) at >75%, warns at 60-75%, passes silently below 60%.
  Add a CI step in the work-package's verification block invoking it
  **Spec scenarios**: skill-workflow-spec → "Joined prompt token budget is enforced"
  **Design decisions**: Risks → Prompt-size pressure
  **Dependencies**: 2.2, 2.6

- [ ] 2.10 Update `skills/autopilot/SKILL.md`: replace the existing prose
  blocks for the **7 sub-agent-dispatching phases** (PLAN_ITERATE,
  PLAN_REVIEW, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, VALIDATE,
  VAL_REVIEW) with explicit 3-step dispatch blocks (build kwargs → call
  Agent → apply outcome). Each block ends with an explicit "if dispatch
  fails OR no archetype resolves, fall through to inline `/<skill>`"
  fallback clause per D5. Phases NOT rewritten: INIT, PLAN, PLAN_FIX,
  IMPL_FIX, VAL_FIX, SUBMIT_PR (per the dispatch matrix in design.md)
  **Spec scenarios**: skill-workflow-spec → "Production autopilot run dispatches harness Agent with resolved model", "Harness Agent tool not exposed, fallback to inline path"
  **Design decisions**: D1, D5; design.md "Phase-by-phase dispatch matrix"
  **Dependencies**: 2.6, 2.8

- [ ] 2.11 Add `openspec/changes/*/.phase-resolution-cache.json` to the
  project `.gitignore`
  **Design decisions**: D4 (cache file lifecycle)
  **Dependencies**: None

- [ ] 2.12 Write a test that exercises the `_FIX` phase archetype-inheritance
  path: drive a fake convergence loop that does NOT converge on round 1,
  triggering PLAN_FIX. Assert `LoopState.phase_archetype` retains the
  value set by the preceding PLAN_REVIEW (i.e. convergence_loop does
  not overwrite the field). This test guards against R1-009-class
  regressions where _FIX phases would silently null the field
  **Spec scenarios**: skill-workflow-spec → "PLAN_FIX inherits phase_archetype from PLAN_REVIEW"
  **Design decisions**: design.md "Phase-by-phase dispatch matrix" — _FIX rows
  **Dependencies**: 2.4, 2.10

## Phase 3 — Coordinator status reporter and discovery (`wp-coordinator-status-discovery`)

Closes deferred D-1 and D-2. Depends on `wp-contracts`. Can run in
parallel with Phase 2.

- [x] 3.1 Write tests for the SQL migration application against a real Postgres
  test container. Verifies: (a) the column is added without altering
  existing rows; (b) the CHECK constraint rejects out-of-enum values;
  (c) the updated `discover_agents()` RPC returns `phase_archetype`
  in its JSONB response after a heartbeat; (d) the updated
  `agent_heartbeat()` RPC accepts the new `p_phase_archetype` parameter
  and persists it via `COALESCE(p_phase_archetype, phase_archetype)`
  (heartbeats with no value passed don't null the field)
  **Spec scenarios**: agent-coordinator-spec → "Migration applies without backfill", "AgentInfo round-trip via heartbeat and discovery"
  **Contracts**: `contracts/db/0NN_add_phase_archetype.sql`
  **Design decisions**: D8; codex review R1-004
  **Dependencies**: 1.2

- [x] 3.2 Apply the migration into `agent-coordinator/database/migrations/`
  with the next available sequence number; verify it loads at coordinator
  startup
  **Spec scenarios**: agent-coordinator-spec → "Migration applies without backfill"
  **Design decisions**: D8
  **Dependencies**: 3.1

- [x] 3.3 Write tests for `AgentInfo.phase_archetype` round-trip via
  `DiscoveryService.heartbeat` and `GET /discovery/agents`
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery", "AgentInfo without phase_archetype defaults to None"
  **Contracts**: `contracts/openapi/discovery-agents.yaml`
  **Design decisions**: D8
  **Dependencies**: 1.4

- [x] 3.4 Extend `AgentInfo` dataclass with `phase_archetype: str | None = None`;
  extend `DiscoveryService.heartbeat(...)` to accept and forward
  `phase_archetype` to the `agent_heartbeat` SQL RPC; extend
  `DiscoveryService.discover(...)` to parse `phase_archetype` from the
  `discover_agents` RPC's JSONB response and place it on the returned
  `AgentInfo`; surface the field in the `GET /discovery/agents` response
  builder at `coordination_api.py:2122` (the discovery_agents() handler
  builds the response dict by hand — `phase_archetype` must be added
  to the per-agent dict construction). The migration in 3.2 already
  updates the two SQL RPCs (`discover_agents`, `agent_heartbeat`) so
  they accept and return the new field — task 3.4 is the Python side
  of that contract
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery"
  **Design decisions**: D8; codex review R1-004 (RPC update is required, ALTER TABLE alone is insufficient)
  **Dependencies**: 3.2, 3.3

- [x] 3.5 Write tests for `report_status.py` reading `phase_archetype` from
  `loop-state.json` and including it in the POST body
  **Spec scenarios**: agent-coordinator-spec → "report_status.py reads phase_archetype from loop-state.json", "report_status.py handles missing phase_archetype gracefully"
  **Contracts**: `contracts/events/status-report.schema.json`
  **Design decisions**: D6
  **Dependencies**: 1.3

- [x] 3.6 Modify `agent-coordinator/scripts/report_status.py` to read
  `state.phase_archetype` from `loop-state.json` (line ~97-100) and add to
  POST body (line ~118-128). Pass through to `coordination_api.report_status`
  endpoint
  **Spec scenarios**: agent-coordinator-spec → "report_status.py reads phase_archetype from loop-state.json"
  **Design decisions**: D6
  **Dependencies**: 3.5

- [x] 3.7 Write tests for `coordination_api.report_status` accepting the new
  field and forwarding it through the event bus to discovery persistence
  **Spec scenarios**: agent-coordinator-spec → "Status report with phase_archetype is persisted"
  **Design decisions**: D6, D8
  **Dependencies**: 3.4, 3.6

- [x] 3.8 Read `agent-coordinator/src/coordination_api.py` `discovery_register`
  and `report_status` endpoint handlers (cite line ranges in the commit
  message). Confirm by code inspection that the archived change's event
  bus path forwards `phase_archetype` from POST /status/report into the
  discovery service's persistence layer. If the inspection finds NO such
  forwarding, add the wiring inline: extend the `StatusReportRequest`
  Pydantic model to include `phase_archetype: str | None = None`,
  forward to `DiscoveryService.heartbeat(phase_archetype=...)`, and
  cover with a regression test
  **Spec scenarios**: agent-coordinator-spec → "Status report with phase_archetype is persisted"
  **Design decisions**: D6, D8
  **Dependencies**: 3.7

- [x] 3.9 Add Pydantic enum validation to `StatusReportRequest`:
  `phase_archetype: Literal["architect","reviewer","implementer","analyst","runner"] | None = None`.
  Verify that out-of-enum POSTs return HTTP 422 (FastAPI default
  validation error). Regression test asserts both the 422 response and
  that the agent_sessions row remains unchanged
  **Spec scenarios**: agent-coordinator-spec → "POST /status/report rejects out-of-enum phase_archetype values"
  **Design decisions**: Risks → DB-layer enum enforcement
  **Dependencies**: 3.7

- [x] 3.10 Add client-side enum validation to `report_status.py`:
  before including `phase_archetype` in the POST body, validate it
  against the allowed set. If invalid (local file tampering or older
  client writing wrong values), drop the field and log a structured
  warning instead of forwarding
  **Spec scenarios**: agent-coordinator-spec → "report_status.py drops invalid phase_archetype values from POST"
  **Design decisions**: Risks → DB-layer enum enforcement (defense in depth)
  **Dependencies**: 3.6

## Phase 4 — Integration validation (`wp-integration`)

Final cross-package verification. Depends on Phase 2 and Phase 3.

- [ ] 4.1 Write end-to-end test `skills/tests/autopilot/test_phase_dispatch_e2e.py`
  using a mocked harness `Agent(...)` runner. Run autopilot through one
  full loop from INIT to DONE. Assertions:
  - Every non-terminal phase's `LoopState.phase_archetype` is non-null
    and matches `archetypes.yaml::phase_mapping`.
  - **INIT specifically** records `phase_archetype = "runner"` despite
    NOT calling the mocked Agent (state-only path per D7).
  - **SUBMIT_PR specifically** records `phase_archetype = "runner"`
    despite NOT calling the mocked Agent (state-only path per D7).
  - The 7 sub-agent-dispatching phases (PLAN_ITERATE, PLAN_REVIEW,
    IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, VALIDATE, VAL_REVIEW) each
    invoke the mocked Agent exactly once with `model` set to the
    resolved phase mapping.
  - The cache file `.phase-resolution-cache.json` is created and
    deleted between consecutive phases (assert it does not exist
    after `apply_phase_outcome` succeeds).
  **Spec scenarios**: skill-workflow-spec → "All 13 non-terminal phases dispatch with resolved archetype", "Production autopilot run dispatches harness Agent with resolved model", "INIT phase records archetype despite being state-only"
  **Design decisions**: D1, D3, D4, D7; design.md "Phase-by-phase dispatch matrix"
  **Dependencies**: 2.10, 3.4

- [ ] 4.2 Write end-to-end test `agent-coordinator/tests/test_phase_archetype_persistence.py`
  asserting full round-trip: autopilot writes `phase_archetype` to loop-state →
  report_status.py POSTs → coordinator persists → `GET /discovery/agents`
  returns the value. Use FastAPI TestClient (in-process) per archived test
  pattern
  **Spec scenarios**: agent-coordinator-spec → "AgentInfo round-trip via heartbeat and discovery", "Status report with phase_archetype is persisted"
  **Design decisions**: D6, D8
  **Dependencies**: 3.4, 3.6, 3.7

- [ ] 4.3 Write inline-fallback regression tests covering three failure
  modes:
  - (a) `Agent(...)` not exposed (mocked absence) → SKILL.md dispatch
    falls through; LoopState records `phase_archetype = None`; warning
    emitted.
  - (b) Coordinator returns HTTP 503 for `POST /archetypes/resolve_for_phase`
    → bridge returns `None`; build_phase_dispatch_kwargs returns options
    without `model` or `system_prompt`; SKILL.md falls through.
  - (c) Bridge raises `TimeoutError` mid-resolution → bridge returns
    `None`; autopilot does not crash or retry inside the same dispatch.
  **Spec scenarios**: skill-workflow-spec → "Harness Agent tool not exposed, fallback to inline path", "Coordinator unreachable, autopilot continues", "Network timeout falls back gracefully"
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
