# Tasks: add-local-model-provider-tier

<!-- TDD test-first ordering. Sizes: all tasks are S or M (no L/XL). -->

## 1. Coordinator roster and validation

- [ ] 1.1 Write tests for `local` roster loading and hardware-matching validation —
  extended entry form accepted, active-parameter ceiling enforced, dense >=30B rejected,
  tier omission degrades, review date required (S)
  **Spec scenarios**: agent-archetypes.2 (tier omission degrades), agent-archetypes.4
  (MoE entry accepted), agent-archetypes.5 (dense large model rejected)
  **Design decisions**: D4, D7
  **Dependencies**: None
  **Files**: agent-coordinator/tests/test_agents_config.py

- [ ] 1.2 Write byte-identical resolution regression test — snapshot every
  (archetype x existing provider) resolution before/after roster addition (S)
  **Spec scenarios**: agent-archetypes.3 (existing providers unaffected)
  **Design decisions**: D6
  **Dependencies**: None
  **Files**: agent-coordinator/tests/test_agents_config.py

- [ ] 1.3 Add `local` roster to `archetypes.yaml` with extended entry metadata
  (`total_params_b`, `active_params_b`, `reviewed`) plus `local_host_class` ceiling
  config; implement validation in `agents_config.py` (M)
  **Dependencies**: 1.1, 1.2
  **Files**: agent-coordinator/archetypes.yaml, agent-coordinator/src/agents_config.py

- [ ] 1.4 Sync `DEFAULT_PROVIDER_MODEL_MAP` with the `local` roster (S)
  **Dependencies**: 1.3
  **Files**: agent-coordinator/src/agents_config.py

- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Trust boundary in the resolver

- [ ] 2.1 Write tests for the local archetype trust boundary — permitted archetypes
  resolve with boundary-check reason; `architect`/`reviewer`/`gatekeeper` under `local`
  fail with structured error naming the permitted list; refusal is audit-logged (M)
  **Spec scenarios**: agent-archetypes.1 (local resolution succeeds), agent-archetypes.6
  (permitted archetype resolves), agent-archetypes.7 (boundary archetype refused)
  **Design decisions**: D3
  **Dependencies**: 1.3
  **Files**: agent-coordinator/tests/test_agents_config.py, agent-coordinator/tests/test_coordination_api.py

- [ ] 2.2 Implement the trust boundary in `resolve_archetype_for_phase` with audit
  logging of refusals (M)
  **Dependencies**: 2.1
  **Files**: agent-coordinator/src/agents_config.py

- [ ] Checkpoint: run tests, review diff, verify scope

## 3. Skills-side dispatch adapter

- [ ] 3.1 Write tests for the `local` dispatch adapter — provider accepted in
  `_SUPPORTED_PROVIDERS`; unset/unreachable endpoint yields structured `fallback`
  result naming `local`; health-probe failure marks adapter unavailable without
  hanging; concurrency cap queues excess dispatches; results normalize to
  `(outcome, handoff_id)` (M)
  **Spec scenarios**: skill-workflow.1 (configured dispatch succeeds), skill-workflow.2
  (unreachable endpoint degrades), skill-workflow.3 (concurrency cap respected)
  **Design decisions**: D2, D5
  **Dependencies**: None
  **Files**: skills/autopilot/scripts/tests/test_provider_dispatch.py

- [ ] 3.2 Add `local` to `_SUPPORTED_PROVIDERS`; implement the OpenAI-compatible
  adapter runner with `LOCAL_INFERENCE_BASE_URL` / `LOCAL_INFERENCE_API_KEY` /
  `LOCAL_INFERENCE_MAX_CONCURRENCY`, session health probe, and queueing cap (M)
  **Dependencies**: 3.1
  **Files**: skills/autopilot/scripts/provider_dispatch.py

- [ ] 3.3 Expose probe status so the roadmap policy engine cannot switch to a dead
  local endpoint (S)
  **Spec scenarios**: skill-workflow.2 (policy engine excluded while probe fails)
  **Design decisions**: D5
  **Dependencies**: 3.2
  **Files**: skills/autopilot/scripts/provider_dispatch.py, skills/autopilot-roadmap/scripts/policy.py

- [ ] Checkpoint: run tests, review diff, verify scope

## 4. Smoke path, docs, and integration

- [ ] 4.1 Write smoke-path selector tests — `local` accepted in dry-run mode; real
  mode against an unreachable endpoint reports fallback degradation as the smoke
  outcome rather than hanging (S)
  **Spec scenarios**: skill-workflow smoke scenarios (local smoke succeeds; retired
  selector still rejected)
  **Design decisions**: D2, D5
  **Dependencies**: 3.2
  **Files**: skills/autopilot/scripts/tests/test_autopilot.py

- [ ] 4.2 Extend `smoke_provider_dispatch.py` with the `local` selector (S)
  **Dependencies**: 4.1
  **Files**: skills/autopilot/scripts/smoke_provider_dispatch.py

- [ ] 4.3 Update operator docs — provider roster mentions in
  `docs/autopilot-phase-archetype-resolution.md` and `docs/autopilot-provider-smoke.md`,
  GX10 endpoint setup pointer to the source evaluation (S)
  **Dependencies**: 4.2
  **Files**: docs/autopilot-phase-archetype-resolution.md, docs/autopilot-provider-smoke.md

- [ ] 4.4 Run full quality gates (pytest, mypy --strict, ruff) across
  agent-coordinator and skills venvs; fix fallout (S)
  **Dependencies**: 4.3
  **Files**: (no new files)

- [ ] Checkpoint: run tests, review diff, verify scope
