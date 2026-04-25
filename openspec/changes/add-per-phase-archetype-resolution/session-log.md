# Session Log — add-per-phase-archetype-resolution

---

## Phase: Plan (2026-04-25)

**Agent**: claude_code (Opus 4.7) | **Session**: N/A (local-profile coordinator)

### Decisions

1. **Coordinator-owned phase mapping (Approach 1)** — Selected at Gate 1 over skills-owned mapping (Approach 2) and phase-as-signal (Approach 3). Rationale: coherence with discovery answers (HTTP-via-bridge import path + all-13-phases scope + model+system_prompt persona). Approaches 2 and 3 each contradict at least one earlier decision.

2. **HTTP via coordination_bridge as the import path** — `skills/autopilot/scripts/phase_agent.py` does not directly import from `agent-coordinator/src/`. Instead, `coordination_bridge.try_resolve_archetype_for_phase(phase, signals)` calls the new `POST /archetypes/resolve_for_phase` endpoint. Preserves the existing skills-as-clients layering.

3. **All 13 non-terminal phases get archetype resolution** — INIT, PLAN, PLAN_ITERATE, PLAN_REVIEW, PLAN_FIX, IMPLEMENT, IMPL_ITERATE, IMPL_REVIEW, IMPL_FIX, VALIDATE, VAL_REVIEW, VAL_FIX, SUBMIT_PR. INIT and SUBMIT_PR remain state-only (no sub-agent dispatch) but record `phase_archetype` for audit (D13).

4. **Both `model` and `system_prompt` injected into options dict** — Full archetype semantics applied. Override path (`AUTOPILOT_PHASE_MODEL_OVERRIDE` env var) sets only `model`, leaves harness default for system_prompt to keep operator behavior predictable.

5. **`LoopState.phase_archetype` field; schema_version bumped 2 → 3** — Coordinator records the resolved archetype alongside the phase for audit/observability. Migration is graceful: schema_version=2 snapshots load with `phase_archetype=None`.

6. **Failure mode: graceful fallback to harness default** — If `try_resolve_archetype_for_phase` returns None (network error, 4xx, 5xx, timeout), `_build_options` skips model/system_prompt injection. Phase still dispatches; warning logged with operator hint.

7. **Coordination with harness-engineering-features via D10 read-only lock** — That change writes to `convergence_loop.py`. This proposal scopes its writes to `phase_agent.py` and `autopilot.py` only. We pre-register a read-only observation lock on `convergence_loop.py` for visibility (file lock acquisition returned 403 due to API key permission gap; declarative lock in work-packages.yaml remains).

### Alternatives Considered

- **Skills-owned phase mapping (Approach 2)**: rejected — duplicates phase concept across skills; weaker provenance for `LoopState.phase_archetype`.
- **Phase-as-signal in `resolve_model` (Approach 3)**: rejected — muddies signal abstraction (originally package-metadata, not state-machine position); awkward to inject `system_prompt` cleanly; contradicts HTTP-via-bridge choice.
- **Per-phase CLI flag**: rejected for now — env var (`AUTOPILOT_PHASE_MODEL_OVERRIDE`) is sufficient for cloud-harness flow; adding flags would plumb through autopilot driver and roadmap orchestrator without adding capability.
- **Wait for harness-engineering-features to merge**: rejected — coordinate via locks is lower-blocking; we don't write to `convergence_loop.py`.
- **Vendor `resolve_model` into skills/shared/**: rejected — DRY violation; HTTP layer is the right boundary.

### Trade-offs

- Accepted **one HTTP round-trip per phase dispatch** (~30-100ms cloud, <5ms local) over direct import to preserve skills-as-clients layering. Mitigated by HTTP keep-alive in the bridge.
- Accepted **larger coordinator surface** (new endpoint, `archetypes.yaml` schema bump) over thinner API to make the endpoint useful beyond autopilot (e.g., for `iterate-on-plan`).
- Accepted **`_PHASE_TASKS` extension to all 13 phases** (~13 task templates) over status-quo-only over D13 sentinel design — uniform phase taxonomy is worth the extra templates.
- Accepted **`LoopState` schema bump 2 → 3** with backward-compatible migration over breaking change — older snapshots load with `phase_archetype=None` and self-update on next save.

### Open Questions

- [ ] Default phase mapping (D11) — initial cut sketched; tune per usage data after first runs.
- [ ] Per-phase signal extraction (D12) — initial signals listed; missing signal sources may surface during implementation.
- [ ] Override syntax — env var only for now; CLI flag deferred unless operator feedback requires it.
- [ ] Sub-agent dispatch for INIT/SUBMIT_PR — kept state-only (D13); reconsider if observability data shows value.
- [ ] What happens during the gap between merging harness-engineering-features and merging this — rebase strategy for `_PHASE_TASKS` if their convergence_loop.py changes affect dispatched phase semantics.

### Context

**Planning goal**: wire the existing archetype catalog into the autopilot state machine so every non-terminal phase resolves an archetype and dispatches its sub-agent with the resolved `model` + `system_prompt`. The catalog already encodes which archetype is right for which kind of work; the autopilot loop just wasn't using it for per-phase selection (only IMPLEMENT-phase work-package level).

**Tier selected**: coordinated (coordinator at coord.rotkohl.ai responding with full capabilities). Decomposed into 5 work packages:

- `wp-contracts` (priority 1, root) — OpenAPI v1 + JSON schemas
- `wp-coordinator` (priority 2, depends on contracts) — coordinator-side schema + endpoint + LoopState
- `wp-skills-bridge` (priority 2, parallel with coordinator) — bridge helper
- `wp-skills-autopilot` (priority 3) — phase_agent.py integration
- `wp-integration` (priority 4) — e2e tests + docs + sync

Parallel-zones validator confirmed `wp-coordinator` and `wp-skills-bridge` can run in parallel with no scope/lock overlap.

**Estimated scope**: ~500-650 LOC across coordinator + skills + tests, ~30-40 new tests across coordinator-side and skills-side. Three specs MODIFIED (`agent-archetypes`, `skill-workflow`, `agent-coordinator`) via ADDED Requirements deltas.

**Validation status at end of plan**: `openspec validate --strict` ✓, `validate_work_packages.py` ✓ (schema/depends_on_refs/dag_cycles/lock_keys), `parallel_zones.py --validate-packages` ✓ (parallel pair confirmed). Coordinator lock pre-registration returned 403 for all 7 attempts due to API key permission gap (documented as expected behavior in project memory).
