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
>   changes no phase"; `.11` is "A harness without a provider adapter escalates".
>
> **HOLD (design D8, operator decision 2026-10-10): only `wp-dispatch` runs in this autopilot
> run. `work-packages.yaml` therefore lists `wp-dispatch` only; `wp-router` is defined in
> `work-packages.held.yaml`, which no scheduler loads. Because no scheduler can run a task of a
> package it does not load, the promotion is step P0 below: an operator/orchestrator action run
> from the feature worktree, outside any package, only after `split-no-evidence-retention-reason`
> (v1.3) and `wp-dispatch` are both on `origin/main`. Task 2.0 is `wp-router`'s first step and
> both its task chains depend on it; it re-checks P0's facts and fails fast, it never promotes.
> The change directory stays active between the two runs: `cleanup-feature` (task migration and
> `openspec archive`) is withheld after the `wp-dispatch` PR merges and runs only after
> `wp-router` merges (design D8). Operator running `cleanup-feature` after the first PR: its
> step 5 will find tasks 2.x–4.x unchecked and ask for a migration target — answer by
> stopping, not by migrating; those tasks belong to the second run. P0 moves the finished
> `loop-state.json` aside so the second run starts fresh.**
>
> Each package rebases onto `main` before its first commit (the plan was written on a branch
> behind `main`; the named router files are unchanged there, `phase_agent.py` and
> `agents_config.py` gained unrelated code).

## 1. Dispatch honors the resolved provider (wp-dispatch)

- [x] 1.1 Write failing tests for `_selected_provider()` in `skills/tests/autopilot/test_build_options.py`:
  with no arg and no `AUTOPILOT_PROVIDER`/`AGENT_TYPE`, or a whitespace-only value, it returns
  `claude_code`; `AGENT_TYPE` and the explicit arg still win; the resolved incumbent is then a
  concrete model (`standard` → `sonnet`), not a tier alias; with the flag off, and with a
  retained incumbent, and with the resolver unavailable, `build_phase_dispatch_payload`
  returns the pre-change provider and the tier's concrete alias as the model. [S]
  **Spec scenarios**: agent-archetypes.1, agent-archetypes.2, agent-archetypes.5
  **Design decisions**: D2
  **Dependencies**: None
- [x] 1.2 Apply the default provider in `_selected_provider()` before archetype resolution
  (same value as `build_phase_dispatch_payload`'s post-resolution default, whitespace-only env
  included); narrow its return type to `str` and audit the callers that branch on `None`
  (`build_phase_dispatch_kwargs`, `build_phase_dispatch_payload`), keeping the post-resolution
  default as a guard. [XS]
  **Dependencies**: 1.1
- [x] 1.3 Write failing tests in a new `skills/tests/autopilot/test_dispatch_provider_pairing.py`:
  - when resolution returns a provider different from the caller's (explicit `provider=` and
    env path both), `run_phase_subagent` (via `make_phase_callback`) passes it as
    `options["provider"]`, and `build_phase_dispatch_kwargs` emits it as `provider`
    (regression);
  - `claude_agent_runner(agent_fn, supported={"claude_code"})` raises `UnservableProviderError`
    for any other `options["provider"]` without calling `agent_fn`; `run_phase_subagent`
    raises `PhaseEscalationError` on the first `UnservableProviderError` without a retry (the
    failure is deterministic: neither the runner's supported set nor `options["provider"]`
    changes between attempts) and without consuming the retry budget;
  - `smoke_provider_dispatch` pairs the resolved provider with the resolved model; routed onto
    `local` with an untrusted archetype it refuses; routed away from `local` it dispatches; a
    resolved non-Claude provider with a Claude alias raises `ProviderModelMappingError`; the
    JSON body and text line carry `provider` and `resolved_provider`. [S]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.7
  **Design decisions**: D1
  **Dependencies**: None
- [x] Checkpoint: run tests, review diff, verify scope
- [x] 1.4 Add `provider: str | None = None` to `run_phase_subagent` and `make_phase_callback`,
  thread it to `_build_options` via `_selected_provider(provider)`, set
  `options["provider"] = state_dict.get("_resolved_provider") or selected_provider`, define
  `UnservableProviderError(provider, supported)` and the reference adapter
  `claude_agent_runner`, and document the runner contract on `SubagentRunner`. Keep
  `skills/tests/phase-record-compaction/test_phase_agent.py` green. [S]
  **Dependencies**: 1.2, 1.3
- [x] 1.5 Make `smoke_provider_dispatch` build the pair from the resolved provider and model,
  re-run the Claude-alias and `local` trust-boundary checks against the resolved provider, and
  report `provider` (caller) plus `resolved_provider` in the JSON body and the text line. Keep
  `skills/tests/vendor-neutral-autopilot/test_smoke_provider_dispatch.py` green. [S]
  **Dependencies**: 1.3
