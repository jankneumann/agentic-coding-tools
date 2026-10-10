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
>   "Dispatch honors the routed provider"; `.7` is "Runner cannot serve the routed provider";
>   `.9` is "Routed selection onto the local provider respects the trust boundary"; `.10` is
>   the narrowed "Empty catalog evidence changes no phase".
>
> **HOLD (design D8, operator decision 2026-10-10): only `wp-dispatch` runs in this autopilot
> run. `wp-router` starts only after `split-no-evidence-retention-reason` (v1.3) has merged to
> `main` and `wp-dispatch` has merged. Task 2.0 enforces the first condition; a dispatcher
> reading only `depends_on` MUST NOT start `wp-router`.**

## 1. Dispatch honors the resolved provider (wp-dispatch)

- [ ] 1.1 Write failing tests for `_selected_provider()` in `skills/tests/autopilot/test_build_options.py`:
  with no arg and no `AUTOPILOT_PROVIDER`/`AGENT_TYPE` it returns `claude_code`; the resolved
  incumbent is then a concrete model, not a tier alias; `AGENT_TYPE` and the explicit arg still
  win. [S]
  **Spec scenarios**: agent-archetypes.5
  **Design decisions**: D2
  **Dependencies**: None
- [ ] 1.2 Apply the default provider in `_selected_provider()` before archetype resolution
  (same value as `build_phase_dispatch_payload`'s post-resolution default); narrow its return
  type to `str` and audit the callers that branch on `None` (`build_phase_dispatch_kwargs`,
  `build_phase_dispatch_payload`), keeping the post-resolution default as a guard. [XS]
  **Dependencies**: 1.1
- [ ] 1.3 Write failing tests in a new `skills/tests/autopilot/test_dispatch_provider_pairing.py`:
  - when resolution returns a provider different from the caller's, `run_phase_subagent`
    (via `make_phase_callback`) passes it as `options["provider"]`, and
    `build_phase_dispatch_kwargs` emits it as `provider` (regression);
  - a runner that raises on an unservable provider is retried and then escalates; the runner
    is never called with the routed model and the caller's provider;
  - `smoke_provider_dispatch` pairs the resolved provider with the resolved model; routed onto
    `local` with an untrusted archetype it refuses; routed away from `local` it dispatches;
    a resolved non-Claude provider with a Claude alias raises `ProviderModelMappingError`. [S]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.7
  **Design decisions**: D1
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 1.4 Make `run_phase_subagent` call `_build_options` with the selected provider and set
  `options["provider"] = state_dict.get("_resolved_provider") or selected_provider`; document
  the runner contract (dispatch to `options["provider"]`, raise when unservable) on
  `SubagentRunner`. [S]
  **Dependencies**: 1.2, 1.3
- [ ] 1.5 Make `smoke_provider_dispatch` build the pair from the resolved provider and model,
  re-run the Claude-alias and `local` trust-boundary checks against the resolved provider, and
  report both caller and resolved provider. [S]
  **Dependencies**: 1.3
- [ ] 1.6 Update the autopilot SKILL.md adapter contract: every per-phase dispatch block
  captures and passes `provider` next to `prompt`/`model`/`isolation`, and states that a
  harness whose only adapter is `Agent(...)` routes a non-`claude_code` provider through the
  provider adapter or escalates, never calling `Agent(...)` with another vendor's model. Add a
  prose-guard test (modelled on `test_dispatch_prohibitions.py`) asserting each block names
  `provider`. [S]
  **Dependencies**: 1.4
- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Contracts (wp-router)

- [ ] 2.0 Gate: assert `openspec/changes/split-no-evidence-retention-reason/contracts/openapi/v1.3.yaml`
  exists (v1.3 merged) and that its SHA matches the one pinned in `contracts/README.md`; if
  v1.3 moved, regenerate `v1.4.yaml`, the record schema and `generated/models.py` from it and
  confirm the diff is only the README's listed differences. Stop if v1.3 is absent. [XS]
  **Design decisions**: D6, D8
  **Dependencies**: None
- [ ] 2.1 Write failing contract tests against the v1.4 overlay (located with `change_dir()`):
  - the new reason is in the enum, in the `retained: false` branch and outside the
    null-selected set;
  - `retention.fallback` is required when the reason is the configured fallback and rejected
    with any other reason (negative cases both ways);
  - `incumbent_exclusion_reasons` accepts only transient values, `minItems: 1`, unique;
  - `ExcludedAssignment.reason` accepts `cost-policy:unclassified`;
  - the `RetentionReason` parity test introduced by `split-no-evidence-retention-reason`
    (its task 1.2: the Literal equals the enum) covers the new value. [S]
  **Spec scenarios**: model-routing.8, model-routing.9
  **Contracts**: contracts/openapi/v1.4.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D6
  **Dependencies**: 2.0
- [ ] 2.2 Finalize `v1.4.yaml`, the record schema, and `generated/models.py` so 2.1 passes;
  each differs from v1.3 only by the differences listed in `contracts/README.md`. [S]
  **Dependencies**: 2.1

## 3. Configured fallback (wp-router)

- [ ] 3.1 Write failing tests for `FallbackOrder.vendor_order` (coordinator) and the client
  loader (`skills/tests/coordination-bridge/`): absent by default; when present it must be
  non-empty with unique, non-empty entries; the client loader additionally rejects an entry
  that names no `agents.yaml` type; the client's `local_static_route` pick is unchanged by the
  key (it stays same-provider). [S]
  **Design decisions**: D4, D5
  **Dependencies**: None
- [ ] 3.2 Add `vendor_order: list[str] | None = None` to `FallbackOrder` with the D5 validators;
  teach `routing_fallback.py`'s `_FALLBACK_FIELDS` and validator the key; then, last, add the
  commented example to `agent-coordinator/routing.yaml` with the key absent. [S]
  **Dependencies**: 3.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.3 Write failing resolver tests (parametrized over the full D3 transient and permanent
  lists) covering:
  - every transient reason triggers the fallback; every permanent reason does not;
  - a mixed transient/permanent row set counts as permanent; two transient rows with different
    reasons fall back and record both reasons sorted;
  - a lane that is both unavailable and roadmap-excluded reports `lane:unavailable` and falls
    back (the masked case, D3);
  - `vendor_order` absent, assignments disabled, or a candidate without an assignment: today's
    behavior;
  - a candidate whose agent type is not in `vendor_order`, or whose location/isolation/
    dispatch mode is not enumerated, is never picked (allowlist, D4);
  - the pick follows the D4 key over `assignment.vendor_type` and ignores score;
  - identical inputs give identical picks; `allow_exploration=True` leaves the pick and the
    reason unchanged;
  - an evidenced alternative still wins first. [M]
  **Spec scenarios**: model-routing.8, model-routing.9
  **Design decisions**: D3, D4, D5
  **Dependencies**: 3.2
- [ ] 3.4 Thread exclusion reasons into `apply_incumbent_retention` as a per-request
  `(vendor, model) → {reasons}` map, pass `policy.document.fallback` (only when the policy is a
  `RoutingPolicy`), implement the configured pick, add `fallback` to `RetentionDecision`, and
  add `incumbent-infeasible-configured-fallback` to `RetentionReason` (asserted equal to the
  v1.4 enum). [M]
  **Dependencies**: 3.3, 2.2
- [ ] 3.5 Write a failing service-level test: a transient fallback persists `retention.fallback`
  (`incumbent_exclusion_reasons`, `order_applied`), the payload validates against the v1.4
  record schema, and the top-level `fallback` stays `false`. [S]
  **Spec scenarios**: model-routing.8
  **Contracts**: contracts/events/routing-decision-record.schema.json
  **Dependencies**: 3.4
- [ ] 3.6 Persist `retention.fallback` from `RetentionDecision.fallback` in `_retain_incumbent`
  so 3.5 passes. [S]
  **Dependencies**: 3.5
- [ ] 3.7 Add `incumbent-infeasible-configured-fallback` to the retention reason list in
  `agent-coordinator/CLAUDE.md`. [XS]
  **Dependencies**: 3.4
- [ ] 3.8 Write a failing test in `agent-coordinator/tests/test_phase_archetype_resolution.py`:
  a routed selection with `assignment.vendor_type == "local"` for an archetype outside
  `LOCAL_TRUSTED_ARCHETYPES` returns the static resolution with a refusal reason; a trusted
  archetype is routed. Then apply the check in `resolve_archetype_for_phase` after routing. [S]
  **Spec scenarios**: agent-archetypes.9
  **Design decisions**: D7
  **Dependencies**: 3.4
- [ ] Checkpoint: run tests, review diff, verify scope

## 4. End to end (wp-router)

- [ ] 4.1 Write a failing end-to-end test: with the flag on, an unavailable incumbent lane, a
  configured allowlist and no evidence, `resolve_archetype_for_phase` returns the fallback's
  provider and model. The narrowed "empty evidence changes no phase" scenario holds when every
  incumbent is feasible, when no order is set, and when the incumbent's exclusion is
  permanent. [M]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.10
  **Dependencies**: 3.6, 3.8, 1.4
- [ ] 4.2 Run the coordinator suite, the autopilot and coordination-bridge skill tests, and
  `install.sh --check`; confirm `mypy --strict` and `ruff` are clean. [XS]
  **Dependencies**: 4.1
- [ ] Checkpoint: run tests, review diff, verify scope
