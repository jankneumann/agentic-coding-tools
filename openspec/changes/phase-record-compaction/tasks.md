# Tasks: Phase-Record Compaction

**Change ID**: phase-record-compaction
**Status**: Draft

## Phase 1: Contracts (wp-contracts)

- [x] 1.1 Write JSON Schema for `PhaseRecord` at `contracts/schemas/phase-record.schema.json`
  **Files**: `contracts/schemas/phase-record.schema.json`
  **Spec scenarios**: skill-workflow / Phase Record Data Model — Round-trip equality through markdown
  **Design decisions**: D1, D10
  **Dependencies**: None

- [x] 1.2 Write JSON Schema for handoff local-file fallback at `contracts/schemas/handoff-local-fallback.schema.json`
  **Files**: `contracts/schemas/handoff-local-fallback.schema.json`
  **Spec scenarios**: skill-workflow / Phase Record Persistence Pipeline — Coordinator unavailable triggers local-file fallback
  **Design decisions**: D3
  **Dependencies**: None

- [x] 1.3 Write tests asserting JSON Schemas validate sample fixtures
  **Files**: `skills/tests/phase-record-compaction/test_schema_fixtures.py`, `skills/tests/phase-record-compaction/fixtures/phase_record_minimal.json`, `skills/tests/phase-record-compaction/fixtures/phase_record_full.json`, `skills/tests/phase-record-compaction/fixtures/handoff_local_fallback.json`
  **Spec scenarios**: skill-workflow / Phase Record Data Model
  **Dependencies**: 1.1, 1.2

- [x] 1.4 Write `contracts/README.md` documenting which contract sub-types apply (only schemas; no OpenAPI/DB/event contracts needed)
  **Files**: `contracts/README.md`
  **Dependencies**: 1.1, 1.2

## Phase 2: PhaseRecord Data Model (wp-phase-record-model)

- [ ] 2.1 Write tests for `PhaseRecord` dataclass construction and field validation
  **Files**: `skills/tests/phase-record-compaction/test_phase_record_model.py`
  **Spec scenarios**: skill-workflow / Phase Record Data Model — all scenarios
  **Design decisions**: D1
  **Dependencies**: 1.3

- [ ] 2.2 Implement `PhaseRecord`, `Decision`, `Alternative`, `TradeOff`, `FileRef` dataclasses
  **Files**: `skills/session-log/scripts/phase_record.py`
  **Spec scenarios**: skill-workflow / Phase Record Data Model
  **Design decisions**: D1
  **Dependencies**: 2.1

- [ ] 2.3 Write tests for `render_markdown()` round-trip and `parse_markdown()`
  **Files**: `skills/tests/phase-record-compaction/test_phase_record_markdown.py`
  **Spec scenarios**: skill-workflow / Phase Record Data Model — Round-trip equality through markdown; Empty optional sections render compactly; PhaseRecord Markdown Round-Trip Preserves Decision Index Tags — all scenarios
  **Design decisions**: D10
  **Dependencies**: 2.2

- [ ] 2.4 Implement `PhaseRecord.render_markdown()` and `parse_markdown()` with `architectural:` and `supersedes:` span preservation
  **Files**: `skills/session-log/scripts/phase_record.py`
  **Spec scenarios**: skill-workflow / PhaseRecord Markdown Round-Trip Preserves Decision Index Tags
  **Design decisions**: D10
  **Dependencies**: 2.3

- [ ] 2.5 Write tests for `to_handoff_payload()` and `from_handoff_payload()` round-trip
  **Files**: `skills/tests/phase-record-compaction/test_phase_record_handoff.py`
  **Spec scenarios**: skill-workflow / Phase Record Data Model — Round-trip equality through handoff payload
  **Dependencies**: 2.2

- [ ] 2.6 Implement `to_handoff_payload()` and `from_handoff_payload()` matching `HandoffService.write` arguments
  **Files**: `skills/session-log/scripts/phase_record.py`
  **Spec scenarios**: skill-workflow / Phase Record Data Model
  **Dependencies**: 2.5

