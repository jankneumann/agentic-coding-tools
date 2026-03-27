# Design: Automated Development Loop with Review Convergence

## Architecture Overview

The automated dev loop is a **conductor pattern** — a state machine that delegates work to existing skills and scripts, advancing through phases when convergence gates pass.

```
                    ┌──────────────────────────────────────────────────────┐
                    │              /auto-dev-loop (Conductor)               │
                    │                                                       │
                    │  ┌──────┐  ┌──────────┐  ┌───────────────┐          │
                    │  │ PLAN │→ │PLAN_REVIEW│→ │  PLAN_FIX     │          │
                    │  │      │  │  loop     │  │  (inline)     │          │
                    │  └──────┘  └──────────┘  └───────────────┘          │
                    │       │         ↑              │                     │
                    │       │         └──────────────┘                     │
                    │       ↓                                              │
                    │  ┌──────────┐  ┌──────────┐  ┌───────────┐         │
                    │  │IMPLEMENT │→ │IMPL_REVIEW│→ │ IMPL_FIX  │         │
                    │  │          │  │  loop     │  │(dispatched)│         │
                    │  └──────────┘  └──────────┘  └───────────┘         │
                    │       │              ↑             │                 │
                    │       │              └─────────────┘                 │
                    │       ↓                                              │
                    │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
                    │  │ VALIDATE │→ │VAL_REVIEW │→ │ VAL_FIX  │          │
                    │  │          │  │  loop     │  │(if needed)│          │
                    │  └──────────┘  └──────────┘  └──────────┘          │
                    │       │              ↑             │                 │
                    │       │              └─────────────┘                 │
                    │       ↓                                              │
                    │  ┌───────────┐  ┌──────────┐                        │
                    │  │ SUBMIT_PR │→ │   DONE   │                        │
                    │  │           │  │(await    │                        │
                    │  └───────────┘  │ approval)│                        │
                    │                  └──────────┘                        │
                    └──────────────────────────────────────────────────────┘
```

## Component Design

### 1. State Machine (`auto_dev_loop.py`)

The conductor is a deterministic state machine with serializable state.

#### States

| State | Entry Action | Exit Gate | Max Iter |
|-------|-------------|-----------|----------|
| `INIT` | Validate inputs, check coordinator, load handoff, run complexity gate | Always passes | 1 |
| `PLAN` | Delegate to `/parallel-plan-feature` or `/linear-plan-feature` to create proposal | Proposal artifacts exist | 1 |
| `PLAN_REVIEW` | Dispatch multi-vendor review of proposal artifacts | No medium+ findings in consensus with quorum met | 3 |
| `PLAN_FIX` | Apply fixes **inline** (conductor applies directly) | Fixes applied, artifacts re-validated | 1 per finding |
| `IMPLEMENT` | Execute work packages via DAG scheduler | All packages complete | 1 |
| `IMPL_REVIEW` | Dispatch multi-vendor review per package | No medium+ findings in any package consensus with quorum met | 3 |
| `IMPL_FIX` | Dispatch fixes to recorded lead vendor, scoped to package write_allow | Fixes applied, verification passes | 2 |
| `VALIDATE` | Run `/parallel-validate-feature` checks | Validation passes | 1 |
| `VAL_REVIEW` | *(optional)* Dispatch multi-vendor review of validation evidence | No medium+ findings in consensus with quorum met | 2 |
| `VAL_FIX` | Fix validation failures | Validation passes on retry | 2 |
| `SUBMIT_PR` | Create PR with full evidence trail | PR created | 1 |
| `DONE` | Write final handoff, update memory | Terminal | - |
| `ESCALATE` | Write diagnostic, pause for human | Human re-invokes and resolves | - |

#### State Transitions

```python
TRANSITIONS = {
    "INIT":         {"next": "PLAN"},
    "PLAN":         {"exists": "PLAN_REVIEW", "created": "PLAN_REVIEW", "failed": "ESCALATE"},
    "PLAN_REVIEW":  {"converged": "IMPLEMENT", "not_converged": "PLAN_FIX", "max_iter": "ESCALATE"},
    "PLAN_FIX":     {"fixed": "PLAN_REVIEW", "stuck": "ESCALATE"},
    "IMPLEMENT":    {"complete": "IMPL_REVIEW", "failed": "ESCALATE"},
    "IMPL_REVIEW":  {"converged": "VALIDATE", "not_converged": "IMPL_FIX", "max_iter": "ESCALATE"},
    "IMPL_FIX":     {"fixed": "IMPL_REVIEW", "stuck": "ESCALATE"},
    "VALIDATE":     {"passed": "VAL_REVIEW or SUBMIT_PR", "failed": "VAL_FIX"},
    # VAL_REVIEW is optional — enabled by complexity gate checkpoints or --val-review flag
    "VAL_REVIEW":   {"converged": "SUBMIT_PR", "not_converged": "VAL_FIX", "max_iter": "ESCALATE"},
    "VAL_FIX":      {"fixed": "VALIDATE", "stuck": "ESCALATE"},
    "SUBMIT_PR":    {"created": "DONE"},
    "ESCALATE":     {"resolved": "<previous_phase>", "abandoned": "DONE"},
}
```

