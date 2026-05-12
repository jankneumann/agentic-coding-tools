# Per-Phase Archetype Resolution in Autopilot

## Why

Autopilot today dispatches every sub-agent with the same harness-default model. The archetype catalog at `agent-coordinator/archetypes.yaml` already knows how to map work to an appropriate persona+model (architect → Opus, implementer → Sonnet w/ escalation, runner → Haiku, etc.), and `agent-coordinator/src/agents_config.py:resolve_model` returns the right model for a given archetype + signals. But `skills/autopilot/scripts/phase_agent.py:_build_options` only sets `isolation`, never `model` or `system_prompt`. Per-task model selection works only inside `IMPLEMENT` (via the work-package archetype field on individual packages); every other autopilot phase silently inherits the harness default.

This means we cannot:

- Run **PLAN** under Opus to get deeper architectural reasoning, while keeping **VALIDATE** on Haiku for cost-efficient mechanical checks.
- Apply the **reviewer** archetype's persona to `IMPL_REVIEW` and `PLAN_REVIEW` even though the catalog defines exactly that role.
- Audit which archetype was active at each phase boundary (the coordinator records the phase but not the resolved archetype).

The user's intent is to take advantage of model heterogeneity across the autopilot lifecycle: Opus where deep planning matters, Sonnet for routine implementation, Haiku for mechanical runs. The archetype system was built for this — it just isn't wired into the autopilot phase loop.

## What Changes

This change wires the existing archetype catalog into the autopilot state machine so every non-terminal phase resolves an archetype and dispatches its sub-agent with the resolved `model` + `system_prompt`.

### High-level deltas

1. **New coordinator HTTP endpoint** — `POST /archetypes/resolve_for_phase` returns `{model, system_prompt, archetype, reasons[]}` for a given phase and signal dict. Implemented in `agent-coordinator/src/coordination_api.py`.

2. **Extended `archetypes.yaml`** — adds a `phase_mapping` section (phase name → archetype name) that covers all 13 non-terminal phases. Phases: `INIT, PLAN, PLAN_ITERATE, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW, VAL_FIX, SUBMIT_PR`.

3. **Extended `resolve_model`** — accepts an optional `phase` kwarg; when present, resolves the archetype via `phase_mapping` before applying escalation logic. Reasons returned to the client include the phase that drove the choice.

4. **Skills-side client** — `coordination_bridge` gains `try_resolve_archetype_for_phase(phase, signals)`. `phase_agent.py:_build_options` calls it and sets both `options["model"]` and `options["system_prompt"]`.

5. **Extended `_PHASE_TASKS`** — currently has entries only for `IMPLEMENT, IMPL_REVIEW, VALIDATE`. Extends to cover all 13 non-terminal phases with appropriate task templates so every phase dispatches via `subagent_runner` (today most phases are pure state transitions on the driver and never call `_build_options`).

6. **`LoopState.phase_archetype`** — new optional field carrying the resolved archetype name; emitted in `POST /status/report` for audit/observability. Schema bump: `LoopState.schema_version` → 3.

7. **CLI override mechanism** — `AUTOPILOT_PHASE_MODEL_OVERRIDE` env var (e.g., `PLAN=opus,IMPL_REVIEW=sonnet`) lets operators force a model per phase for testing/cost control. Override takes precedence over archetype resolution.

8. **Spec updates (3 specs MODIFIED)**:
   - `agent-archetypes` — add per-phase mapping requirement
   - `skill-workflow` — add "Per-Phase Archetype Resolution" requirement under Autopilot Skill
   - `agent-coordinator` — add `phase_archetype` field to `LoopState` schema and status-report payload

9. **Tests** — new `skills/tests/autopilot/` directory with phase-resolution tests; coordinator-side tests for the new endpoint.

### Coordination with `harness-engineering-features`

That change touches `skills/autopilot/scripts/convergence_loop.py` (Tasks 2.1/2.2). This proposal scopes its writes to `phase_agent.py`, `archetypes.yaml`, `agents_config.py`, `coordination_api.py`, `coordination_bridge`, and `autopilot.py` (only for `_PHASE_TASKS` extension and `LoopState.phase_archetype` field). It does **not** modify `convergence_loop.py`. We will pre-register a coordinator file lock on `convergence_loop.py` with `intent="read-only observation"` so the conflict is visible to both authors, and check daily for merge-window opportunities.