- [ ] 2.7 Write tests for `write_both()` — happy path, coordinator unavailable, sanitizer failure, append failure
  **Files**: `skills/tests/phase-record-compaction/test_phase_record_write_both.py`
  **Spec scenarios**: skill-workflow / Phase Record Persistence Pipeline — all four scenarios
  **Design decisions**: D2, D3, D4
  **Dependencies**: 2.4, 2.6

- [ ] 2.8 Implement `PhaseRecord.write_both()` three-step pipeline with best-effort failure semantics and local-file fallback
  **Files**: `skills/session-log/scripts/phase_record.py`
  **Spec scenarios**: skill-workflow / Phase Record Persistence Pipeline
  **Design decisions**: D2, D3, D4
  **Dependencies**: 2.7

- [ ] 2.9 Extend `openspec/schemas/feature-workflow/templates/session-log.md` with `## Completed Work` and `## Relevant Files` sections; update `skills/session-log/SKILL.md` phase-entry template to match
  **Files**: `openspec/schemas/feature-workflow/templates/session-log.md`, `skills/session-log/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase Record Data Model — Empty optional sections render compactly
  **Dependencies**: 2.8

- [ ] 2.10 Re-implement `append_phase_entry()` as deprecation-warned compatibility shim that constructs a minimal `PhaseRecord` and calls `write_both()`
  **Files**: `skills/session-log/scripts/extract_session_log.py`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption — Legacy append_phase_entry callers continue working
  **Design decisions**: D5
  **Dependencies**: 2.8

- [ ] 2.11 Update `skills/tests/session-log/test_extract_session_log.py` to assert deprecation warning is emitted on `append_phase_entry` call
  **Files**: `skills/tests/session-log/test_extract_session_log.py`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption — Legacy append_phase_entry callers continue working
  **Dependencies**: 2.10

## Phase 3: Skill Retrofits (wp-skills-retrofit) — Parallelizable Sub-Tasks

- [ ] 3.1 Retrofit `plan-feature` SKILL.md Step 11.5 to use `PhaseRecord.write_both()` instead of `append_phase_entry`
  **Files**: `skills/plan-feature/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption — A skill produces matching session-log and coordinator content
  **Dependencies**: 2.8, 2.9

- [ ] 3.2 Retrofit `iterate-on-plan` SKILL.md to use `PhaseRecord.write_both()`
  **Files**: `skills/iterate-on-plan/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption
  **Dependencies**: 2.8, 2.9

- [ ] 3.3 Retrofit `implement-feature` SKILL.md to use `PhaseRecord.write_both()`
  **Files**: `skills/implement-feature/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption
  **Dependencies**: 2.8, 2.9

- [ ] 3.4 Retrofit `iterate-on-implementation` SKILL.md to use `PhaseRecord.write_both()`
  **Files**: `skills/iterate-on-implementation/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption
  **Dependencies**: 2.8, 2.9

- [ ] 3.5 Retrofit `validate-feature` SKILL.md to use `PhaseRecord.write_both()`
  **Files**: `skills/validate-feature/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption
  **Dependencies**: 2.8, 2.9

- [ ] 3.6 Retrofit `cleanup-feature` SKILL.md to use `PhaseRecord.write_both()`
  **Files**: `skills/cleanup-feature/SKILL.md`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption
  **Dependencies**: 2.8, 2.9

- [ ] 3.7 Write integration test: each retrofitted skill produces matching `session-log.md` and `handoff_documents` content for the same phase
  **Files**: `skills/tests/phase-record-compaction/test_skills_integration.py`
  **Spec scenarios**: skill-workflow / Phase-Boundary Skill PhaseRecord Adoption — A skill produces matching session-log and coordinator content
  **Dependencies**: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6

## Phase 4: Autopilot Layer 1 — Handoff Wiring (wp-autopilot-layer-1)

- [ ] 4.1 Write tests for `build_phase_record(state, prev, next)` — produces valid `PhaseRecord` for each `_HANDOFF_BOUNDARIES` pair
  **Files**: `skills/tests/phase-record-compaction/test_handoff_builder.py`
  **Spec scenarios**: skill-workflow / Coordinator Handoff Population at Autopilot Phase Boundaries — Handoff is populated on each defined boundary
  **Dependencies**: 2.8

