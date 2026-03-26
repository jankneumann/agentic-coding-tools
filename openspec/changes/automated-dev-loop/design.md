# Design: Automated Development Loop with Review Convergence

## Architecture Overview

The automated dev loop is a **conductor pattern** — a state machine that delegates work to existing skills and scripts, advancing through phases when convergence gates pass.

```
                    ┌─────────────────────────────────────────────┐
                    │           /auto-dev-loop (Conductor)         │
                    │                                              │
                    │  ┌──────┐  ┌──────────┐  ┌───────────────┐ │
                    │  │ PLAN │→ │PLAN_REVIEW│→ │  PLAN_FIX     │ │
                    │  │      │  │  loop     │  │  (if needed)  │ │
                    │  └──────┘  └──────────┘  └───────────────┘ │
                    │       │         ↑              │            │
                    │       │         └──────────────┘            │
                    │       ↓                                     │
                    │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
                    │  │IMPLEMENT │→ │IMPL_REVIEW│→ │ IMPL_FIX  │ │
                    │  │          │  │  loop     │  │(if needed)│ │
                    │  └──────────┘  └──────────┘  └───────────┘ │
                    │       │              ↑             │        │
                    │       │              └─────────────┘        │
                    │       ↓                                     │
                    │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
                    │  │ VALIDATE │→ │ VAL_FIX  │→ │ SUBMIT_PR │ │
                    │  │          │  │(if needed)│  │           │ │
                    │  └──────────┘  └──────────┘  └───────────┘ │
                    │                                    │        │
                    │                                    ↓        │
                    │                              ┌──────────┐  │
                    │                              │   DONE    │  │
                    │                              │(await     │  │
                    │                              │ approval) │  │
                    │                              └──────────┘  │
                    └─────────────────────────────────────────────┘
```

## Component Design

### 1. State Machine (`auto_dev_loop.py`)

The conductor is a deterministic state machine with serializable state.

#### States

| State | Entry Action | Exit Gate | Max Iter |
|-------|-------------|-----------|----------|
| `INIT` | Validate inputs, check coordinator, load handoff | Always passes | 1 |
| `PLAN_REVIEW` | Dispatch multi-vendor review of proposal artifacts | No medium+ findings in consensus | 3 |
| `PLAN_FIX` | Apply fixes from review findings, re-validate artifacts | Fixes applied, artifacts valid | 1 per finding |
| `IMPLEMENT` | Execute work packages via DAG scheduler | All packages complete | 1 |
| `IMPL_REVIEW` | Dispatch multi-vendor review per package | No medium+ findings in any package consensus | 3 |
| `IMPL_FIX` | Apply fixes, re-run package verification | Fixes applied, verification passes | 2 |
| `VALIDATE` | Run `/parallel-validate-feature` checks | Validation passes | 1 |
| `VAL_FIX` | Fix validation failures | Validation passes on retry | 2 |
| `SUBMIT_PR` | Create PR with full evidence trail | PR created | 1 |
| `DONE` | Write final handoff, update memory | Terminal | - |

#### State Transitions

```python
TRANSITIONS = {
    "INIT":         {"next": "PLAN_REVIEW"},
    "PLAN_REVIEW":  {"converged": "IMPLEMENT", "not_converged": "PLAN_FIX", "max_iter": "ESCALATE"},
    "PLAN_FIX":     {"fixed": "PLAN_REVIEW", "stuck": "ESCALATE"},
    "IMPLEMENT":    {"complete": "IMPL_REVIEW", "failed": "ESCALATE"},
    "IMPL_REVIEW":  {"converged": "VALIDATE", "not_converged": "IMPL_FIX", "max_iter": "ESCALATE"},
    "IMPL_FIX":     {"fixed": "IMPL_REVIEW", "stuck": "ESCALATE"},
    "VALIDATE":     {"passed": "SUBMIT_PR", "failed": "VAL_FIX"},
    "VAL_FIX":      {"fixed": "VALIDATE", "stuck": "ESCALATE"},
    "SUBMIT_PR":    {"created": "DONE"},
    "ESCALATE":     {"resolved": "<previous_state>", "abandoned": "DONE"},
}
```

#### Serializable State

```python
@dataclass
class LoopState:
    change_id: str
    current_phase: str
    iteration: int                          # within current phase
    total_iterations: int                   # across all phases
    max_phase_iterations: int               # cap per phase (default 3)
    findings_trend: list[int]               # findings count per review round
    blocking_findings: list[dict]           # current blockers
    vendor_availability: dict[str, bool]    # live vendor status
    packages_status: dict[str, str]         # per-package completion
    implementation_strategy: dict[str, str] # per-package: "alternatives" | "lead_review"
    memory_keys: list[str]                  # coordinator memory keys written
    handoff_ids: list[str]                  # handoff documents written
    started_at: str                         # ISO timestamp
    phase_started_at: str                   # ISO timestamp
    error: str | None                       # last error if ESCALATE
```

