# Tasks: Automated Development Loop

## Task Dependencies

```
T1 (schema) ─────────────────────────────────┐
T2 (convergence engine + tests) ─────┐       │
T3 (strategy selector + tests) ─────┐│       │
T4 (complexity gate + tests) ───────┐││      │
                                    │││      │
T5 (state machine + tests) ────────┘┘┘      │
                                    │        │
T6 (SKILL.md) ────────────────────┘         │
                                             │
T7 (integration test) ─────────────────────┘
```

## Tasks

### T1: Create convergence-state schema + extend work-packages schema
**Priority**: 1 (no dependencies)
**Files**: `openspec/schemas/convergence-state.schema.json`, `openspec/schemas/work-packages.schema.json`

Define JSON Schema for the serializable loop state including:
- Phase enum (INIT, PLAN, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW, VAL_FIX, SUBMIT_PR, DONE, ESCALATE)
- Iteration tracking, findings trend array
- Vendor availability map, package status map
- `package_authors` map (vendor that authored each package)
- `implementation_strategy` map
- `memory_ids` list (episodic memory IDs, not string keys)
- `handoff_ids` list
- `previous_phase` and `escalation_reason` for ESCALATE state
- Timestamps, error field

Also add optional `metadata` object to WorkPackage in `work-packages.schema.json`:
- `loc_estimate` (integer, optional) — estimated lines of code
- `alternatives_count` (integer, optional) — design alternatives noted
- `package_kind` (string enum, optional) — algorithm, data_model, crud, config, migration, integration

**Acceptance**: `openspec validate --strict` passes with both schema changes. Existing work-packages.yaml files remain valid (metadata is optional).

---

### T2: Implement convergence loop engine
**Priority**: 1 (no dependencies)
**Files**: `skills/auto-dev-loop/scripts/convergence_loop.py`, `skills/auto-dev-loop/scripts/tests/test_convergence_loop.py`

Reusable review-fix convergence engine:
- Imports `ReviewOrchestrator` and `ConsensusSynthesizer` via sys.path from `skills/parallel-implement-feature/scripts/`
- Uses `ReviewOrchestrator.dispatch_and_wait()` with correct signature (review_type, dispatch_mode, prompt, cwd, ...)
- Uses `ConsensusSynthesizer.synthesize()` with correct signature (review_type, target, vendor_results)
- Reads `consensus_findings` and `summary.total_unique_findings` from results
- Implements quorum gate: require `min_quorum` successful vendor results before evaluating findings
- Implements exit condition: no blocking findings at configured severity
- Implements 3-point stall detection: escalate if findings at round N >= findings at round N-2
- Relaxes unconfirmed findings in final round only
- Fix dispatch differs by phase: inline for plan, targeted for implementation
- Writes episodic coordinator memory via `remember(event_type, summary, details, tags)` at each round
- Returns `ConvergenceResult` with converged flag, rounds count, consensus

**Acceptance**: Unit tests cover convergence (0 findings + quorum met), non-convergence (max rounds), stall detection (3-point window), quorum loss (< 2 vendors), inline vs targeted fix dispatch, and memory writes. Tests mock ReviewOrchestrator, ConsensusSynthesizer, and coordinator.

---

### T3: Implement implementation strategy selector
**Priority**: 1 (no dependencies)
**Files**: `skills/auto-dev-loop/scripts/implementation_strategy_selector.py`, `skills/auto-dev-loop/scripts/tests/test_implementation_strategy_selector.py`

Per-package decision logic:
- Input: work-packages.yaml (reads `metadata.loc_estimate`, `metadata.alternatives_count`, `metadata.package_kind`), design.md, vendor availability
- Output: dict mapping package_id to "alternatives" | "lead_review"
- Scoring: LOC estimate (<200 = alternatives), design alternatives count (>=2), package type (algorithm/data_model), vendor count (3)
- Threshold: score >= 2.0 → alternatives, else lead_review
- Fallback: if metadata absent, default to lead_review
- Recalls vendor effectiveness from coordinator memory (episodic recall with tags) to bias lead selection

