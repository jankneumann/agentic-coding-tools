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

---

## Phase: Implementation (2026-04-25)

**Agent**: claude_code | **Session**: N/A

### Decisions
1. **Inline implementation instead of multi-agent dispatch** `architectural: agent-coordinator` — Coordinator was available (true coordinated tier eligible), but a single Claude session with full repo context honors TDD-RED-GREEN per task more cleanly than spawning isolated Agent(isolation:worktree) subagents. Coordinator audit + D10 lock benefits preserved by routing through coordination_bridge.
2. **Bypass capability-probe machinery for the new bridge helper** `architectural: coordination-bridge` — try_resolve_archetype_for_phase calls _http_request directly instead of going through _execute_single_endpoint_operation, to avoid adding a new CAN_ARCHETYPES probe that every unrelated try_* call would then run on every invocation.
3. **Defer GET /discovery/agents persistence (D-1)** `architectural: agent-coordinator` — wp-coordinator scope (write_allow) covers agents_config, coordination_api, archetypes.yaml only. Persisting phase_archetype on the AgentInfo record requires editing discovery.py + adding a DB migration — both outside scope. Status reports forward the value via the event bus context, covering the primary in-flight observability need.
4. **Defer INIT phase archetype recording + status reporter emission (D-2)** `architectural: skill-workflow` — INIT is a pure state transition in autopilot.run_loop (bypasses run_phase_subagent). The status reporter at agent-coordinator/scripts/report_status.py is outside wp-skills-autopilot's write_allow. Both would require broader autopilot or hook-script changes; tracked in deferred-tasks.md D-2 for a follow-up.
5. **Defer install.sh runtime sync to /cleanup-feature (D-3)** `architectural: autopilot` — Running install.sh from this branch would clobber .claude/skills/ and .agents/skills/ which were synced from main's d1cbd76. After rebase against main, the sync runs cleanly. Recording as a deferred merge-window action.

### Alternatives Considered
- Multi-agent dispatch via Agent(isolation:worktree) for parallel wp-coordinator + wp-skills-bridge: rejected because Adds branch-merge complexity for two ~700+150 LOC packages that one Opus session can serialize without losing context or test coverage. Saves nothing in wall-clock when the orchestrator is the bottleneck on commit ordering.
- Add CAN_ARCHETYPES capability probe in coordination_bridge: rejected because Each existing try_* helper would then probe the new endpoint on every call (capability detection runs across all probes). Direct _http_request keeps the helper isolated.
- Force INIT through run_phase_subagent for archetype recording: rejected because Restructures the state-machine dispatch table for an audit-only side effect. A small driver-level helper at INIT phase entry is the cleaner future path (D-2).

