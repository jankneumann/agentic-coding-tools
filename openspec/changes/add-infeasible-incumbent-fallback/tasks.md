# Tasks: Configured fallback for an unavailable incumbent

> Change ID: `add-infeasible-incumbent-fallback`
> Tier: coordinated (two packages: `wp-dispatch` → `wp-router`)
> Scenario IDs:
> - `model-routing.N`: scenarios of "Incumbent Retention Until Routing Evidence" in order, as
>   restated by this change on top of `split-no-evidence-retention-reason`. `.8` is
>   "Transiently unavailable incumbent falls back to the configured order"; `.9` is
>   "Infeasible incumbent without an evidenced alternative".
> - `agent-archetypes.N`: scenarios of "Archetype Resolution Delegates to Adaptive Router" in
>   order. `.1` is "Flag off preserves static behavior"; `.5` is "Provider-less dispatch
>   resolves its default provider first"; `.6` is "Dispatch honors the routed provider"; `.7`
>   is "Runner cannot serve the routed provider"; `.9` is "Routed selection onto the local
>   provider respects the trust boundary"; `.10` is the narrowed "Empty catalog evidence
>   changes no phase".
>
> **HOLD (design D8, operator decision 2026-10-10): only `wp-dispatch` runs in this autopilot
> run. `wp-router` starts only after `split-no-evidence-retention-reason` (v1.3) has merged to
> `main` and `wp-dispatch` has merged. Task 2.0 is `wp-router`'s first step and both its task
> chains depend on it; a dispatcher reading only `depends_on` MUST NOT start `wp-router`.**
>
> Each package rebases onto `main` before its first commit (the plan was written on a branch
> behind `main`; the named router files are unchanged there, `phase_agent.py` and
> `agents_config.py` gained unrelated code).

## 1. Dispatch honors the resolved provider (wp-dispatch)

- [ ] 1.1 Write failing tests for `_selected_provider()` in `skills/tests/autopilot/test_build_options.py`:
  with no arg and no `AUTOPILOT_PROVIDER`/`AGENT_TYPE`, or a whitespace-only value, it returns
  `claude_code`; `AGENT_TYPE` and the explicit arg still win; the resolved incumbent is then a
  concrete model (`standard` → `sonnet`), not a tier alias; with the flag off, and with a
  retained incumbent, `build_phase_dispatch_payload` returns the pre-change provider and the
  tier's concrete alias as the model. [S]
  **Spec scenarios**: agent-archetypes.1, agent-archetypes.5
  **Design decisions**: D2
  **Dependencies**: None
- [ ] 1.2 Apply the default provider in `_selected_provider()` before archetype resolution
  (same value as `build_phase_dispatch_payload`'s post-resolution default, whitespace-only env
  included); narrow its return type to `str` and audit the callers that branch on `None`
  (`build_phase_dispatch_kwargs`, `build_phase_dispatch_payload`), keeping the post-resolution
  default as a guard. [XS]
  **Dependencies**: 1.1
- [ ] 1.3 Write failing tests in a new `skills/tests/autopilot/test_dispatch_provider_pairing.py`:
  - when resolution returns a provider different from the caller's (explicit `provider=` and
    env path both), `run_phase_subagent` (via `make_phase_callback`) passes it as
    `options["provider"]`, and `build_phase_dispatch_kwargs` emits it as `provider`
    (regression);
  - `claude_agent_runner(agent_fn, supported={"claude_code"})` raises `UnservableProviderError`
    for any other `options["provider"]` without calling `agent_fn`; `run_phase_subagent`
    retries and then raises `PhaseEscalationError`;
  - `smoke_provider_dispatch` pairs the resolved provider with the resolved model; routed onto
    `local` with an untrusted archetype it refuses; routed away from `local` it dispatches; a
    resolved non-Claude provider with a Claude alias raises `ProviderModelMappingError`; the
    JSON body and text line carry `provider` and `resolved_provider`. [S]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.7
  **Design decisions**: D1
  **Dependencies**: None
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 1.4 Add `provider: str | None = None` to `run_phase_subagent` and `make_phase_callback`,
  thread it to `_build_options` via `_selected_provider(provider)`, set
  `options["provider"] = state_dict.get("_resolved_provider") or selected_provider`, define
  `UnservableProviderError(provider, supported)` and the reference adapter
  `claude_agent_runner`, and document the runner contract on `SubagentRunner`. Keep
  `skills/tests/phase-record-compaction/test_phase_agent.py` green. [S]
  **Dependencies**: 1.2, 1.3