**Acceptance**: Unit tests cover all scoring branches, boundary cases, metadata present vs absent, and fallback when memory unavailable.

---

### T4: Implement complexity gate
**Priority**: 1 (no dependencies)
**Files**: `skills/auto-dev-loop/scripts/complexity_gate.py`, `skills/auto-dev-loop/scripts/tests/test_complexity_gate.py`

Entry assessment:
- Input: proposal.md, work-packages.yaml, tasks.md
- Reads configurable thresholds from `work-packages.yaml` `defaults.auto_loop.*` with built-in fallbacks
- Output: `GateResult` with `allowed: bool`, `warnings: list`, `checkpoints: list`, `val_review_enabled: bool`
- Thresholds: LOC > 500, packages > 4, external deps > 2, db migrations, security paths
- Above threshold: warn + require `--force`, or inject manual review checkpoints
- Database migrations / security-sensitive paths → enable VAL_REVIEW

**Acceptance**: Unit tests cover each threshold independently and in combination, custom thresholds from YAML, and VAL_REVIEW injection.

---

### T5: Implement state machine conductor
**Priority**: 2 (depends on T1-T4)
**Files**: `skills/auto-dev-loop/scripts/auto_dev_loop.py`, `skills/auto-dev-loop/scripts/tests/test_auto_dev_loop.py`

The main conductor:
- Loads/saves `LoopState` from `loop-state.json` (dual-write to coordinator memory)
- Implements state transition table with all 13 states including PLAN and VAL_REVIEW
- PLAN phase delegates to `/parallel-plan-feature` or `/linear-plan-feature`
- VAL_REVIEW is conditional: skipped unless complexity gate enables it
- Delegates to convergence_loop for PLAN_REVIEW, IMPL_REVIEW, VAL_REVIEW
- Delegates to dag_scheduler for IMPLEMENT
- Records `package_authors` during IMPLEMENT for targeted fix dispatch
- Delegates to implementation_strategy_selector for per-package strategy
- Delegates to complexity_gate at INIT
- Writes handoff documents at each major transition
- Creates PR at SUBMIT_PR state
- ESCALATE: persists `previous_phase` and `escalation_reason`, writes diagnostic handoff, exits
- Resume: detects ESCALATE state on re-invocation, re-evaluates gate condition

**Acceptance**: Unit tests cover all state transitions, resumability (load from disk + continue), ESCALATE + resume, VAL_REVIEW skip/enable, vendor dropout mid-loop, and targeted fix dispatch.

---

### T6: Write SKILL.md prompt
**Priority**: 2 (depends on T5)
**Files**: `skills/auto-dev-loop/SKILL.md`

Skill prompt that:
- Accepts change-id (existing proposal) or feature description (creates proposal first)
- Accepts optional flags: `--force` (bypass complexity gate), `--val-review` (force VAL_REVIEW)
- Checks coordinator availability, degrades to linear workflow if unavailable
- Runs complexity gate, warns if above thresholds
- Invokes state machine conductor
- Provides progress updates at each state transition
- Handles resume: if loop-state.json exists, offers to continue from last checkpoint

---

### T7: Integration test
**Priority**: 3 (depends on T5-T6)
**Files**: `skills/auto-dev-loop/scripts/tests/test_integration.py`
**Marker**: `@pytest.mark.integration`

End-to-end test with mocked vendor CLIs:
- Creates a trivial feature proposal
- Runs the full loop with fake vendor responses that converge in 2 rounds
- Verifies: state transitions, finding trend, memory writes, handoff documents, PR creation
- Verifies: VAL_REVIEW is skipped for simple features
- Uses coordinator in-memory mode (no DB dependency)

**Acceptance**: Full loop completes without human intervention. All state transitions logged.