### Out of scope

- Changing default model assignments in existing archetypes (those are policy decisions for a separate proposal)
- Adding new archetypes beyond the 6 already in `archetypes.yaml`
- Changing how IMPLEMENT-phase work packages resolve archetypes for individual packages (that already works correctly via `resolve_model` + package metadata)
- Vendor-routing changes (i.e., which API provider serves which model — handled by the agent-dispatch layer)

## Approaches Considered

Three approaches were considered. They differ on **where the phase→archetype mapping lives** and **how much of the resolution logic the coordinator owns**.

### Approach 1: Coordinator-owned phase mapping (Recommended)

**Description**: All policy in `agent-coordinator/archetypes.yaml` (extended with a `phase_mapping` section). Coordinator endpoint takes `phase + signals`, returns `{model, system_prompt, archetype, reasons[]}`. Skills are pure clients of this API.

**Pros**:
- Single source of truth — phase→archetype mapping lives next to archetype definitions
- Coordinator can apply cross-cutting policy decisions (cost ceilings, vendor allowlists) to phase mappings centrally
- Future skills (e.g., `iterate-on-plan`, `iterate-on-implementation`) can reuse the same endpoint without duplicating phase logic
- The `phase_archetype` field in `LoopState` has obvious authoritative source (the coordinator)

**Cons**:
- Largest coordinator changes: new endpoint, new schema section in `archetypes.yaml`, new test surface
- Couples skill evolution to coordinator schema evolution (phase enum changes need coordinated rollout)
- Higher latency per phase dispatch (one HTTP round-trip; mitigated by HTTP keep-alive in the bridge)

**Effort**: L (estimated ~500-650 LOC across coordinator + skills + tests)

### Approach 2: Skills-owned phase mapping, thin coordinator API

**Description**: Phase mapping lives in `skills/autopilot/scripts/phase_archetypes.yaml`. Coordinator endpoint stays minimal: `POST /archetypes/resolve` takes `{archetype: str, signals: dict}` (no phase concept), returns `{model, system_prompt}`. The skills client maps `phase → archetype` locally before calling resolve.

**Pros**:
- Smaller coordinator API surface — `/archetypes/resolve` is genuinely stateless and reusable beyond autopilot
- Phase mapping evolves with the autopilot skill; can be edited and tested without coordinator deploy
- Lower risk of merge conflict with `harness-engineering-features` (most edits are skills-side)
- Coordinator's `archetypes.yaml` stays focused on archetype definitions, not phase mapping

**Cons**:
- Phase concept is duplicated if other skills later want phase-aware resolution (e.g., `iterate-on-plan` would re-implement the mapping)
- `LoopState.phase_archetype` has weaker provenance — the coordinator records what the skill claimed, not what the coordinator resolved
- Two configs to keep in sync (coordinator's archetype catalog + skills's phase mapping)

**Effort**: M (estimated ~350-450 LOC, lighter on coordinator side)

### Approach 3: Phase as a signal field in `resolve_model`

**Description**: Treat `phase` as just another signal in the existing escalation mechanism — `resolve_model` accepts `signals = {phase: str, loc_estimate: int, ...}`, and `ArchetypeConfig` gains an optional `phase_overrides: {phase: alternate_archetype}` field. No new endpoint; reuse the existing `resolve_model` path. The skills-side client looks up the archetype from a hardcoded default (e.g., `"implementer"`) and lets `phase_overrides` redirect to a different archetype based on phase signal.

**Pros**:
- Reuses the existing escalation mechanism (less new infrastructure)
- Phase becomes orthogonal to archetype — both can evolve independently
- `resolve_model` keeps a single signal abstraction (no special-case for phase)