**Dual-write persistence**:
1. **Primary**: Written to `openspec/changes/<change-id>/loop-state.json` after every state transition. This is the source of truth for resumability and is inspectable without running services.
2. **Secondary**: Key fields mirrored to coordinator memory via `remember()` for cross-agent visibility (e.g., merge queue conflict detection, multi-feature dashboarding). If coordinator write fails, the loop continues — file state is authoritative.

### 2. Convergence Loop Engine (`convergence_loop.py`)

A reusable engine parameterized by review type. Used in PLAN_REVIEW, IMPL_REVIEW, and VAL_FIX.

#### Algorithm

```
function converge(review_type, artifacts, max_rounds=3):
    for round in 1..max_rounds:
        # 1. Dispatch reviews
        results = review_dispatcher.dispatch_and_wait(
            review_type=review_type,
            prompt=build_review_prompt(artifacts, round),
            output_dir=artifacts_dir / "reviews" / f"round-{round}"
        )

        # 2. Synthesize consensus
        consensus = consensus_synthesizer.synthesize(
            findings=[r.findings for r in results if r.success],
            review_type=review_type
        )

        # 3. Check exit condition
        blocking = [f for f in consensus.findings
                    if f.agreed_criticality in ("medium", "high", "critical")
                    and f.status in ("confirmed", "unconfirmed")]

        if not blocking:
            return ConvergenceResult(converged=True, rounds=round, consensus=consensus)

        # 4. Check trend — escalate if findings not decreasing
        trend.append(len(blocking))
        if len(trend) >= 2 and trend[-1] >= trend[-2]:
            return ConvergenceResult(converged=False, reason="stalled", rounds=round)

        # 5. Dispatch fixes
        fix_results = dispatch_fixes(blocking, review_type, artifacts)

        # 6. Write memory — what was found and fixed
        remember(f"convergence-{change_id}-round-{round}", {
            "findings_count": len(blocking),
            "fix_success_rate": fix_results.success_rate,
            "vendor_agreement": consensus.summary.confirmed_count / consensus.summary.total
        })

    return ConvergenceResult(converged=False, reason="max_rounds", rounds=max_rounds)
```

#### Convergence Exit Criteria

The exit condition is **severity-gated**:

| Severity | Action |
|----------|--------|
| `critical` | Must fix. Blocks convergence. |
| `high` | Must fix. Blocks convergence. |
| `medium` | Must fix. Blocks convergence. |
| `low` | Logged but does not block. |

Additionally, **finding status** affects blocking:

| Status | Blocking? | Rationale |
|--------|-----------|-----------|
| `confirmed` (2+ vendors) | Yes | High confidence issue |
| `unconfirmed` (1 vendor, medium+) | Yes, round 1-2; No, round 3 | Give benefit of doubt early; accept vendor disagreement eventually |
| `disagreement` | Escalate | Vendors disagree on fix — needs human judgment |

#### Fix Dispatch

Fixes are dispatched to the **authoring agent** (the vendor that created the artifact):

1. Build fix prompt from finding descriptions + resolutions
2. Include the original artifact + review context
3. Dispatch in `alternative` mode (write access)
4. Validate the fix doesn't introduce regressions (run verification)

### 3. Implementation Strategy Selector (`implementation_strategy_selector.py`)

Decides per work-package which implementation approach to use.

#### Decision Matrix

| Signal | Alternatives + Synthesis | Lead + Review |
|--------|--------------------------|---------------|
| Package LOC estimate | < 200 LOC | >= 200 LOC |
| Design alternatives in `design.md` | >= 2 noted | 0-1 noted |
| Package type | Algorithm, data model | CRUD, config, migration |
| Available vendors | 3 available | < 3 available |

**Scoring**: Each criterion contributes a score (0-1). If total >= 2.0, use alternatives; otherwise lead+review.

#### Alternatives + Synthesis Flow

```
1. Dispatch package to all 3 vendors independently (alternative mode)
2. Each vendor produces implementation in its own worktree branch
3. Synthesis agent (Claude by default) reviews all 3, picks best approach
4. Merge selected implementation, cherry-pick individual improvements from others
5. Review the synthesized result (convergence loop)
```

#### Lead + Review Flow

```
1. Select lead vendor (Claude by default, or vendor with best recent success rate from memory)
2. Lead implements package in its worktree
3. Dispatch review to other vendors (convergence loop)
4. Lead applies fixes from review findings
5. Repeat until converged
```

### 4. Memory Architecture

Three categories of memory are written during the loop:

#### Procedural Memory (coordinator `remember()`)

