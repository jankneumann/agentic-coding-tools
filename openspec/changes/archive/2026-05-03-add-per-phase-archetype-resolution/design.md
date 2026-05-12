# Design — Per-Phase Archetype Resolution in Autopilot

## Context

Autopilot's state machine has 15 phases; only 3 (`IMPLEMENT`, `IMPL_REVIEW`, `VALIDATE`) currently dispatch sub-agents via `_PHASE_TASKS`. The remaining phases are state transitions on the driver. Even the dispatched 3 phases all run on the harness's default model — there's no per-phase model selection, even though `agents_config.py:resolve_model` and `archetypes.yaml` already encode "which archetype is best for which kind of work."

This design wires the existing archetype catalog into all 13 non-terminal phases of the autopilot loop, with the coordinator as the authoritative source for phase→archetype mapping.

## Decisions

### D1: Phase mapping lives in `agent-coordinator/archetypes.yaml`

The existing `archetypes.yaml` schema gains a top-level `phase_mapping` section keyed by phase name:

```yaml
schema_version: 2  # bumped from 1
archetypes: { ... existing content unchanged ... }
phase_mapping:
  PLAN:           { archetype: architect, signals: [capabilities_touched] }
  PLAN_ITERATE:   { archetype: architect, signals: [capabilities_touched, iteration_count] }
  PLAN_REVIEW:    { archetype: reviewer, signals: [proposal_loc, capabilities_touched] }
  PLAN_FIX:       { archetype: architect, signals: [findings_severity, findings_count] }
  IMPLEMENT:      { archetype: implementer, signals: [loc_estimate, write_dirs, dependencies] }
  IMPL_ITERATE:   { archetype: implementer, signals: [iteration_count, write_dirs] }
  IMPL_REVIEW:    { archetype: reviewer, signals: [files_changed, lines_changed] }
  IMPL_FIX:       { archetype: implementer, signals: [findings_severity, findings_count] }
  VALIDATE:       { archetype: analyst, signals: [test_count, suite_duration] }
  VAL_REVIEW:     { archetype: reviewer, signals: [findings_severity] }
  VAL_FIX:        { archetype: implementer, signals: [findings_severity] }
  INIT:           { archetype: runner, signals: [] }
  SUBMIT_PR:      { archetype: runner, signals: [] }
```

**Why**: Single source of truth, additive extension (existing consumers ignore unknown sections). Schema bump from 1 → 2 is observed by `load_archetypes_config` and used to gate phase-mapping parsing.

**Alternatives rejected**: separate `phase_mapping.yaml` file (two-file maintenance burden); skills-side mapping (Approach 2, rejected at Gate 1).

### D2: New HTTP endpoint `POST /archetypes/resolve_for_phase`

```
POST /archetypes/resolve_for_phase
Headers: X-API-Key: <key>
Body:    {"phase": "PLAN", "signals": {"capabilities_touched": 3}}
Response 200:
  {
    "model": "opus",
    "system_prompt": "You are a software architect. ...",
    "archetype": "architect",
    "reasons": ["phase=PLAN maps to archetype=architect", "no escalation triggered"]
  }
Response 400: phase unknown or signals malformed
Response 404: phase has no mapping (fallback to harness default expected)
```

**Why**: Enables future skills (`iterate-on-plan`, `iterate-on-implementation`, `validate-feature`) to reuse the same resolution without duplicating mapping logic. Carries `reasons[]` for audit/debugging.

**Implementation**: Adds a handler in `agent-coordinator/src/coordination_api.py` that calls a new service-layer function `resolve_archetype_for_phase(phase, signals)` in `agents_config.py`.

### D3: `resolve_model` gains optional `phase` kwarg

```python
def resolve_model(
    archetype: ArchetypeConfig,
    package_metadata: dict[str, Any],
    *,
    return_reasons: bool = False,
    phase: str | None = None,  # NEW
) -> str | tuple[str, list[str]]:
```