#### ESCALATE Resolution Protocol

When the loop enters ESCALATE:
1. The system persists `previous_phase` and `escalation_reason` in `LoopState`
2. Writes a diagnostic handoff document with blocking findings and context
3. The system **exits** (returns control to the user)
4. The human investigates and resolves the issue (e.g., manually fixes the code, overrides a finding)
5. The human re-invokes `/auto-dev-loop <change-id>`
6. The system loads `loop-state.json`, detects `current_phase == "ESCALATE"`
7. Re-evaluates the escalation condition (re-runs the gate check for `previous_phase`)
8. If resolved → transitions to `previous_phase`; if not → remains in ESCALATE with updated diagnostic

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
    package_authors: dict[str, str]         # per-package: vendor that authored it
    implementation_strategy: dict[str, str] # per-package: "alternatives" | "lead_review"
    memory_ids: list[str]                   # coordinator memory IDs (episodic)
    handoff_ids: list[str]                  # handoff documents written
    started_at: str                         # ISO timestamp
    phase_started_at: str                   # ISO timestamp
    previous_phase: str | None              # set when entering ESCALATE
    escalation_reason: str | None           # diagnostic message
    error: str | None                       # last error if ESCALATE
```

**Dual-write persistence**:
1. **Primary**: Written to `openspec/changes/<change-id>/loop-state.json` after every state transition. This is the source of truth for resumability and is inspectable without running services.
2. **Secondary**: Key fields mirrored to coordinator memory via `remember()` for cross-agent visibility (e.g., merge queue conflict detection, multi-feature dashboarding). If coordinator write fails, the loop continues — file state is authoritative.

### 2. Convergence Loop Engine (`convergence_loop.py`)

A reusable engine parameterized by review type. Used in PLAN_REVIEW, IMPL_REVIEW, and VAL_REVIEW.

#### Cross-Skill Import Strategy

`convergence_loop.py` needs `ReviewOrchestrator` and `ConsensusSynthesizer` from `skills/parallel-implement-feature/scripts/`. Rather than duplicating code, the engine adds the dependency path to `sys.path` at import time:

```python
import sys
from pathlib import Path
# Add parallel-implement-feature scripts to import path
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "parallel-implement-feature" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
from review_dispatcher import ReviewOrchestrator, ReviewResult
from consensus_synthesizer import ConsensusSynthesizer, VendorResult
```

This matches the existing pattern used by other cross-skill scripts (e.g., `integration_orchestrator.py` imports from the same directory).

#### Algorithm

```python
def converge(review_type, artifacts, max_rounds=3, min_quorum=2):
    orchestrator = ReviewOrchestrator.from_agents_yaml(agents_path)
    trend = []

    for round in range(1, max_rounds + 1):
        # 1. Dispatch reviews via ReviewOrchestrator
        results: list[ReviewResult] = orchestrator.dispatch_and_wait(
            review_type=review_type,
            dispatch_mode="review",
            prompt=build_review_prompt(artifacts, round),
            cwd=worktree_path,
        )

        # 1b. Check quorum BEFORE evaluating findings
        successful = [r for r in results if r.success]
        if len(successful) < min_quorum:
            return ConvergenceResult(converged=False, reason="quorum_lost", rounds=round)

        # 2. Convert ReviewResult → VendorResult, then synthesize
        # ReviewResult.findings is a parsed JSON dict; extract into Finding objects
        vendor_results = []
        for r in successful:
            findings = [Finding(**f) for f in (r.findings or {}).get("findings", [])]
            vendor_results.append(VendorResult(vendor=r.vendor, findings=findings))

        synthesizer = ConsensusSynthesizer(quorum=min_quorum)
        consensus: ConsensusReport = synthesizer.synthesize(
            review_type=review_type,
            target=change_id,
            vendor_results=vendor_results,
        )

        # 3. Convert to dict for inspection
        report = consensus.to_dict()

        # 3a. Check for disagreement → immediate ESCALATE
        disagreements = [f for f in report["consensus_findings"]
                         if f["status"] == "disagreement"]
        if disagreements:
            return ConvergenceResult(converged=False, reason="disagreement",
                                     rounds=round, escalate_findings=disagreements)

        # 3b. Check exit condition (medium+ confirmed/unconfirmed)
        blocking = [f for f in report["consensus_findings"]
                    if f["agreed_criticality"] in ("medium", "high", "critical")
                    and f["status"] in ("confirmed", "unconfirmed")]

        # 3c. Relax unconfirmed in final round
        if round == max_rounds:
            blocking = [f for f in blocking if f["status"] != "unconfirmed"]

        if not blocking:
            return ConvergenceResult(converged=True, rounds=round, consensus=report)

        # 4. Check trend — escalate if findings not decreasing over 3 consecutive rounds
        trend.append(len(blocking))
        if len(trend) >= 3 and trend[-1] >= trend[-3]:
            return ConvergenceResult(converged=False, reason="stalled", rounds=round)

        # 5. Dispatch fixes (see Fix Dispatch section below)
        fix_results = dispatch_fixes(blocking, review_type, artifacts)

        # 6. Write episodic memory
        remember(
            event_type="convergence_round",
            summary=f"Round {round}: {len(blocking)} blocking findings",
            details={
                "change_id": change_id,
                "phase": review_type,
                "round": round,
                "findings_count": len(blocking),
                "fix_success_rate": fix_results.success_rate,
                "vendor_agreement": report["summary"]["confirmed_count"] /
                    max(report["summary"]["total_unique_findings"], 1),
            },
            tags=["convergence", change_id, review_type],
        )

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
| `unconfirmed` (1 vendor, medium+) | Yes, round 1..N-1; No, final round | Give benefit of doubt early; accept vendor disagreement eventually |
| `disagreement` | Escalate | Vendors disagree on fix — needs human judgment |