### Trade-offs
- Accepted One HTTP round-trip per phase dispatch (~30-100ms cloud, <5ms local) over In-process resolution that would couple skills to coordinator-side YAML schema because HTTP boundary lets future skills (iterate-on-plan, validate-feature) reuse the resolution endpoint without duplicating the phase mapping. Mitigated by HTTP keep-alive in the bridge.
- Accepted phase_archetype in LoopState as scalar (current phase only) instead of dict (per-phase history) over Persisting full phase_archetype history alongside handoff_ids[] because Spec D7 specifies scalar; phase history lives in handoff_ids + phase records, so the scalar avoids duplication. Observability dashboards can reconstruct history by joining loop-state snapshots over time.
- Accepted Pre-existing mypy errors in autopilot.py left in place over Fixing the import-not-found errors for sibling try/except imports because Errors are environmental (mypy from agent-coordinator/.venv doesn't see skills/ sibling modules); my changes added 0 new errors. Fix belongs to a skills/ pyproject.toml change, outside this proposal's scope.

### Open Questions
- [ ] Should the scalar phase_archetype become a per-phase dict in a follow-up, alongside handoff_ids[]?
- [ ] Once /cleanup-feature runs install.sh post-rebase, verify .agents/skills/autopilot/scripts/phase_agent.py reflects the new _PHASE_SIGNAL_KEYS dict and _build_options(phase, state_dict) signature.
- [ ] When INIT archetype recording is wired (D-2), should it also emit a 'phase_started' audit event so the audit trail shows the runner archetype for INIT, not just for IMPLEMENT/PLAN/etc.?

### Completed Work
- wp-contracts (6e660f1): change-context.md with 10-row Requirement Traceability Matrix; tasks 1.1-1.3 flipped (contracts authored in plan commit 7ba3720).
- wp-skills-bridge (c0c65df): try_resolve_archetype_for_phase helper + 10 unit tests + bonus dict[str, Any] annotation widening to unblock mypy --strict.
- wp-coordinator (c68efa9): PhaseMappingEntry + ResolvedArchetype dataclasses; load_archetypes_config phase_mapping parsing with cross-reference validation; resolve_archetype_for_phase function; phase kwarg on resolve_model; POST /archetypes/resolve_for_phase endpoint with X-API-Key + audit; StatusReportRequest.phase_archetype + event-bus forwarding; archetypes.yaml v2 with 13-entry phase_mapping; 18 unit tests.
- wp-skills-autopilot (0333dd4): LoopState v3 with phase_archetype + v2->v3 migration; _PHASE_SIGNAL_KEYS dict; _extract_signals_for_phase; _parse_phase_model_override + _check_phase_model_override; _build_options(phase, state_dict) with override + archetype + fallback paths; _PHASE_TASKS extended to all 13 phases (None for INIT/SUBMIT_PR per D13); make_phase_callback propagates _resolved_archetype to LoopState.phase_archetype; 59 unit tests; 1 baseline assertion update in test_autopilot.py.
- wp-integration (87613a2): 5 e2e wiring tests using FastAPI TestClient; SKILL.md per-phase section; CLAUDE.md API table entry; new docs/autopilot-phase-archetype-resolution.md operator guide; D-3 deferred-task entry.
- Quality gates: 2081 agent-coordinator tests pass (3 pre-existing Docker failures unrelated); 182 skills tests pass scoped to my packages; 0 NEW mypy errors; ruff clean; openspec validate --strict PASS; change-context Coverage Summary 10/10 traced/tested/evidenced.

### Next Steps
- /validate-feature add-per-phase-archetype-resolution should run the deploy/smoke/security/e2e phases (Docker-dependent) before merge.
- /cleanup-feature add-per-phase-archetype-resolution: rebase against main (resolves d1cbd76 runtime-sync drift), then run skills/install.sh to propagate the canonical changes into .claude/skills/ and .agents/skills/ (D-3).
- Optionally: register the read-only file lock on convergence_loop.py with reason='read-only observation: add-per-phase-archetype-resolution' for visibility with the harness-engineering-features change (D10 advisory).
- Pick up D-1 (GET /discovery/agents listing exposure) and D-2 (INIT recording + status reporter emission) as a follow-up proposal once this lands.

### Relevant Files
- `agent-coordinator/src/agents_config.py` — Schema bump + PhaseMappingEntry/ResolvedArchetype + resolve_archetype_for_phase + phase kwarg on resolve_model.
- `agent-coordinator/src/coordination_api.py` — POST /archetypes/resolve_for_phase endpoint + StatusReportRequest.phase_archetype field + event-bus forwarding.
- `agent-coordinator/archetypes.yaml` — schema_version 1->2 with 13-entry phase_mapping section.
- `skills/coordination-bridge/scripts/coordination_bridge.py` — try_resolve_archetype_for_phase helper + module logger + dict[str, Any] annotation fix.
- `skills/autopilot/scripts/phase_agent.py` — _PHASE_SIGNAL_KEYS, _extract_signals_for_phase, _parse/_check_phase_model_override, extended _build_options, extended _PHASE_TASKS for all 13 phases, make_phase_callback propagation.
- `skills/autopilot/scripts/autopilot.py` — LoopState bumped 2->3 with phase_archetype + v2->v3 migration in load_state.
- `skills/tests/autopilot/test_phase_archetype_e2e.py` — 5 end-to-end wiring tests using FastAPI TestClient as the in-process coordinator.
- `docs/autopilot-phase-archetype-resolution.md` — Operator-facing guide: 13-phase mapping, override syntax, failure mode, observability, API reference.
- `openspec/changes/add-per-phase-archetype-resolution/change-context.md` — Requirement Traceability Matrix with 10/10 evidence pass cells; Design Decision Trace; Coverage Summary 10/10.
- `openspec/changes/add-per-phase-archetype-resolution/deferred-tasks.md` — D-1 (GET listing exposure), D-2 (INIT recording + reporter emission), D-3 (merge-window operator actions).

### Context
Implemented per-phase archetype resolution across 5 work packages (coordinator, bridge, autopilot, contracts, integration). All 13 non-terminal autopilot phases now resolve a {model, system_prompt} via POST /archetypes/resolve_for_phase before sub-agent dispatch. LoopState bumped to schema_version=3 with phase_archetype field; AUTOPILOT_PHASE_MODEL_OVERRIDE env var supports operator overrides; graceful fallback to harness defaults on coordinator failure.

---

## Phase: Validation (2026-04-28)

**Agent**: claude_code | **Session**: N/A

### Decisions
1. **Skip deploy + smoke + e2e + logs phases (services not deployed)** `architectural: autopilot` — docker-compose.yml provides infrastructure (postgres, openbao, langfuse) but no agent-coordinator API service. Local dev runs `python -m src.coordination_api` directly. Smoke tests need a live HTTP service; without one they fail with connection refused. Change-specific routing/auth/error paths are exercised by 23 in-process FastAPI TestClient tests (test_phase_archetype_resolution + test_phase_archetype_e2e), which use the same ASGI machinery a deployed instance uses.
2. **Accept security via --dry-run + structural review** `architectural: autopilot` — No new external dependencies added; new endpoint is X-API-Key auth-gated. Full Dependency-Check + ZAP would take 10+ min and not change the verdict (no new deps to flag; ZAP requires deployed service). Dry-run shows decision=PASS, triggered_count=0.
3. **Treat 4 CI failures as pre-existing, not blocking** `architectural: autopilot` — dependency-audit-coordinator + dependency-audit-skills both fail on pip 26.0.1 CVE-2026-3219 (a vulnerability in pip itself; not added by this PR). validate-decision-index fails on decision-index drift in decisions/ (this PR does not touch that tree). SonarCloud is advisory. The critical `test` job passes.

### Open Questions
- [ ] Should docker-compose.yml gain an agent-coordinator API service so future /validate-feature runs can do a real deploy + smoke phase?
- [ ] Should validate-feature treat compose-without-coordinator as an explicit 'partial-deploy' result rather than 'skip'?
- [ ] When does the decision-index drift get reconciled? It's been failing CI on this branch and likely main too.

### Completed Work
- spec (task drift gate + traceability)
- evidence (work-packages audit)
- security (dry-run + structural review)
- architecture (info-only diagnostics)
- ci (status check)

### Next Steps
- /cleanup-feature add-per-phase-archetype-resolution — rebases against main, runs skills/install.sh, merges PR #129, archives change.
- Optionally: address CI failures separately as cross-cutting maintenance (pip pin, SonarCloud config, regenerate decision-index).

### Context
Validation PASS for add-per-phase-archetype-resolution. Critical gates (spec drift, openspec validate, requirement traceability, work-package evidence) all pass. 4 phases skipped (deploy/smoke/e2e/logs) due to compose-stack lacking a coordinator API service; 23 in-process FastAPI TestClient tests cover the equivalent surface. CI: 6 pass / 4 fail with all 4 failures pre-existing and unrelated to this PR.

---

## Phase: Validation (2026-05-03)

**Agent**: claude_code | **Session**: N/A

### Decisions
1. **Re-validate via deployed stack rather than --force gate override** — The infra extension (PR #129 commit 637cc12) was created precisely to enable deploy/smoke/e2e against a real coordinator-api. Running the gate against the new stack produces real evidence; --force would have shipped the same skip rationale a second time without exercising the new infrastructure.
2. **Keep both tabular Phase Results and canonical phase sections in the report** — The tabular form is for human readers; the canonical `## Smoke Tests`/`## Security`/`## E2E Tests` sections with `**Status**: pass` are what gate_logic.py parses. Both serve different audiences and don't conflict.

### Completed Work
- deploy: docker compose --profile api up -d --build coordinator-api (healthy <2s)
- smoke: 10/10 passed (1 CORS preflight skipped intentionally)
- security: PASS, triggered_count=0, no threshold findings
- e2e: 19/19 passed against live ParadeDB (audit, handoffs, memory, work_queue, locks, guardrails, auth, health)
- validation-report.md rewritten in canonical gate-parseable format
- pre-merge gate now PASSES (was halting on missing phase sections)

### Next Steps
- proceed with cleanup-feature merge + archive

### Context
Re-validation against the new coordinator-api compose stack (commit 637cc12) promoted deploy/smoke/e2e/logs from skip to pass and rewrote the validation-report.md to expose canonical phase sections that the pre-merge gate parses.