- [ ] 4.2 Implement `skills/autopilot/scripts/handoff_builder.py` with `build_phase_record(state, prev, next) -> PhaseRecord` and per-phase builders
  **Files**: `skills/autopilot/scripts/handoff_builder.py`
  **Spec scenarios**: skill-workflow / Coordinator Handoff Population at Autopilot Phase Boundaries
  **Dependencies**: 4.1

- [ ] 4.3 Write tests for `LoopState` schema bump — `last_handoff_id` field, backward-compat snapshot loading
  **Files**: `skills/tests/phase-record-compaction/test_loopstate_schema.py`
  **Spec scenarios**: skill-workflow / Coordinator Handoff Population at Autopilot Phase Boundaries — Existing autopilot snapshots load without migration
  **Dependencies**: None

- [ ] 4.4 Add `last_handoff_id: str | None = None` field to `LoopState` in `skills/autopilot/scripts/autopilot.py:47-72`; bump `schema_version` to 2; ensure `from_dict`/`to_dict` round-trip preserves new field; existing snapshots load with `last_handoff_id=None`
  **Files**: `skills/autopilot/scripts/autopilot.py`
  **Spec scenarios**: skill-workflow / Coordinator Handoff Population at Autopilot Phase Boundaries — Existing autopilot snapshots load without migration
  **Dependencies**: 4.3

- [ ] 4.5 Write tests for `_maybe_handoff` dispatch — calls `handoff_fn(state, PhaseRecord)` instead of description-string; appends `handoff_id` to `state.handoff_ids`; updates `state.last_handoff_id`
  **Files**: `skills/tests/phase-record-compaction/test_autopilot_handoff_dispatch.py`
  **Spec scenarios**: skill-workflow / Coordinator Handoff Population at Autopilot Phase Boundaries — Handoff is populated on each defined boundary
  **Dependencies**: 4.4, 4.2

- [ ] 4.6 Modify `_maybe_handoff` at `skills/autopilot/scripts/autopilot.py:702-712` to call `handoff_fn(state, build_phase_record(state, prev, next))`; update `handoff_fn` callable signature to `Callable[[LoopState, PhaseRecord], str | None]`; populate `state.handoff_ids` and `state.last_handoff_id` from return value
  **Files**: `skills/autopilot/scripts/autopilot.py`
  **Spec scenarios**: skill-workflow / Coordinator Handoff Population at Autopilot Phase Boundaries
  **Dependencies**: 4.5

- [ ] 4.7 Write tests for `phase_token_meter.py` — SDK path, proxy fallback, disabled path
  **Files**: `skills/tests/phase-record-compaction/test_phase_token_meter.py`
  **Spec scenarios**: skill-workflow / Context Window Token Instrumentation — all three scenarios
  **Design decisions**: D9
  **Dependencies**: None

- [ ] 4.8 Implement `skills/autopilot/scripts/phase_token_meter.py` with `measure_context(messages) -> int`; SDK primary, proxy fallback, env-var disable
  **Files**: `skills/autopilot/scripts/phase_token_meter.py`
  **Spec scenarios**: skill-workflow / Context Window Token Instrumentation
  **Design decisions**: D9
  **Dependencies**: 4.7

- [ ] 4.9 Wire `measure_context()` calls into autopilot at each `_HANDOFF_BOUNDARIES` transition; emit `phase_token_pre` and `phase_token_post` audit entries via coordinator
  **Files**: `skills/autopilot/scripts/autopilot.py`
  **Spec scenarios**: skill-workflow / Context Window Token Instrumentation
  **Design decisions**: D9
  **Dependencies**: 4.8, 4.6

## Phase 5: Autopilot Layer 2 — Sub-Agent Isolation (wp-autopilot-layer-2)

- [ ] 5.1 Write tests for `run_phase_subagent` return contract — `(outcome, handoff_id)` only, transcript not consumed
  **Files**: `skills/tests/phase-record-compaction/test_phase_agent.py`
  **Spec scenarios**: skill-workflow / Autopilot Phase Sub-Agent Isolation — Sub-agent return surfaces only outcome and handoff_id
  **Design decisions**: D6
  **Dependencies**: 4.6