- [ ] 1.5 Make `smoke_provider_dispatch` build the pair from the resolved provider and model,
  re-run the Claude-alias and `local` trust-boundary checks against the resolved provider, and
  report `provider` (caller) plus `resolved_provider` in the JSON body and the text line. Keep
  `skills/tests/vendor-neutral-autopilot/test_smoke_provider_dispatch.py` green. [S]
  **Dependencies**: 1.3
- [ ] 1.6 Update the autopilot SKILL.md adapter contract: the 8-phase protocol block and each
  of the seven per-phase "Capture `prompt`, `model`, `isolation`" blocks also capture and pass
  `provider`, with the rule that a harness whose only adapter is `Agent(...)` routes a
  non-`claude_code` provider through the provider adapter or escalates, never calling
  `Agent(...)` with another vendor's model. Add
  `skills/tests/autopilot/test_skill_dispatch_provider_prose.py` (modelled on
  `test_prose_free_gates.py`) asserting every capture line after a `build-dispatch` call names
  `provider` and that there are seven such blocks. [S]
  **Dependencies**: 1.4
- [ ] Checkpoint: run tests, review diff, verify scope

## 2. Contracts (wp-router)

- [ ] 2.0 Gate (first step of the package; both chains depend on it): resolve the v1.3 change
  with `change_dir(repo_root, "split-no-evidence-retention-reason")` from `openspec_paths`
  (active or archived); require `git merge-base --is-ancestor origin/main HEAD`; compare
  `git hash-object` of its `contracts/openapi/v1.3.yaml`, `contracts/events/routing-decision-record.schema.json`
  and `contracts/generated/models.py` with the blob hashes pinned in `contracts/README.md`;
  assert `"no-evidenced-challenger"` is in `api.RetentionReason`. If a hash differs,
  regenerate `v1.4.yaml`, the record schema and `generated/models.py` from the merged v1.3 and
  confirm the diff is only the README's listed differences; if the change is absent, stop. [XS]
  **Design decisions**: D6, D8
  **Dependencies**: None
- [ ] 2.1 Write failing contract tests in
  `agent-coordinator/tests/model_routing/test_incumbent_retention_contracts.py` against the
  v1.4 overlay (located with `change_dir()`):
  - the new reason is in the enum, in the `retained: false` branch and outside the
    null-selected set, and a response with that reason and `selected: null` is rejected;
  - `retention.fallback` is required when the reason is the configured fallback and rejected
    with any other reason (negative cases both ways);
  - `incumbent_exclusion_reasons` accepts only transient values, `minItems: 1`, unique;
  - `order_applied` requires all four lists, each non-empty and duplicate-free;
  - `ExcludedAssignment.reason` accepts `cost-policy:unclassified`;
  - the `RetentionReason` parity test from `split-no-evidence-retention-reason` (its task 1.2:
    the Literal equals the enum) covers the new value — this file owns parity. [S]
  **Spec scenarios**: model-routing.8, model-routing.9
  **Contracts**: contracts/openapi/v1.4.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D6
  **Dependencies**: 2.0
- [ ] 2.2 Finalize `v1.4.yaml`, the record schema, and `generated/models.py` so 2.1 passes;
  each differs from v1.3 only by the differences listed in `contracts/README.md`. [S]
  **Dependencies**: 2.1

## 3. Configured fallback (wp-router)