- [ ] 1.6 Update the autopilot SKILL.md adapter contract: the 8-phase protocol block and every
  per-phase dispatch block that follows a `runner.py build-dispatch` call — the GATEKEEPER
  block ("call the dispatch adapter with `prompt`/`model`") and the seven "Capture `prompt`,
  `model`, `isolation`" blocks, eight in all — capture and pass `provider`, with the rule that
  a harness whose only adapter is `Agent(...)` routes a non-`claude_code` provider through the
  provider adapter or escalates, never calling `Agent(...)` with another vendor's model. Add
  `skills/tests/autopilot/test_skill_dispatch_provider_prose.py` (modelled on
  `test_prose_free_gates.py`) that locates every `runner.py build-dispatch` invocation,
  asserts the adapter-call sentence after each names `provider`, and asserts the count is
  eight. [S]
  **Spec scenarios**: agent-archetypes.11
  **Design decisions**: D1
  **Dependencies**: 1.4
- [ ] Checkpoint: run tests, review diff, verify scope

## P. Promotion gate (operator/orchestrator step; belongs to no package)

- [ ] P0 Promotion gate. **Not a task of any package**: `work-packages.held.yaml` is loaded by
  no scheduler, so no worker can be dispatched to a `wp-router` task before this step; it is run
  by the operator or the orchestrator from the feature worktree, outside any package scope,
  after `wp-dispatch` has merged and before the autopilot run that dispatches `wp-router`. All
  checks read the `origin/main` tree after `git fetch origin`, never the working tree:
  - locate the v1.3 change directory on `origin/main` with `git ls-tree` under
    `openspec/changes/` or `openspec/changes/archive/*-split-no-evidence-retention-reason/`;
    stop if absent;
  - compare `git rev-parse origin/main:<dir>/contracts/openapi/v1.3.yaml`,
    `…/contracts/events/routing-decision-record.schema.json` and
    `…/contracts/generated/models.py` with the blob ids pinned in `contracts/README.md`;
  - `git grep -q no-evidenced-challenger origin/main -- agent-coordinator/src/model_routing/api.py`
    (v1.3 code merged);
  - one marker per `wp-dispatch` dispatch surface, all on `origin/main`:
    `git grep -q UnservableProviderError origin/main -- skills/autopilot/scripts/phase_agent.py`
    (1.4), `git grep -q resolved_provider origin/main -- skills/autopilot/scripts/smoke_provider_dispatch.py`
    (1.5), and `git cat-file -e origin/main:skills/tests/autopilot/test_skill_dispatch_provider_prose.py`
    followed by running that prose-guard test from the feature worktree, which is rebased onto
    `origin/main` and therefore carries that SKILL.md (1.6: the eight SKILL.md blocks); a
    partial implementation fails one of the three; record the command and result in the
    promotion commit message;
  - require `git merge-base --is-ancestor origin/main HEAD` (the feature branch is rebased);
  - require that the change directory is still active: `openspec/changes/<id>/` exists on
    `origin/main` and not under `openspec/changes/archive/` (design D8: `cleanup-feature` is
    withheld for this change until `wp-router` merges; if it was archived, stop and restore
    before promoting);
  - require that `openspec/changes/<id>/loop-state.json` is absent or has `current_phase:
    DONE` (the first run finished); move it to `loop-state.run-1.json` as the `wp-dispatch`
    completion record, so the second run starts at `INIT` (`runner.py init` leaves an existing
    file alone and `apply-outcome` is a no-op at `DONE`).
  If a blob differs, regenerate `v1.4.yaml`, the record schema and `generated/models.py` from
  the merged v1.3, confirm the diff is only the README's listed differences, and re-pin the
  three blob ids and the source commit in `contracts/README.md` in the same commit. Then promote
  `wp-router`: run `skills/validate-packages/scripts/validate_work_packages.py
  work-packages.held.yaml` (must be VALID), copy its package entry from
  `work-packages.held.yaml` into the `packages` list of `work-packages.yaml` in place of
  `wp-dispatch` (the completed `wp-dispatch` is on `origin/main`; its record lives in the merged
  PR and in `loop-state.json`, not in the manifest), delete the held file, run
  `validate_work_packages.py work-packages.yaml` again (must be VALID), and commit on the
  feature branch. [XS]
  **Design decisions**: D6, D8
  **Dependencies**: `wp-dispatch` and v1.3 on `origin/main` (external; not a task id)

## 2. Contracts (wp-router)

