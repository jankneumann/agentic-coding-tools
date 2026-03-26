# Tasks: Automated Development Loop

## Task Dependencies

```
T1 (schema) ─────────────────────────────────┐
T2 (convergence engine) ──────┐              │
T3 (strategy selector) ──────┐│              │
T4 (complexity gate) ────────┐││             │
                             │││             │
T5 (state machine) ──────────┘┘┘             │
                             │               │
T6 (SKILL.md) ──────────────┘               │
                             │               │
T7 (tests) ─────────────────┘               │
                                             │
T8 (integration test) ──────────────────────┘
```

## Tasks

### T1: Create convergence-state schema
**Priority**: 1 (no dependencies)
**Files**: `openspec/schemas/convergence-state.schema.json`

Define JSON Schema for the serializable loop state that tracks phase, iteration, findings trend, vendor availability, and package status. Must support resumability — loading state from disk and continuing from the last checkpoint.

**Acceptance**: `openspec validate --strict` passes with new schema.

---

### T2: Implement convergence loop engine
**Priority**: 1 (no dependencies)
**Files**: `skills/auto-dev-loop/scripts/convergence_loop.py`

Reusable review-fix convergence engine:
- Accepts review_type, artifacts path, max_rounds, severity threshold
- Calls `review_dispatcher.dispatch_and_wait()` for multi-vendor review
- Calls `consensus_synthesizer.synthesize()` for finding reconciliation
- Implements exit condition: no blocking findings at configured severity
- Implements trend tracking: escalate if findings not decreasing over 2 rounds
- Implements fix dispatch: send findings to authoring agent in alternative mode
- Writes coordinator memory at each round
- Returns `ConvergenceResult` with converged flag, rounds count, consensus

**Acceptance**: Unit tests cover convergence (0 findings), non-convergence (max rounds), stall detection (flat trend), and vendor unavailability (reduced quorum).

---

### T3: Implement implementation strategy selector
**Priority**: 1 (no dependencies)
**Files**: `skills/auto-dev-loop/scripts/implementation_strategy_selector.py`

Per-package decision logic:
- Input: work-packages.yaml, design.md, vendor availability
- Output: dict mapping package_id to "alternatives" | "lead_review"
- Scoring: LOC estimate (<200 = alternatives), design alternatives count, package type, vendor count
- Threshold: score >= 2.0 → alternatives, else lead_review
- Recalls vendor effectiveness from coordinator memory to bias lead selection

**Acceptance**: Unit tests cover all scoring branches, boundary cases, and fallback when memory unavailable.

---

### T4: Implement complexity gate
**Priority**: 1 (no dependencies)
**Files**: `skills/auto-dev-loop/scripts/complexity_gate.py`

Entry assessment that determines if a feature is suitable for full automation:
- Input: proposal.md, work-packages.yaml, tasks.md
- Output: `GateResult` with `allowed: bool`, `warnings: list`, `checkpoints: list`
- Thresholds: LOC > 500, packages > 4, external deps > 2, db migrations, security paths
- Above threshold: warn + require `--force`, or inject manual review checkpoints

**Acceptance**: Unit tests cover each threshold independently and in combination.

---

### T5: Implement state machine conductor
**Priority**: 2 (depends on T1-T4)
**Files**: `skills/auto-dev-loop/scripts/auto_dev_loop.py`

The main conductor:
- Loads/saves `LoopState` from `loop-state.json`
- Implements state transition table with all 10 states
- Delegates to convergence_loop for PLAN_REVIEW, IMPL_REVIEW
- Delegates to dag_scheduler for IMPLEMENT
- Delegates to implementation_strategy_selector for per-package strategy
- Delegates to complexity_gate at INIT
- Writes handoff documents at each major transition
- Creates PR at SUBMIT_PR state
- Handles ESCALATE: writes diagnostic handoff, pauses for human input

**Acceptance**: Unit tests cover all state transitions, resumability (load from disk + continue), escalation paths, and vendor dropout mid-loop.

---

### T6: Write SKILL.md prompt
**Priority**: 2 (depends on T5)
**Files**: `skills/auto-dev-loop/SKILL.md`

Skill prompt that:
- Accepts change-id (existing proposal) or feature description (creates proposal first)
- Checks coordinator availability, degrades to linear workflow if unavailable
- Runs complexity gate, warns if above thresholds
- Invokes state machine conductor
- Provides progress updates at each state transition
- Handles resume: if loop-state.json exists, offers to continue from last checkpoint

---

### T7: Unit tests
**Priority**: 2 (depends on T2-T5)
**Files**: `skills/auto-dev-loop/scripts/tests/test_*.py`

Comprehensive unit tests for all four scripts:
- `test_convergence_loop.py`: convergence, non-convergence, stall, quorum, memory writes
- `test_implementation_strategy_selector.py`: scoring, boundaries, memory recall
- `test_complexity_gate.py`: thresholds, checkpoints, combinations
- `test_auto_dev_loop.py`: state transitions, serialization, resume, escalation

All tests must mock external dependencies (reviewer dispatch, coordinator, git operations).

**Acceptance**: >= 90% line coverage on all scripts. All tests pass.

---

### T8: Integration test
**Priority**: 3 (depends on T5-T7)
**Files**: `skills/auto-dev-loop/scripts/tests/test_integration.py`
**Marker**: `@pytest.mark.integration`

End-to-end test with mocked vendor CLIs:
- Creates a trivial feature proposal
- Runs the full loop with fake vendor responses that converge in 2 rounds
- Verifies: state transitions, finding trend, memory writes, handoff documents, PR creation
- Uses coordinator in-memory mode (no DB dependency)

**Acceptance**: Full loop completes without human intervention. All state transitions logged.
