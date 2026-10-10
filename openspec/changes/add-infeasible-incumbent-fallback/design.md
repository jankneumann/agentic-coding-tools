# Design: add-infeasible-incumbent-fallback

## Context

- **Where exclusion reasons are lost.** `RoutingService.select_model` (`api.py`) collapses
  every exclusion to a bare `(vendor, model)` before `apply_incumbent_retention` sees it. The
  reason (`lane:unavailable`, `roadmap:vendor-excluded`, …) survives only in the response's
  `excluded` payload. Both sources carry a reason: `score_and_rank`'s `excluded` pairs
  (`feasibility_reason`: `unavailable`, `quota:exhausted`) and `assignment_excluded`
  (`ExcludedAssignmentInput.reason`, the `lane:*`/`roadmap:*`/`cost-policy:*` family).
- **Unevidenced candidates are already scored.** Feasible unevidenced candidates are in
  `ranked` with full `RoutingAssignment`s. The retention core drops them via the `c.evidenced`
  filter.
- **Lane attributes live on the assignment.** `vendor_type` (agent type), `location`,
  `isolation`, `dispatch_mode` and `agent_id` exist only on `ScoredCandidate.assignment`,
  which is `None` when the service runs without a registry or policy
  (`RoutingService._assignment_enabled`).
- **The order config exists but is client-only.** `routing.yaml` already has a `fallback:`
  block (`location_order`, `isolation_order`, `dispatch_mode_order`), parsed server-side into
  `RoutingPolicyDocument.fallback` (strict model, `extra="forbid"`, each list `min_length=1`)
  but consumed only by `skills/coordination-bridge/scripts/routing_fallback.py`
  (`local_static_route`) when the coordinator is unreachable. That client path considers only
  lanes of the caller's static provider and **excludes** a lane whose location or isolation is
  not enumerated in the order lists. Its loader rejects unknown `fallback:` keys.
- **The client trusts the router's vendor, but dispatch doesn't.**
  - `phase_agent.build_phase_dispatch_kwargs` sets the payload provider to
    `_resolved_provider or selected_provider`.
  - `run_phase_subagent` (via `make_phase_callback`) calls `_build_options` provider-less and
    passes the runner only `prompt` and `options` (`model`, `system_prompt`, `isolation`).
    The runner contract is `(prompt, options) -> (outcome, handoff_id)`.
  - `smoke_provider_dispatch` uses its own fixed provider for the pair, the smoke phase, the
    Claude-alias check and the `local` trust-boundary check.
  - The autopilot SKILL.md per-phase blocks tell the harness to capture `prompt`/`model`/
    `isolation` and call `Agent(...)`, although `build-dispatch` already emits `provider`.
- **Provider-less resolution sends a tier alias.** `_selected_provider()` returns `None` with
  no arg and no `AUTOPILOT_PROVIDER`/`AGENT_TYPE`, so resolution runs provider-less and the
  incumbent is `{vendor: null, model: "<tier alias>"}`. `build_phase_dispatch_payload` applies
  the `claude_code` default only after resolution.
- **The `local` trust boundary is checked on the caller's provider only.**
  `resolve_archetype_for_phase` raises `LocalProviderTrustBoundaryError` when the *caller's*
  provider is `local` and the archetype is outside `LOCAL_TRUSTED_ARCHETYPES`, but a routed
  selection whose `vendor_type` is `local` is returned without that check.
- **Reason precedence.** `_lane_exclusion_reason` returns the first failing check, and
  availability (`lane:unavailable`, `lane:model-rate-limited`) is checked before archetype,
  dispatch mode, location, isolation and `roadmap:*`. A lane that is both down and
  policy-excluded reports only the transient reason.

## Goals / Non-Goals

**Goals**
- No dispatch ever pairs a routed model with a different vendor's runner.
- Provider-less dispatch routes like provider-ful dispatch.
- A transiently unavailable incumbent falls back to a configured, deterministic,
  operator-allowlisted choice.
- A routed selection never crosses the `local` trust boundary.

**Non-goals**
- Falling back on permanent mismatches (D3).
- Using evidence to pick the fallback; evidenced alternatives already win via
  `incumbent-infeasible-evidenced-alternative`, which is unchanged.
