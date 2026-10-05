# Tasks: Configured fallback for an unavailable incumbent

> Change ID: `add-infeasible-incumbent-fallback`
> Tier: coordinated (two packages: `wp-dispatch` → `wp-router`)
> Scenario IDs:
> - `model-routing.N`: scenarios of "Incumbent Retention Until Routing Evidence" in order, as
>   restated by this change on top of `split-no-evidence-retention-reason`. `.8` is
>   "Transiently unavailable incumbent falls back to the configured order"; `.9` is
>   "Infeasible incumbent without an evidenced alternative".
> - `agent-archetypes.N`: scenarios of "Archetype Resolution Delegates to Adaptive Router" in
>   order. `.5` is "Provider-less dispatch resolves its default provider first"; `.6` is
>   "Dispatch honors the routed provider"; `.8` is the narrowed "Empty catalog evidence
>   changes no phase".
>
> **`wp-router` starts only after `split-no-evidence-retention-reason` (v1.3) has merged
> (design D6). `wp-dispatch` has no such dependency.**

## 1. Dispatch honors the resolved provider (wp-dispatch)

- [ ] 1.1 Write failing tests for `_selected_provider()`. With no arg and no
  `AUTOPILOT_PROVIDER`/`AGENT_TYPE` it returns `claude_code`; the resolved incumbent is then a
  concrete model, not a tier alias. [S]
  **Spec scenarios**: agent-archetypes.5
  **Design decisions**: D2
  **Dependencies**: None
- [ ] 1.2 Apply the default provider in `_selected_provider()` before archetype resolution
  (same value as `build_phase_dispatch_payload`'s post-resolution default). [XS]
  **Dependencies**: 1.1
- [ ] 1.3 Write failing tests: when resolution returns a provider different from the
  caller's, the runner receives the routed provider. Cover both `run_phase_subagent` (via
  `make_phase_callback`) and `smoke_provider_dispatch`; neither may pair the routed model
  with the caller's provider. [S]
  **Spec scenarios**: agent-archetypes.6
  **Design decisions**: D1
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 1.4 Make `run_phase_subagent` pass `_resolved_provider` to its runner. [S]
  **Dependencies**: 1.3
- [ ] 1.5 Make `smoke_provider_dispatch` use the resolved provider with the resolved model. [XS]
  **Dependencies**: 1.3
- [ ] 1.6 Name `provider` in the autopilot SKILL.md dispatch-adapter contract next to
  `prompt`/`model`. [XS]
  **Dependencies**: 1.4
- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Contracts (wp-router)

- [ ] 2.1 Write failing contract tests against the v1.4 overlay (located with `change_dir()`):
  - the new reason is in the enum, in the "retained: false" branch and outside the
    null-selected set;
  - the decision record accepts `retention.fallback`;
  - the reason-parity check (from item 5) covers the new value. [S]
  **Spec scenarios**: model-routing.8
  **Contracts**: contracts/openapi/v1.4.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D6
  **Dependencies**: None
- [ ] 2.2 Finalize `v1.4.yaml`, the record schema, and `generated/models.py` so 2.1 passes;
  each differs from v1.3 only by the D6 additions. [S]
  **Dependencies**: 2.1

## 3. Configured fallback (wp-router)

- [ ] 3.1 Write failing tests for `FallbackOrder.vendor_order`: it parses from `routing.yaml`,
  is absent by default, and the client-side `routing_fallback.py` sort honors it with the same
  semantics. [S]
  **Design decisions**: D4, D5
  **Dependencies**: None
- [ ] 3.2 Add `vendor_order` to `FallbackOrder`; make the coordinator load the `fallback:`
  block; teach `routing_fallback.py` the key. [S]
  **Dependencies**: 3.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.3 Write failing resolver tests covering:
  - every transient reason triggers the fallback;
  - every permanent reason does not (parametrized over the full D3 list);
  - a mixed transient/permanent row set counts as permanent;
  - no `vendor_order` means today's behavior;
  - no feasible candidate means today's behavior;
  - the pick follows the D4 key and ignores score;
  - identical inputs give identical picks;
  - an evidenced alternative still wins first. [M]
  **Spec scenarios**: model-routing.8, model-routing.9
  **Design decisions**: D3, D4, D5
  **Dependencies**: 3.2
- [ ] 3.4 Thread exclusion reasons into `apply_incumbent_retention` and implement the
  configured pick; add `incumbent-infeasible-configured-fallback` to `RetentionReason`. [M]
  **Dependencies**: 3.3, 2.2
- [ ] 3.5 Write a failing service-level test: a transient fallback persists
  `retention.fallback` and validates against the v1.4 record schema. [S]
  **Spec scenarios**: model-routing.8
  **Contracts**: contracts/events/routing-decision-record.schema.json
  **Dependencies**: 3.4
- [ ] 3.6 Persist `retention.fallback` in the decision payload so 3.5 passes. [S]
  **Dependencies**: 3.5
- [ ] Checkpoint: run tests, review diff, verify scope

## 4. End to end (wp-router)

- [ ] 4.1 Write a failing end-to-end test: with the flag on, an unavailable incumbent lane, a
  configured order and no evidence, `resolve_archetype_for_phase` returns the fallback's
  provider and model. The narrowed "empty evidence changes no phase" scenario holds whenever
  every incumbent is feasible or no order is set. [M]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.8
  **Dependencies**: 3.6, 1.4
- [ ] 4.2 Run the coordinator suite and the autopilot skill tests; confirm `mypy --strict` and
  `ruff` are clean. [XS]
  **Dependencies**: 4.1
- [ ] Checkpoint: run tests, review diff, verify scope