**Quorum gate**: Convergence CANNOT be declared unless `min_quorum` vendors returned valid results. If fewer than `min_quorum` succeed, the loop pauses with reason `quorum_lost`.

**Stall detection**: Uses a 3-point sliding window. If the finding count at round N is >= the count at round N-2, the trend is considered stalled. This gives the fix cycle room to handle churn (where fixes address old issues but surface new ones) while still catching genuine stalls.

#### Fix Dispatch

Fix dispatch differs by phase:

**PLAN_FIX (inline)**: The conductor applies plan fixes directly — it already has full context of the proposal artifacts. No CLI subprocess dispatch. The conductor reads the finding descriptions and resolutions, edits the relevant plan files (proposal.md, design.md, specs, work-packages.yaml), and re-validates with `openspec validate`.

**IMPL_FIX (targeted dispatch)**: Fixes are dispatched to the **recorded lead vendor** for the package (stored in `LoopState.package_authors`). The fix prompt includes:
1. Finding descriptions and resolutions
2. The original package scope (write_allow, read_allow)
3. The package's worktree path

Targeted dispatch uses `CliVendorAdapter.dispatch()` directly (not the orchestrator's broadcast `dispatch_and_wait()`). The adapter is looked up from `ReviewOrchestrator.adapters` by the vendor name stored in `package_authors`. This bypasses broadcast and sends the fix to exactly one vendor. Fix dispatch is scoped: the worktree is the package's isolated worktree, and post-fix verification checks that `files_modified ⊆ write_allow`.

**VAL_FIX (inline or targeted)**: Validation fixes are applied inline if they're configuration/test changes, or targeted to the relevant package's author if they require code changes.

### 3. Implementation Strategy Selector (`implementation_strategy_selector.py`)

Decides per work-package which implementation approach to use.

#### Input Data

The selector reads structured metadata from `work-packages.yaml`. Each package includes optional fields:

```yaml
metadata:
  loc_estimate: 150          # Estimated lines of code
  alternatives_count: 2       # Number of design alternatives noted
  package_kind: "algorithm"   # One of: algorithm, data_model, crud, config, migration, integration
```

If `metadata` is absent, the selector infers from the description (best-effort) or defaults to `lead_review`.

#### Decision Matrix

| Signal | Alternatives + Synthesis | Lead + Review |
|--------|--------------------------|---------------|
| `loc_estimate` | < 200 | >= 200 |
| `alternatives_count` | >= 2 | 0-1 |
| `package_kind` | algorithm, data_model | crud, config, migration |
| Available vendors | 3 available | < 3 available |

**Scoring**: Each criterion contributes a score (0-1). If total >= 2.0, use alternatives; otherwise lead+review.

#### Alternatives + Synthesis Flow

```
1. Dispatch package to all 3 vendors independently (alternative mode)
2. Each vendor produces implementation in its own worktree branch
3. Synthesis agent (Claude by default) reviews all 3, selects ONE as winner
4. Synthesis agent may make targeted edits to incorporate specific improvements from others
5. Review the synthesized result (convergence loop)
```

Note: Automated cherry-pick across divergent branches is unreliable. The synthesis agent selects a single winner and applies manual improvements, rather than attempting git cherry-pick.

#### Lead + Review Flow

```
1. Select lead vendor (Claude by default, or vendor with best recent success rate from memory)
2. Lead implements package in its worktree
3. Dispatch review to other vendors (convergence loop)
4. Lead applies fixes from review findings
5. Repeat until converged
```

The lead vendor is recorded in `LoopState.package_authors[package_id]` for targeted fix dispatch.

### 4. Memory Architecture

Memory uses the coordinator's **episodic memory** API (`remember(event_type, summary, details, tags)`), which returns `memory_id`. The state tracks `memory_ids` (not string keys) for reference.

#### Procedural Memory (per convergence round)

```python
remember(
    event_type="convergence_round",
    summary=f"automated-dev-loop plan round 2: 3 blocking findings",
    details={
        "change_id": "automated-dev-loop",
        "phase": "plan",
        "round": 2,
        "findings_count": 3,
        "top_finding_types": ["architecture", "security"],
        "vendor_agreement_rate": 0.75,
        "fix_success_rate": 1.0,
        "duration_seconds": 120
    },
    outcome="negative",
    lessons=["Architecture findings dominated this round"],
    tags=["convergence", "automated-dev-loop", "plan"]
)
```

#### Strategic Memory (at loop completion)

```python
remember(
    event_type="loop_completion",
    summary=f"automated-dev-loop completed in 7 rounds, fast convergence",
    details={
        "change_id": "automated-dev-loop",
        "total_rounds": 7,
        "implementation_strategy_used": {"wp-api": "lead_review", "wp-model": "alternatives"},
        "vendor_effectiveness": {
            "claude": {"findings_raised": 12, "findings_confirmed": 8, "fixes_authored": 15},
            "codex": {"findings_raised": 8, "findings_confirmed": 6, "fixes_authored": 0},
            "gemini": {"findings_raised": 10, "findings_confirmed": 7, "fixes_authored": 0}
        },
        "convergence_pattern": "fast"
    },
    outcome="positive",
    tags=["loop_completion", "automated-dev-loop"]
)
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

Before entering the loop, a complexity assessment determines if the feature is suitable for full automation.

#### Configurable Thresholds

Thresholds are read from `work-packages.yaml` defaults if present, falling back to built-in defaults:

```yaml
# In work-packages.yaml
defaults:
  auto_loop:
    max_loc: 500
    max_packages: 4
    max_external_deps: 2
    require_force_above: true
```

| Metric | Default Threshold | Above Threshold |
|--------|-------------------|-----------------|
| Total LOC estimate | 500 | Warn, require `--force` if `require_force_above` |
| Work packages | 4 | Warn, require `--force` |
| External dependencies | 2 (new packages) | Warn |
| Database migrations | 1 | Proceed but add manual review checkpoint |
| Security-sensitive paths | Any auth/crypto | Proceed but add manual review checkpoint |

Features above thresholds can still run the loop but get additional checkpoints injected.

### 6. PLAN Phase

When invoked with a feature description (not a change-id), the PLAN phase delegates to an existing planning skill:

- If coordinator is available: `/parallel-plan-feature <description>`
- If coordinator is unavailable: `/linear-plan-feature <description>`

The plan skill creates the proposal artifacts (proposal.md, design.md, specs, tasks.md, work-packages.yaml). Once created, the state machine transitions to PLAN_REVIEW for convergence.

If invoked with an existing change-id, the PLAN phase checks that artifacts exist and skips to PLAN_REVIEW.

### 7. PR Submission

The SUBMIT_PR state creates a pull request with full evidence:

```markdown
## Summary
[Auto-generated from proposal.md]

## Evidence Trail
- **Plan reviews**: 2 rounds, 3 vendors, 0 blocking findings
- **Implementation**: 2 packages (wp-api: lead+review, wp-model: alternatives)
- **Impl reviews**: 1 round, 3 vendors, 0 blocking findings
- **Validation**: Passed (unit: 42/42, integration: 8/8, lint: clean)
- **Validation review**: skipped (simple feature)
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

### E. Key-value memory API
**Rejected**: The coordinator provides episodic memory (event_type + summary + details + tags), not key-value. Using the episodic API with structured tags enables the same recall patterns (filter by change_id + phase) while staying compatible with the existing interface.

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
| `review_dispatcher.py` | Exists | Import via sys.path; use `ReviewOrchestrator` class |
| `consensus_synthesizer.py` | Exists | Import via sys.path; use `ConsensusSynthesizer` class |
| `integration_orchestrator.py` | Exists | No changes needed |
| `dag_scheduler.py` | Exists | No changes needed |
| `agents.yaml` | Exists | No changes needed |
| `work-packages.schema.json` | Exists | wp-schema adds optional `metadata` field to WorkPackage |
| `review-findings.schema.json` | Exists | No changes needed |
| `consensus-report.schema.json` | Exists | No changes needed |
| Coordinator MCP (memory, handoffs) | Exists | Use episodic `remember()` API, not key-value |
| `convergence-state.schema.json` | **New** | Must create |