When `phase` is provided AND the archetype has phase-specific escalation rules (future extension), apply them. For this proposal's scope, `phase` is recorded in reasons but doesn't change escalation behavior. The phase-mapping lookup itself happens in a new wrapper `resolve_archetype_for_phase(phase, signals)` — `resolve_model` is called by that wrapper.

**Why**: Keeps `resolve_model` signature backward-compatible; `phase` is purely additive metadata for now, with room to add phase-specific escalation thresholds in a follow-up proposal.

### D4: Skills-side client via `coordination_bridge.try_resolve_archetype_for_phase`

```python
# skills/coordination-bridge/scripts/coordination_bridge.py
def try_resolve_archetype_for_phase(
    phase: str,
    signals: dict[str, Any],
) -> dict[str, Any] | None:
    """Returns {model, system_prompt, archetype, reasons} or None on failure."""
```

Returns `None` on any failure (network, 4xx, 5xx, timeout). Caller decides fallback. Uses the existing `try_*` pattern in `coordination_bridge` (no new HTTP infrastructure).

**Why**: Consistent with the existing bridge pattern; failure-tolerant by design; testable via mock.

### D5: `_build_options` sets both `model` and `system_prompt`

```python
def _build_options(phase: str, state_dict: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if phase in _WORKTREE_PHASES:
        options["isolation"] = "worktree"

    # NEW: per-phase archetype resolution
    signals = _extract_signals_for_phase(phase, state_dict)
    override = _check_phase_model_override(phase)  # AUTOPILOT_PHASE_MODEL_OVERRIDE
    if override:
        options["model"] = override
        # No system_prompt with override (harness default applies)
    else:
        resolved = bridge.try_resolve_archetype_for_phase(phase, signals)
        if resolved:
            options["model"] = resolved["model"]
            options["system_prompt"] = resolved["system_prompt"]
            # phase_archetype recorded into state_dict for LoopState
            state_dict["_resolved_archetype"] = resolved["archetype"]
        # else: fallback to harness default — leave options as-is

    return options
```

**Why**: Implements full archetype semantics (persona + model). Override path skips system_prompt to keep operator overrides predictable.

### D6: `_PHASE_TASKS` extends to all 13 non-terminal phases

Currently has entries for `IMPLEMENT, IMPL_REVIEW, VALIDATE`. Extends to:

```
PLAN, PLAN_ITERATE, PLAN_REVIEW, PLAN_FIX,
IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, IMPL_FIX,
VALIDATE, VAL_REVIEW, VAL_FIX,
INIT, SUBMIT_PR
```

Each entry defines the task content (instructions to the sub-agent for that phase). For phases that don't exist as sub-agent dispatches today (PLAN, PLAN_ITERATE, etc.), the task content delegates to the existing skill (e.g., PLAN → `/plan-feature`). This means `_PHASE_TASKS` becomes the canonical "what does this phase do" registry.

**INIT and SUBMIT_PR caveat (see D13)**: These remain state-only on the driver; their `_PHASE_TASKS` entry is `None` (sentinel meaning "do not dispatch a sub-agent, but record the resolved archetype in `LoopState.phase_archetype` for audit").

**Why**: Uniform phase taxonomy — every phase that dispatches a sub-agent has a `_PHASE_TASKS` entry; every phase has a `phase_mapping` entry. No special cases.

### D7: `LoopState.phase_archetype` field; schema bump 2 → 3

```python
@dataclass
class LoopState:
    schema_version: int = 3  # bumped
    # ... existing fields ...
    phase_archetype: str | None = None  # NEW — name of the resolved archetype for the current phase
```

Persisted in `loop-state.json`; emitted in `POST /status/report` payload alongside `phase`.

**Migration**: Older `loop-state.json` files with `schema_version=2` are loaded with `phase_archetype=None`; first phase transition writes the resolved value. No destructive migration needed.

**Why**: Coordinator is the audit authority — recording which archetype was active at each phase enables observability dashboards, cost analysis, and (future) policy gates.

### D8: `AUTOPILOT_PHASE_MODEL_OVERRIDE` env var format