Written at each convergence round:
```json
{
  "key": "convergence:automated-dev-loop:plan:round-2",
  "value": {
    "findings_count": 3,
    "top_finding_types": ["architecture", "security"],
    "vendor_agreement_rate": 0.75,
    "fix_success_rate": 1.0,
    "duration_seconds": 120
  }
}
```

#### Strategic Memory (coordinator `remember()`)

Written at loop completion:
```json
{
  "key": "strategy:automated-dev-loop:summary",
  "value": {
    "total_rounds": 7,
    "implementation_strategy_used": {"wp-api": "lead_review", "wp-model": "alternatives"},
    "vendor_effectiveness": {
      "claude": {"findings_raised": 12, "findings_confirmed": 8, "fixes_authored": 15},
      "codex": {"findings_raised": 8, "findings_confirmed": 6, "fixes_authored": 0},
      "gemini": {"findings_raised": 10, "findings_confirmed": 7, "fixes_authored": 0}
    },
    "convergence_pattern": "fast"  // or "slow", "stalled"
  }
}
```

#### Handoff Documents (coordinator `write_handoff()`)

Written at each major state transition:
```json
{
  "from_phase": "PLAN_REVIEW",
  "to_phase": "IMPLEMENT",
  "summary": "Plan converged after 2 rounds. Key decisions: ...",
  "blocking_resolved": ["F-003: added rate limiting", "F-007: fixed schema migration order"],
  "context_for_next_phase": {
    "critical_constraints": ["must use async handlers for /api/events"],
    "vendor_notes": "Codex flagged thread safety in round 1; confirmed by Claude in round 2"
  }
}
```

### 5. Complexity Gate

Before entering the loop, a complexity assessment determines if the feature is suitable for full automation:

| Metric | Threshold | Above Threshold |
|--------|-----------|-----------------|
| Total LOC estimate | 500 | Warn, require explicit `--force` |
| Work packages | 4 | Warn, require explicit `--force` |
| External dependencies | 2 (new packages) | Warn |
| Database migrations | 1 | Proceed but add manual review checkpoint |
| Security-sensitive paths | Any auth/crypto | Proceed but add manual review checkpoint |

Features above thresholds can still run the loop but get additional checkpoints injected.

### 6. PR Submission

The SUBMIT_PR state creates a pull request with full evidence:

```markdown
## Summary
[Auto-generated from proposal.md]

## Evidence Trail
- **Plan reviews**: 2 rounds, 3 vendors, 0 blocking findings
- **Implementation**: 2 packages (wp-api: lead+review, wp-model: alternatives)
- **Impl reviews**: 1 round, 3 vendors, 0 blocking findings
- **Validation**: Passed (unit: 42/42, integration: 8/8, lint: clean)
- **Total convergence rounds**: 5
- **Total duration**: 18m 32s

## Convergence Report
[Link to convergence-state.json]

## Review Consensus
[Links to consensus reports per phase]

Generated by `/auto-dev-loop` — awaiting human approval for merge.
```

## Alternatives Considered

### A. No automation — manual skill invocation
**Rejected**: This is the current state. Works but slow for simple features.

### B. GitHub Actions orchestration (external)
**Rejected**: Would lose coordinator memory/handoff integration. CLI subprocess dispatch from within Claude Code is more flexible and already proven with MVRO.

### C. Single convergence loop (no per-phase loops)
**Rejected**: Plan issues caught early are cheaper to fix than implementation issues. Per-phase convergence prevents wasted implementation effort on a flawed plan.

### D. Fixed vendor roles (Claude=author, others=reviewers always)
**Rejected**: The implementation strategy selector allows dynamic role assignment based on package characteristics and vendor capacity. This is more resilient and produces better results for small algorithmic packages.

## File Layout

```
skills/
  auto-dev-loop/
    SKILL.md                              # Skill prompt for conductor
    scripts/
      auto_dev_loop.py                    # State machine conductor
      convergence_loop.py                 # Reusable review-fix loop engine
      implementation_strategy_selector.py  # Per-package strategy decision
      complexity_gate.py                  # Entry complexity assessment
      tests/
        test_auto_dev_loop.py
        test_convergence_loop.py
        test_implementation_strategy_selector.py
        test_complexity_gate.py
openspec/
  schemas/
    convergence-state.schema.json         # Loop state schema
```

## Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| `review_dispatcher.py` | Exists | No changes needed |
| `consensus_synthesizer.py` | Exists | No changes needed |
| `integration_orchestrator.py` | Exists | No changes needed |
| `dag_scheduler.py` | Exists | No changes needed |
| `agents.yaml` | Exists | No changes needed |
| `work-packages.schema.json` | Exists | No changes needed |
| `review-findings.schema.json` | Exists | No changes needed |
| `consensus-report.schema.json` | Exists | No changes needed |
| Coordinator MCP (memory, handoffs) | Exists | No changes needed |
| `convergence-state.schema.json` | **New** | Must create |