- #636 item 4 (attribution), which is decided and lives in #612.
- Changing the offline client path (`routing_fallback.py`) beyond parsing and validating the
  new `vendor_order` key. It stays same-provider; it never performs a cross-vendor move.
- Changing the pre-existing behavior that a permanently excluded incumbent, kept with
  `selected: null`, is still dispatched statically by the client.
- Guarding against a fallback landing in a worse cost tier than the incumbent's lane (D4
  states the precedence; the owner accepted the trade-off).

## Decisions

### D1: Phase 1 (dispatch) lands before phase 2 (fallback), and the runner contract carries `provider`

The phase 1 changes are prerequisites and independently correct:
- `run_phase_subagent` and `make_phase_callback` gain `provider: str | None = None`, threaded
  to `_build_options(phase, state_dict, provider=_selected_provider(provider))`, so an
  explicit caller provider and the env path both make the incumbent provider-ful (today the
  path is env-only). `run_phase_subagent` then writes
  `options["provider"] = state_dict.get("_resolved_provider") or selected_provider`, the same
  key and precedence `build_phase_dispatch_kwargs` already uses for the payload.
- The runner contract becomes: a `SubagentRunner` MUST dispatch to `options["provider"]`
  through the provider-neutral adapter (`provider_dispatch`). A runner that cannot serve that
  provider MUST raise `phase_agent.UnservableProviderError(provider, supported)` rather than
  run the model under its own vendor; the raise takes the existing failure path (`phase_agent`
  D8: retry budget, then `PhaseEscalationError`). The mismatched pair is never produced.
  `phase_agent.py` ships a reference adapter, `claude_agent_runner(agent_fn, supported=
  {"claude_code"})`, that wraps the harness `Agent(...)` callable and raises on any other
  `options["provider"]`; it is the runner the SKILL.md Claude blocks describe, and the one
  tests exercise.