```
AUTOPILOT_PHASE_MODEL_OVERRIDE=PLAN=opus,IMPL_REVIEW=sonnet,VALIDATE=haiku
```

Parsed by `_parse_phase_model_override` in `phase_agent.py`. Format is `<phase>=<model>` pairs, comma-separated. Unknown phase names are warned and ignored. Unknown model names pass through (validated downstream by the harness).

**Precedence**: Override > resolved archetype > harness default. Override sets only `model`; `system_prompt` is left to the harness default to keep operator behavior predictable.

**Why**: Env var is sufficient for cloud-harness flow (where flags would need plumbing through autopilot driver). Comma-separated `key=value` pairs match existing patterns (e.g., `COORDINATION_API_KEYS`).

**Alternative rejected**: per-phase CLI flag (`--phase-model PLAN=opus`) — adds plumbing through autopilot driver and roadmap orchestrator without adding capability.

### D9: Failure mode — fallback chain

When the bridge call fails (D4 returns None):

1. **First attempt**: harness default. Phase dispatches with no `model` / `system_prompt` injection. `phase_archetype` recorded as `None`. Log a structured warning with the phase + error reason.
2. **No retry within phase dispatch**. The phase still runs, just without per-phase model selection. Autopilot continues.
3. **Operator visibility**: status report carries `phase_archetype: null`; downstream observability surfaces these as "default-fallback" phases. Operator can investigate and either fix coordinator availability or set `AUTOPILOT_PHASE_MODEL_OVERRIDE` as a temporary mitigation.

**Why**: Don't block autopilot progress on coordinator availability. Per-phase model selection is an optimization, not a correctness requirement; degrading gracefully preserves the existing behavior.

**Alternative rejected**: hard failure if bridge is unreachable — too brittle, especially in cloud-harness flows where coordinator may be slow but recoverable.

### D10: Coordination with `harness-engineering-features` via read-only lock

This change does not write to `convergence_loop.py`. We pre-register a coordinator file lock with `intent="read-only observation: per-phase archetype resolution proposal needs convergence_loop.py merge state visibility"` so:

- The other change's author sees we're tracking it
- We can detect when their PR merges (lock release event)
- A standard merge-queue conflict check before our PR ships

**Why**: Lock-based visibility is consistent with the project's existing coordinator-mediated coordination patterns. No actual exclusion needed since we don't write.

### D11: Default phase mapping (initial cut)

Captured in D1's YAML. Rationale per phase:

| Phase | Archetype | Why |
|---|---|---|
| `PLAN`, `PLAN_ITERATE`, `PLAN_FIX` | `architect` | Deep cross-cutting reasoning during proposal generation |
| `PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW` | `reviewer` | Adversarial code/spec review (Opus default) |
| `IMPLEMENT`, `IMPL_ITERATE`, `IMPL_FIX` | `implementer` | Routine code-writing with escalation on complex packages (existing behavior) |
| `VALIDATE`, `VAL_FIX` | `analyst` | Mechanical synthesis of test/CI output (Sonnet default) |
| `INIT`, `SUBMIT_PR` | `runner` | State transitions, no model thinking required |

These can be tuned via `archetypes.yaml` without code changes. The proposal ships these defaults; operators can override.

### D12: Signal extraction per phase

Each phase has a `signals: [...]` list in `phase_mapping` (D1). The skills-side `_extract_signals_for_phase(phase, state_dict)` reads only the listed signals from `state_dict`. Initial signal sources:

| Signal | Source |
|---|---|
| `capabilities_touched` | Length of `state_dict["capabilities"]` (PLAN-time) |
| `iteration_count` | `state_dict["plan_iteration"]` or `state_dict["impl_iteration"]` |
| `proposal_loc` | `wc -l` on `proposal.md` (PLAN_REVIEW) |
| `findings_severity`, `findings_count` | From last review payload (FIX phases) |
| `loc_estimate`, `write_dirs`, `dependencies` | Existing IMPLEMENT-phase signals from work-package metadata |
| `files_changed`, `lines_changed` | From git diff against base branch (IMPL_REVIEW) |
| `test_count`, `suite_duration` | From validate-feature output (VALIDATE) |