- [ ] 5.2 Implement `skills/autopilot/scripts/phase_agent.py` exposing `run_phase_subagent(phase, state, incoming_handoff) -> tuple[str, str]`; assemble standard prompt scaffold (artifacts manifest, incoming PhaseRecord JSON, phase task instructions); use `Agent(...)` with `isolation: "worktree"` only when `phase == "IMPLEMENT"`
  **Files**: `skills/autopilot/scripts/phase_agent.py`
  **Spec scenarios**: skill-workflow / Autopilot Phase Sub-Agent Isolation — IMPLEMENT runs in worktree isolation; IMPL_REVIEW and VALIDATE run in shared checkout
  **Design decisions**: D6, D7
  **Dependencies**: 5.1

- [ ] 5.3 Write tests for crash recovery — first-attempt success, malformed-output retry, escalation after 3 failures
  **Files**: `skills/tests/phase-record-compaction/test_phase_agent_recovery.py`
  **Spec scenarios**: skill-workflow / Phase Sub-Agent Crash Recovery — all three scenarios
  **Design decisions**: D8
  **Dependencies**: 5.2

- [ ] 5.4 Implement crash recovery in `phase_agent.py` — retry up to 3 attempts with same incoming PhaseRecord; on final failure, write `phase-failed` PhaseRecord and raise `PhaseEscalationError(phase_name, attempts, last_error)`
  **Files**: `skills/autopilot/scripts/phase_agent.py`
  **Spec scenarios**: skill-workflow / Phase Sub-Agent Crash Recovery
  **Design decisions**: D8
  **Dependencies**: 5.3

- [ ] 5.5 Wire `run_phase_subagent` into autopilot for `IMPLEMENT`, `IMPL_REVIEW`, `VALIDATE` phase callbacks; replace inline phase logic with sub-agent dispatch; consume `(outcome, handoff_id)` return only
  **Files**: `skills/autopilot/scripts/autopilot.py`
  **Spec scenarios**: skill-workflow / Autopilot Phase Sub-Agent Isolation
  **Design decisions**: D6
  **Dependencies**: 5.4

- [ ] 5.6 Write tests for `LoopState` opacity — driver context delta after Layer 2 phase return is bounded; sub-agent transcript not in driver state
  **Files**: `skills/tests/phase-record-compaction/test_loopstate_opacity.py`
  **Spec scenarios**: skill-workflow / Autopilot Phase Sub-Agent Isolation — Sub-agent return surfaces only outcome and handoff_id
  **Dependencies**: 5.5

## Phase 6: Integration & Validation (wp-integration)

- [ ] 6.1 Run full pytest suite across `skills/tests/`, `skills/autopilot/scripts/tests/`, `agent-coordinator/tests/` — assert all existing tests pass plus all new tests pass
  **Spec scenarios**: All
  **Dependencies**: 5.6, 4.9, 3.7

- [ ] 6.2 Run `make decisions` against the corpus before and after this change; assert byte-identical output for `docs/decisions/<capability>.md` files
  **Spec scenarios**: skill-workflow / PhaseRecord Markdown Round-Trip Preserves Decision Index Tags — Decision index regenerator output is unchanged
  **Design decisions**: D10
  **Dependencies**: 2.4

- [ ] 6.3 Smoke-run a representative mid-size feature through autopilot end-to-end (e.g., a small bug-fix proposal) with token instrumentation enabled; collect `phase_token_pre`/`post` audit entries; compute peak-context-reduction percentage
  **Spec scenarios**: Success Criterion 4 (≥30% peak-context-window reduction)
  **Design decisions**: D9
  **Dependencies**: 6.1

- [ ] 6.4 Run `openspec validate phase-record-compaction --strict`; fix any spec format errors
  **Spec scenarios**: All
  **Dependencies**: 5.6, 4.9, 3.7

- [ ] 6.5 Run mypy strict + ruff on all modified files; fix type/lint errors
  **Files**: `skills/session-log/scripts/phase_record.py`, `skills/autopilot/scripts/handoff_builder.py`, `skills/autopilot/scripts/phase_agent.py`, `skills/autopilot/scripts/phase_token_meter.py`, `skills/autopilot/scripts/autopilot.py`
  **Dependencies**: 6.1