- `smoke_provider_dispatch` builds the pair from the resolved provider and model, re-runs the
  Claude-alias and `local` trust-boundary checks against the **resolved** provider, picks the
  smoke phase from the caller's provider (that is what the smoke exercises), and reports both:
  the JSON body and the text line keep `provider` (the caller's) and add `resolved_provider`.
- The autopilot SKILL.md adapter contract names `provider` in the 8-phase protocol block and in
  each of the seven per-phase "Capture `prompt`, `model`, `isolation`" dispatch blocks, with
  the rule: a harness whose only adapter is `Agent(...)` MUST route a non-`claude_code`
  provider through the provider adapter or escalate; it never calls `Agent(...)` with another
  vendor's model. A prose-guard test, `skills/tests/autopilot/test_skill_dispatch_provider_prose.py`
  (modelled on `test_prose_free_gates.py`), asserts every capture line after a
  `build-dispatch` call names `provider` and that the count of such blocks is seven.
- `build_phase_dispatch_kwargs` already honors `_resolved_provider`; it gains a regression
  test and no behavior change.

They touch only `skills/`, so they can merge ahead of the contract chain. Phase 2 must not
merge before phase 1, because a cross-vendor fallback over unfixed dispatch produces
mismatched model/vendor pairs.

### D2: The default provider is resolved before resolution, and it is the same default

`_selected_provider()` returns `claude_code` when no explicit provider and neither
`AUTOPILOT_PROVIDER` nor `AGENT_TYPE` is set, or when the env value is whitespace only: the
value `build_phase_dispatch_payload` already applies *after* resolution. Its return type
narrows from `str | None` to `str`; the callers that branch on `None`
(`build_phase_dispatch_kwargs`'s `dispatch_provider`, `build_phase_dispatch_payload`'s
post-resolution default) keep working and the latter becomes unreachable-by-default but stays
as a guard.

What changes for provider-less callers:
- The **model** becomes the default provider's concrete mapping of the archetype tier.
  Today `resolve_provider_model_spec` passes the tier alias through when `provider` is falsy,
  so the payload carried `model: "standard"`; with the default applied first it carries the
  `claude_code` alias for that tier (`standard` → `sonnet`, per `archetypes.yaml`
  `model_aliases`). The **provider** is unchanged (`claude_code` either way).
- The incumbent becomes a concrete `(vendor, model)`, so every routing outcome that needs one
  becomes reachable — `challenger-evidenced-above-margin`, `exploration-evidenced`,
  `incumbent-infeasible-evidenced-alternative` and the new configured fallback. Before, such
  runs always ended `incumbent-unresolved`.
- With routing off, or with a retained incumbent, the dispatched provider is the one it
  already was and the model is the concrete alias above. A non-Claude harness that wants
  another default must set `AGENT_TYPE`, as today.

### D3: The fallback fires only on transient availability exclusions

Transient set (the trigger): `lane:unavailable`, `unavailable`, `quota:exhausted`,
`lane:model-rate-limited`.

Permanent set (keeps `incumbent-infeasible-no-evidenced-alternative`, `selected: null`):
- `lane:archetype-ineligible`, `lane:dispatch-mode-ineligible`, `lane:not-dispatchable`;
- `lane:location-mismatch`, `lane:isolation-mismatch`;
- `roadmap:*`, `cedar:*`, `cost-policy:unclassified`;
- `catalog:no-configured-lane`, `registry:no-catalog-projection`.

This list is authoritative; the proposal and the spec cite it rather than restating it.
Any reason string outside both sets is treated as permanent.

Rationale: a permanent mismatch is a contradiction between the operator's static
configuration for the phase and the lane policy (roster, roadmap, location, isolation). The
router surfaces it unchanged instead of guessing which side the operator meant. Note that
the fallback candidate itself always passed the full feasibility and policy filter, so
falling back would not bypass policy; the pre-existing static dispatch of a permanently
excluded incumbent is a client behavior this change leaves alone (non-goal).

Precedences and classification rules:
- `cost-policy:lower-priority-tier` on the incumbent keeps its existing path: `api.py` sets
  `incumbent_below_cost_tier` and routes through plain `choose()` before retention runs, so
  the fallback never sees such a request, even if other incumbent rows are transient.
- Exclusion reasons are carried into retention as `(vendor, model) → {reasons}`, built once
  per request from both exclusion sources. An incumbent with several excluded rows is
  transiently unavailable only if **every** row's reason is transient; a mixed set counts as
  permanent.
- Classification uses the reported reason. Because `_lane_exclusion_reason` reports the first
  failing check and availability is checked first, a lane that is both down and
  policy-excluded reads as transient and may fall back. That is safe: every fallback
  candidate passed the full policy filter, and the recorded reason is what the router
  actually observed. The masked case is a tested, documented behavior rather than a second
  reason pass.
- The fallback requires lane assignments: it is **disabled** (today's behavior) when the
  service runs without `_assignment_enabled` or without a loaded `RoutingPolicy` whose
  document carries `fallback`. When it is enabled, a candidate that has no `assignment` is
  simply **ineligible** (skipped); the other candidates are still ordered.

### D4: The order lists are allowlists; the pick is lexicographic over them with `agent_id` as the final tie-break

Sort key, ascending, over the eligible candidates:
`(vendor_order.index(assignment.vendor_type), location_order.index(assignment.location),
isolation_order.index(assignment.isolation), dispatch_mode_order.index(assignment.dispatch_mode),
assignment.agent_id)`.

- **Eligibility.** A candidate is eligible only if it is feasible (in `ranked`), is not one of
  the incumbent's own rows, and every one of its four attributes is enumerated in the
  corresponding list. A vendor type absent from `vendor_order` is **not** a fallback target.
  This is the same exclusion rule `local_static_route` applies to the three existing lists,
  and it makes `vendor_order` the operator's allowlist: listing `[codex]` cannot yield a pick
  of `grok`, `pi` or `local`.
- `vendor_type` is the agent type from `agents.yaml` (`assignment.vendor_type`), not the
  catalog vendor; `pi-local` has `type: pi` but `catalog_vendor: openrouter`.
- Score and RNG are never consulted. Identical catalog, config and availability give the
  identical pick (NFR determinism).
- The three existing lists are already Literal-typed and ship fully enumerated, so in
  practice only `vendor_order` restricts.
- Cost-policy filtering runs before retention (existing), so the eligible pool is the best
  cost tier among the *remaining* feasible candidates. When the incumbent's lane was the
  only subscription-tier option, that pool can be a metered tier. This is the owner's option-B
  trade-off; the tier is derivable from the persisted `selected.assignment`
  (`location`, `endpoint_kind`), so it is auditable without a new field.
- Implementation note: build the `(vendor, model) → {reasons}` map and the `value → index`
  maps once per request from the already-loaded `RoutingPolicy.document`; no second registry
  call, no re-parse of `routing.yaml`.

### D5: No `vendor_order` means no fallback

`FallbackOrder.vendor_order: list[str] | None = None`. When present it MUST be non-empty,
entries unique and non-empty strings. The trigger requires it to be present; with it absent,
behavior is exactly today's, so the change is opt-in by config.

The shipped `agent-coordinator/routing.yaml` keeps the key **absent**, with a commented
example listing the agent types in `agents.yaml`; the owner populates it at implementation
review. Shipping the key absent, rather than empty, keeps the file loadable by any installed
skill copy or deployed coordinator that predates this change (both parsers reject unknown or
empty keys), so there is no install-order hazard.

Validation split: the server validates shape only (it has no `agents.yaml` at policy load).
On the client, `routing_fallback.load_routing_policy_document(repo_root)` gains the check: when
`fallback.vendor_order` is present it reads `agents.yaml` via `_agents_yaml_path(repo_root)`
and raises `ValueError("fallback.vendor_order names unknown agent type <x>")` for an entry that
matches no agent `type`. The loader test fixture builder gains an `agents.yaml` so the
populated-key case is covered; the shipped file ships the key absent, so the check guards the
owner's later edit, not the initial state. The `routing.yaml` edit is the last step of task
3.2, after both parsers accept the key.

### D6: A new retention reason, `retained: false`, in a v1.4 overlay

`incumbent-infeasible-configured-fallback` is a routed selection, not a kept one, so the
client follows it to the new provider through the dispatch path D1 fixes.

- `RetentionDecision` gains `fallback: RetentionFallback | None`, and `_retain_incumbent`
  copies it into the persisted `retention` payload. The record is
  `retention.fallback = {incumbent_exclusion_reasons, order_applied}`:
  `incumbent_exclusion_reasons` is the sorted, unique set of the incumbent's excluded-row
  reasons (all transient by D3; one lane may be `lane:unavailable` while another is
  `quota:exhausted`); `order_applied` is a **verbatim copy** of `policy.document.fallback`:
  all four lists, each non-empty and duplicate-free.
- Both schemas enforce presence and shape: `retention.fallback` is required when `reason` is
  the configured fallback and forbidden otherwise, and that reason implies `selected` is an
  object (a configured fallback is never a null selection).
- The response's top-level `fallback: bool` keeps its existing meaning (offline local-static
  route) and stays `false` for a configured fallback.
- Exploration cannot disturb the pick: the trigger requires that no feasible challenger is
  evidenced, so `choose_evidenced` sees fewer than two evidenced candidates and returns the
  fallback unchanged. This invariant is asserted by a test rather than assumed.
- The v1.4 overlay builds on `split-no-evidence-retention-reason`'s v1.3; the archived v1.2
  and the pending v1.3 stay untouched (D7 of `retain-static-model-until-routing-evidence`).
  v1.4 also widens the `ExcludedAssignment.reason` pattern to the `cost-policy:` prefix that
  `api.py` already emits; this is a pre-existing drift carried in v1.2/v1.3 and is listed in
  the contracts README as a v1.4 difference.
- There is no migration: `retention` is JSONB with no CHECK on its contents.

### D7: A routed selection onto `local` respects the trust boundary, in the router first

Two layers, both in the coordinator:

1. **Primary, at lane projection.** `vendor_registry._lane` advertises, for an agent whose
   `type` is `LOCAL_PROVIDER`, only `archetypes ∩ LOCAL_TRUSTED_ARCHETYPES`. The router then
   excludes such a lane for an untrusted archetype with the existing
   `lane:archetype-ineligible` (`_lane_exclusion_reason` already checks the request's
   archetype against the lane's list), so a `local` lane is never a feasible candidate, never
   a challenger and never a fallback target for an untrusted archetype. The persisted decision
   therefore matches what is dispatched: no attribution gap of the kind that ruled out
   Approach 2.
2. **Guard, at resolution.** `resolve_archetype_for_phase` applies the static path's check to
   `_routed_provider(selected)` (which derives `local` from `assignment.vendor_type` or, with
   no assignment, from the catalog vendor): when it is `local` and the archetype is untrusted,
   resolution returns `dataclasses.replace(static, reasons=[*static.reasons, "adaptive routing
   refused: provider=local outside LOCAL_TRUSTED_ARCHETYPES (archetype=<name>)"])` and logs a
   warning. This is defense in depth; if it ever fires, layer 1 has a bug. The scenario asserts
   equality with the static resolution plus that reason, not object identity.

This closes a pre-existing gap for evidenced challengers as well; the fallback is what makes
it reachable during a vendor outage, so it ships here. The operator additionally controls
whether `local` is ever a fallback target through `vendor_order` (D4).

### D8: wp-router is held until v1.3 merges

The operator approved this change on 2026-10-10 with the condition that only `wp-dispatch`
runs now and `wp-router` waits for `split-no-evidence-retention-reason` (v1.3) to merge. The
hold is recorded in `work-packages.yaml` (`inputs.hold`, `inputs.external_prerequisites` on
`wp-router`; `metadata` is closed by the schema, `inputs` is the open extension point), in the
package description, in tasks.md, and as task 2.0, which is the package's first step and the
dependency of both the 2.x and the 3.x chains. Task 2.0 proves the merge rather than a file's
presence: it resolves the v1.3 change with `change_dir()` (active or archived), requires the
feature branch to contain `origin/main`, compares the **blob hashes** of the three v1.3
contract files with the ones pinned in the contracts README (a squash merge keeps blob hashes
but not commit SHAs), and asserts the v1.3 code is present (`"no-evidenced-challenger"` in
`api.RetentionReason`). A dispatcher that reads only `depends_on` MUST NOT be used to start
wp-router; the orchestrator checks the hold before dispatch.

## Risks / Trade-offs

- **Contract chain dependency.** v1.4 needs v1.3 first, and v1.3 waits on the task-router
  change. Phase 1 is independent of that chain, so the most important correctness fix doesn't
  wait. The v1.3 the overlay was derived from is pinned by SHA in the contracts README; task
  2.0 regenerates and diffs if it moved.
- **A configured order can name a vendor whose model is weaker, or a metered lane.** That is
  the explicit trade-off the owner chose: an available, human-chosen model over a
  known-failing one. The reasons and the order are persisted, so this is auditable.
- **Allowlist strictness.** A candidate whose vendor type the owner did not list is never a
  fallback target even if it is the only feasible one; the request then keeps today's
  `incumbent-infeasible-no-evidenced-alternative`. This is the intended "human-chosen" rule.
- **Masked reasons.** A lane that is both down and policy-excluded falls back. Accepted
  because fallback candidates are policy-filtered; the alternative (a second reason pass over
  the incumbent's lanes) adds a code path for no safety gain.
- **#647's displaced-incumbent rule does not apply here.** Exploration is not involved: the
  fallback pick is deterministic and the incumbent is infeasible anyway.
- **Scope growth for D7.** `agents_config.py` and `vendor_registry.py` join wp-router's scope
  for a few lines each and their tests. Kept in this change because the fallback creates the
  production exposure.
- **`install.sh --check` cannot run inside an isolated package worktree.** It diffs `skills/`
  against the gitignored `.claude/skills` and `.agents/skills` mirrors, which an isolated
  worktree does not have. It is therefore not a per-package verification step; task 4.2 runs
  it from the feature worktree after `install.sh --mode copy --force --deps none
  --python-tools none`, and the validation phase repeats it.
- **The plan was written against a branch behind `main`.** The named router files are
  unchanged on `main`; `phase_agent.py` and `agents_config.py` gained unrelated code. Each
  package rebases onto `main` before its first commit and re-anchors the cited lines.