Missing signals are tolerated (resolve falls back to archetype default model). The endpoint validates only `phase` is known.

### D13: INIT and SUBMIT_PR remain state-only; archetype resolved for audit

INIT does setup (loops, registry init). SUBMIT_PR opens a PR via `gh pr create`. Neither does cognitive work that benefits from per-phase model selection. They keep their `_PHASE_TASKS` entry as `None` (sentinel: "no sub-agent"), but `_build_options` is still called so `LoopState.phase_archetype` records the resolved value (`runner`) for audit consistency.

**Why**: Avoids special-casing in `LoopState.phase_archetype` (every non-terminal phase has a value); avoids premature "promote these to sub-agent dispatches" decisions that would expand scope.

## Phase Architecture (visual)

```
+-----------------------+
| autopilot.py (driver) |
|  state machine loop   |
+----------+------------+
           |
           v
+----------+------------+
| make_phase_callback   |
|  for each phase       |
+----------+------------+
           |
           v
+----------+------------+
| run_phase_subagent    |
|  in phase_agent.py    |
+----------+------------+
           |
           v
+----------+------------+         +----------------------------+
| _build_options(phase) |-------->| coordination_bridge.       |
|  (NEW: signals, model,|  HTTP   | try_resolve_archetype_     |
|   system_prompt)      |  POST   | for_phase()                |
+----------+------------+         +-------------+--------------+
           |                                    |
           |                                    v
           v                       +------------+----------------+
+----------+------------+          | coordination_api.py         |
|  subagent_runner(     |          |  POST /archetypes/          |
|    prompt=...,        |          |  resolve_for_phase          |
|    options={          |          +-------------+---------------+
|      model: "opus",   |                        |
|      system_prompt:..,|                        v
|      isolation: ...   |          +-------------+---------------+
|    })                 |          | agents_config.py            |
+-----------------------+          |  resolve_archetype_         |
                                   |  for_phase(phase, signals)  |
                                   |   1. lookup phase_mapping   |
                                   |   2. load archetype         |
                                   |   3. resolve_model(         |
                                   |        archetype, signals)  |
                                   |   4. return {model,         |
                                   |        system_prompt, ...}  |
                                   +-----------------------------+
```

## Trade-offs Accepted

1. **One HTTP round-trip per phase dispatch** (~30-100ms in coordinated cloud-harness, <5ms locally). Mitigated by HTTP keep-alive in the bridge and by caching in `LoopState` for the duration of a phase.
2. **Coordinator becomes a hard dependency for optimal autopilot behavior** — but soft via D9 fallback (default model still works).
3. **Phase mapping schema in `archetypes.yaml`** — couples archetype catalog to autopilot phase taxonomy. Acceptable because (a) the catalog is the natural home for "which model does this work get," and (b) phase taxonomy changes are rare and warrant coordinated rollout anyway.
4. **`_PHASE_TASKS` extension to all 13 phases** — adds ~13 task templates. The PLAN/PLAN_ITERATE/PLAN_REVIEW templates are mostly delegations to existing skills (`/plan-feature`, `/iterate-on-plan`); their content is short.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Coordinator endpoint breaks autopilot if poorly tested | M | H | Require integration tests against live coordinator before merge; D9 fallback as defense in depth |
| `harness-engineering-features` lands first and changes `convergence_loop.py` semantics our `_PHASE_TASKS` extension assumes | M | M | D10 lock for visibility; rebase against main daily during plan→implement gap |
| Schema bump in `LoopState` breaks in-flight autopilot runs on older schema_version=2 | L | M | D7 graceful migration (None default); validate in coordinator handler |
| `system_prompt` injection at the harness layer is unsupported | M | H | Validate harness contract during implement-feature task 1.1 (contract test); fall back to model-only injection if unsupported |