- [ ] 2.0 Fail-fast re-check (first step of the package; both chains depend on it). Re-run P0's
  **object-store** checks from the package worktree: the three blob comparisons, the v1.3
  marker, the three `wp-dispatch` markers as `git grep` / `git cat-file -e` against
  `origin/main` (not the prose-guard test execution: the package denies `skills/autopilot/**`
  and cannot create another checkout; P0's run of it is attested by the promotion commit),
  `merge-base --is-ancestor`, and
  `skills/validate-packages/scripts/validate_work_packages.py work-packages.yaml` on the promoted
  manifest; stop the package if any fails. Every command reads the git object store or the
  change directory, both inside the package's read scope. This step never promotes or
  regenerates anything; it proves that P0 ran against the tree the worker sees. [XS]
  **Design decisions**: D8
  **Dependencies**: None
- [ ] 2.1 Write failing contract tests in
  `agent-coordinator/tests/model_routing/test_incumbent_retention_contracts.py` against the
  v1.4 overlay (located with `change_dir()`):
  - the new reason is in the enum, in the `retained: false` branch and outside the
    null-selected set, and a response with that reason and `selected: null` is rejected;
  - `retention.fallback` is required when the reason is the configured fallback and rejected
    with any other reason (negative cases both ways);
  - `incumbent_exclusion_reasons` accepts only transient values, `minItems: 1`, unique
    (unsorted input is accepted by all three contracts: sorting is a producer invariant,
    tested in 3.5);
  - `order_applied` requires all four lists, each non-empty and duplicate-free; rejects an
    empty-string `vendor_order` entry; and rejects a `location_order` / `isolation_order` /
    `dispatch_mode_order` value outside the `Location` / `Isolation` / `DispatchMode` enums
    (e.g. `location_order: ["mars"]`), in all three contracts;
  - the record schema rejects `retention.reason: incumbent-infeasible-configured-fallback`
    when `request.incumbent` is absent and when it is `null` (negative cases both);
  - a configured-fallback response with top-level `fallback: true` is rejected;
  - the record schema requires `retention` whenever `request.incumbent` is an object: a record
    with an incumbent and no `retention` is rejected, one with `incumbent: null` (or absent) and
    no `retention` is accepted;
  - the generated `Retention` model rejects `retained` inconsistent with `reason` and an
    explicit `fallback: null` for any other reason;
  - `ExcludedAssignment.reason` accepts `cost-policy:unclassified`;
  - parity: this file owns the single `RetentionReason` parity assertion (the code Literal
    equals the v1.4 enum). If the merged v1.3 ships its own Literal-equals-v1.3-enum assertion
    (its task 1.2; none exists on `main` today), 2.1 **retargets that assertion to the v1.4
    overlay in place** rather than adding a second one, so no v1.3-anchored parity test is left
    in the suite to go red when 3.4 adds the value. The retargeted case is expected to stay red
    after 2.2 (the Literal gains the value only in 3.4); mark it
    `xfail(strict=True, reason="until task 3.4")` so the 2.x checkpoint is green and 3.4 flips
    it by removing the marker. [S]
  **Spec scenarios**: model-routing.8, model-routing.9
  **Contracts**: contracts/openapi/v1.4.yaml, contracts/events/routing-decision-record.schema.json
  **Design decisions**: D6
  **Dependencies**: 2.0
- [ ] 2.2 Finalize `v1.4.yaml`, the record schema, and `generated/models.py` so 2.1 passes
  (every case except the `xfail`-marked parity case, which 3.4 turns green); each differs from
  v1.3 only by the differences listed in `contracts/README.md`. [S]
  **Dependencies**: 2.1
- [ ] Checkpoint: run tests, review diff, verify scope

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
  - an incumbent with at least one feasible row is never displaced by the fallback, whatever
    its other rows' exclusion reasons (the trigger requires no feasible row and at least one
    excluded row, D3);
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
  `incumbent-infeasible-configured-fallback` to `RetentionReason`, and remove the `xfail`
  marker 2.1 put on the parity case. [M]
  **Dependencies**: 3.3, 2.2
- [ ] 3.5 Write a failing service-level test in
  `agent-coordinator/tests/model_routing/test_service_incumbent.py`: a transient fallback
  persists `retention.fallback` (`incumbent_exclusion_reasons`, `order_applied` equal to the
  policy's `fallback:` block, `incumbent_exclusion_reasons` emitted sorted), `selected` is
  non-null, the payload validates against the v1.4 record schema, and the top-level
  `fallback` stays `false`. [S]
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
    advertises `archetypes ∩ LOCAL_TRUSTED_ARCHETYPES`;
    `agent-coordinator/tests/model_routing/test_resolver.py` (inside the package's
    `tests/model_routing/**` scope, run by the "Model-routing suite" step): the router excludes
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

## 4. End to end (4.1 in wp-router; 4.2 is the validation phase's feature-level gate, no package)

- [ ] 4.1 Extend `agent-coordinator/tests/model_routing/test_empty_evidence_end_to_end.py`
  with a failing test: with the flag on, an unavailable incumbent lane, a configured allowlist
  and no evidence, `resolve_archetype_for_phase` returns the fallback's provider and model.
  The narrowed "empty evidence changes no phase" scenario holds when every incumbent is
  feasible, when no order is set, and when the incumbent's exclusion is permanent. [M]
  **Spec scenarios**: agent-archetypes.6, agent-archetypes.10
  **Dependencies**: 3.6, 3.8, 1.4
- [ ] 4.2 Feature-level gate, run from the feature worktree by the validation phase (it
  cannot run inside an isolated package worktree): the coordinator suite, the autopilot,
  phase-record-compaction, vendor-neutral-autopilot and coordination-bridge skill tests;
  `cd skills && bash install.sh --mode copy --force --deps none --python-tools none && bash
  install.sh --check`; `mypy --strict` and `ruff` clean. The per-package verification steps in
  both manifests cover everything except the install check. [XS]
  **Dependencies**: 4.1
- [ ] Checkpoint: run tests, review diff, verify scope