- [ ] 3.1 Write failing tests for `FallbackOrder.vendor_order` in
  `agent-coordinator/tests/model_routing/test_routing_policy_config.py` (absent by default;
  when present non-empty with unique, non-empty entries) and for the client loader in
  `skills/tests/coordination-bridge/test_routing_fallback.py`
  (`load_routing_policy_document` accepts the key; raises `ValueError("fallback.vendor_order
  names unknown agent type …")` for an entry matching no `agents.yaml` `type`, using a fixture
  with the key populated; `local_static_route`'s pick is unchanged by the key). [S]
  **Design decisions**: D4, D5
  **Dependencies**: 2.0
- [ ] 3.2 Add `vendor_order: list[str] | None = None` to `FallbackOrder` with the D5 validators;
  teach `routing_fallback.py`'s `_FALLBACK_FIELDS`, validator and `load_routing_policy_document`
  the key (reading `agents.yaml` via `_agents_yaml_path(repo_root)` only when the key is
  present); then, last, add the commented example to `agent-coordinator/routing.yaml` with the
  key absent. [S]
  **Dependencies**: 3.1
- [ ] Checkpoint: run tests, review diff, verify scope
- [ ] 3.3 Write failing resolver tests in
  `agent-coordinator/tests/model_routing/test_incumbent_retention.py` (parametrized over the
  full D3 transient and permanent lists) covering:
  - every transient reason triggers the fallback; every permanent reason does not;
  - a mixed transient/permanent row set counts as permanent; two transient rows with different
    reasons fall back and record both reasons sorted;
  - a lane that is both unavailable and roadmap-excluded reports `lane:unavailable` and falls
    back (the masked case, D3);
  - `vendor_order` absent, or no `FallbackOrder` passed (assignments disabled): today's
    behavior; a single candidate without an assignment is skipped while others are ordered;
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
  `RoutingPolicy` and assignments are enabled), implement the configured pick, add
  `fallback: RetentionFallback | None` to `RetentionDecision`, and add
  `incumbent-infeasible-configured-fallback` to `RetentionReason`. [M]
  **Dependencies**: 3.3, 2.2
- [ ] 3.5 Write a failing service-level test in
  `agent-coordinator/tests/model_routing/test_service_incumbent.py`: a transient fallback
  persists `retention.fallback` (`incumbent_exclusion_reasons`, `order_applied` equal to the
  policy's `fallback:` block), `selected` is non-null, the payload validates against the v1.4
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
- [ ] 3.8 Write failing tests for D7, then implement both layers:
  - `agent-coordinator/tests/test_vendor_registry.py`: a lane whose agent `type` is `local`
    advertises `archetypes ∩ LOCAL_TRUSTED_ARCHETYPES`; `test_resolver.py`: the router excludes
    it with `lane:archetype-ineligible` for an untrusted archetype;
  - `agent-coordinator/tests/test_phase_archetype_resolution.py`: a response naming `local`
    via `assignment.vendor_type`, and one via catalog-vendor mapping with no assignment, for an
    untrusted archetype each return a resolution equal to the static one plus the refusal
    reason (equality, not identity) and log a warning; a trusted archetype is routed.
  Then intersect the archetypes in `vendor_registry._lane` and apply the guard to
  `_routed_provider(selected)` in `resolve_archetype_for_phase`. [S]
  **Spec scenarios**: agent-archetypes.9
  **Design decisions**: D7
  **Dependencies**: 3.4
- [ ] Checkpoint: run tests, review diff, verify scope

## 4. End to end (wp-router)

- [ ] 4.1 Extend `agent-coordinator/tests/model_routing/test_empty_evidence_end_to_end.py`
  with a failing test: with the flag on, an unavailable incumbent lane, a configured allowlist
  and no evidence, `resolve_archetype_for_phase` returns the fallback's provider and model.
  The narrowed "empty evidence changes no phase" scenario holds when every incumbent is
  feasible, when no order is set, and when the incumbent's exclusion is permanent. [M]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.10
  **Dependencies**: 3.6, 3.8, 1.4
- [ ] 4.2 From the feature worktree: run the coordinator suite, the autopilot,
  phase-record-compaction, vendor-neutral-autopilot and coordination-bridge skill tests;
  `cd skills && bash install.sh --mode copy --force --deps none --python-tools none && bash
  install.sh --check`; confirm `mypy --strict` and `ruff` are clean. [XS]
  **Dependencies**: 4.1
- [ ] Checkpoint: run tests, review diff, verify scope