**Cons**:
- "Phase" muddies the `resolve_model` signal abstraction, which was originally about *package* metadata (LOC, write_dirs, dependencies). Phase is fundamentally different — it's a state-machine position, not package complexity
- `phase_overrides` produces awkward archetype-centric mappings ("if phase=PLAN and archetype=implementer, use architect instead") — inverted from natural "phase X uses archetype Y" reading
- Doesn't expose `system_prompt` cleanly without further refactoring (the existing `resolve_model` only returns a model string)
- Inconsistent with the user's stated preference for HTTP-via-bridge as the import path

**Effort**: M (estimated ~300-400 LOC, but with higher refactor risk in `resolve_model`)

## Selected Approach

**Approach 1 — Coordinator-owned phase mapping** was selected at Gate 1 (no modifications requested).

The detailed rationale is preserved below; Approaches 2 and 3 are retained for context but will not be implemented.

## Recommended Approach (rationale for selection)

**Approach 1 (Coordinator-owned phase mapping)** is recommended.

Rationale:

1. **The user explicitly chose HTTP via coordination_bridge** as the import path. Approach 1 makes the HTTP API meaningful (carries phase semantics, not just archetype + signals) — Approach 2 reduces the API to a thin shim where most of the value still lives in skills, and Approach 3 doesn't require an HTTP endpoint at all (which contradicts the import-path choice).

2. **The user explicitly chose all 13 non-terminal phases**. Approach 1 makes the coordinator the authoritative source for "what does each phase use" — if we later want to apply policy (cost caps, model deprecation rollouts, vendor failover) to specific phases, having the mapping coordinator-side is the only approach that makes that natural.

3. **`LoopState.phase_archetype` provenance**. The coordinator already records `phase` transitions; recording the resolved archetype alongside it (rather than trusting the skill's self-report) is consistent with the coordinator's role as audit authority.

4. **Reuse beyond autopilot**. Other skills already in the workflow (`iterate-on-plan`, `iterate-on-implementation`, `validate-feature`) could benefit from per-phase archetype resolution. A coordinator-owned API serves all of them; a skills-owned mapping forces each to maintain its own.

The trade-off accepted is the higher coordinator-side surface area and one HTTP round-trip per phase dispatch. The latter is mitigated by HTTP keep-alive in the existing `coordination_bridge` and by caching the resolved value in `LoopState` for the duration of the phase. The former is mitigated by the fact that the new endpoint is small and the schema extension to `archetypes.yaml` is additive (existing consumers ignore unknown sections).

## Open Questions for Plan Refinement

These will be settled during `/iterate-on-plan` if not earlier:

1. **Default phase mapping**. Initial proposal: `PLAN/PLAN_ITERATE/PLAN_FIX → architect`, `IMPLEMENT/IMPL_FIX → implementer`, `IMPL_REVIEW/PLAN_REVIEW/VAL_REVIEW → reviewer`, `VALIDATE/VAL_FIX → analyst`, `INIT/SUBMIT_PR → runner`, `IMPL_ITERATE → implementer`. Is this the right starting point, or should some phases map differently?

2. **Signal extraction per phase**. For non-IMPLEMENT phases, what signals make sense for escalation? PLAN: number of capabilities touched? IMPL_REVIEW: number of files changed in the PR under review? VALIDATE: count of test failures? Each phase needs a signal extractor.

3. **Override syntax**. Proposed `AUTOPILOT_PHASE_MODEL_OVERRIDE=PLAN=opus,IMPL_REVIEW=sonnet`. Should there also be a per-phase CLI flag (e.g., `--phase-model PLAN=opus`)? Env var alone may be enough for the coordinated cloud-harness flow.

4. **Sub-agent dispatch for state-only phases**. `INIT` and `SUBMIT_PR` are mostly state transitions today, not sub-agent work. Should they actually dispatch a sub-agent (with a `runner` archetype) so they have a uniform `_PHASE_TASKS` story, or should they remain pure state transitions and only resolve an archetype for audit purposes?

5. **Failure mode**. If `coordination_bridge.try_resolve_archetype_for_phase` fails (network error, coordinator unreachable, malformed response), what's the fallback? Hardcoded harness default? Last successful resolution from `LoopState`? Skip archetype injection for that phase and proceed with harness default?

These will be addressed in `design.md` and reflected in the spec deltas before Gate 2.
