# Plan Findings: add-infeasible-incumbent-fallback

> Structured quality findings from `/iterate-on-plan` cycles. Each iteration appends a section.
> Criticality: critical > high > medium > low. Threshold for this run: medium.

## Iteration 1 (2026-10-10T21:30Z, architect archetype, coordinated tier)

Baseline: `openspec validate --strict` passes; `validate_work_packages.py` VALID. Findings below come
from three parallel dimension analysts (completeness/consistency, feasibility/testability,
security/assumptions) merged with the orchestrating architect's own read of the code the plan names.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | feasibility | critical | Task 1.4 "pass `_resolved_provider` to its runner" names no mechanism. `SubagentRunner` is `(prompt, options)` (`phase_agent.py:175,221`); `run_phase_subagent`/`make_phase_callback` have no provider parameter and `_build_options` is called provider-less (`:217`). Nothing says what a runner does when it cannot serve the routed provider, which is exactly the cross-vendor case D1 protects against. | D1 now fixes the mechanism: `options["provider"]` (same key `build_phase_dispatch_kwargs` emits), runners dispatch through the provider-neutral adapter, and a runner that cannot serve `options["provider"]` MUST raise, never run the model under its own vendor. New scenario agent-archetypes.7; tasks 1.3/1.4 rewritten. |
| 2 | consistency | critical | D4 claims the server sort is "identical to the client-side sort" and that missing values "sort after every listed value". The client (`routing_fallback.py:622,651-662`) only considers lanes of the static provider and *drops* lanes whose attribute is not enumerated. `vendor_order` can never change the client pick. Tasks 3.1/3.2 "same semantics" cannot hold. | D4 restated: all four lists are allowlists (a candidate must be enumerated in every list), which matches the client's exclusion rule. The client path stays same-provider; it parses and validates `vendor_order` with the shared rules but applies no cross-vendor move (explicit non-goal). Task 3.1 narrowed. |
| 3 | security | critical | `vendor_order` was a preference order with unlisted vendors sorting last (D4), unvalidated. A typo or a list of `[codex]` still let grok, pi or `local` be picked via `location_order`, which puts `local` first. | `vendor_order` is an allowlist of agent types (`assignment.vendor_type`): only listed vendors are fallback-eligible. Entries unique and non-empty; the client loader (which has `agents.yaml`) rejects unknown types, so the shipped file is CI-checked. D4/D5 and the spec updated; tests in 3.1/3.3. |
| 4 | security | high | A routed selection that lands on the `local` provider skips `LOCAL_TRUSTED_ARCHETYPES`: the coordinator checks it only when the *caller's* provider is local (`agents_config.py:2606-2612`), not on the routed result (`:2836-2858`). `smoke_provider_dispatch` keys the same check on the input provider (`:98-112`). Pre-existing for evidenced challengers; the fallback makes it reachable in a vendor outage. | New D7: `resolve_archetype_for_phase` re-applies the trust boundary to any routed provider and returns the static resolution (with a reason) when it fails; smoke re-runs its checks against the resolved provider. New scenario agent-archetypes.9, task 3.8, `agents_config.py` added to wp-router scope and locks. |
| 5 | feasibility | high | The D4 sort key needs `assignment.{vendor_type,location,isolation,dispatch_mode,agent_id}`; `ScoredCandidate.assignment` is `None` when `_assignment_enabled` is false (`api.py:440`, `resolver.py:136`). `apply_incumbent_retention` is pure and receives no policy. Task 3.2 "make the coordinator load the fallback block" is already done (`routing_policy.py:131`). | D3/D4: the fallback requires lane assignments and a loaded `RoutingPolicy`; otherwise today's behavior. 3.2 reworded to "pass `policy.document.fallback` into retention"; 3.3 gains both cases. |
| 6 | consistency | high | Proposal says routing.yaml "ships with an order the owner reviews"; D5 says it "starts empty" yet requires non-empty to trigger. `FallbackOrder` is `extra="forbid"` with `min_length=1` siblings (`routing_policy.py:22,79-82`); the client rejects unknown fallback keys (`routing_fallback.py:82,303`), so an installed-but-stale skill copy would stop loading the policy. | D5: `vendor_order: list[str] \| None = None`; absent disables. The shipped `routing.yaml` keeps the key **absent** with a commented example; the owner populates it at implementation review. The routing.yaml edit is the last step of 3.2, after both parsers accept the key; wp-router verification adds the coordination-bridge skill tests and `install.sh --check`. Proposal and D5 now agree. |
| 7 | consistency | high | `retention.fallback.incumbent_exclusion_reason` is a single enum value, but D3 allows several transient rows with different reasons (`lane:unavailable` on one lane, `quota:exhausted` on another) and nothing says which is recorded. | Contract field becomes `incumbent_exclusion_reasons`: the sorted, unique set of the incumbent's row reasons (`minItems: 1`). v1.4 OpenAPI, record schema, `models.py`, README, D6 and the spec AND clause updated. |
| 8 | completeness | high | Spec model-routing.8 omits D3's every-row-transient rule. Two precedences are undocumented: `incumbent_below_cost_tier` (`api.py:615-620`) sends the request to plain `choose()` before retention, and `_lane_exclusion_reason` reports only the first reason, availability first (`resolver.py:376-407`), so a lane that is both down and roadmap-excluded reads as transient. | Scenario WHEN now states the every-row rule. D3 documents the cost-tier precedence and the reported-reason classification, and why it is safe (every fallback candidate passed the full policy filter). 3.3 tests the masked case. |
| 9 | assumptions | high | D3's rationale "a fallback must not route around policy" is backwards: the fallback candidate always passes every policy filter, while keeping static dispatches the very incumbent the policy excluded (pre-existing). | D3 rationale rewritten: a permanent mismatch is a contradiction between the static configuration and lane policy, surfaced rather than guessed around; the static dispatch of a permanently excluded incumbent is pre-existing and an explicit non-goal. |
| 10 | scope | high | The operator's hold ("wp-dispatch only this run; wp-router waits for the v1.3 merge") exists only in prose. `work-packages.yaml` has `depends_on: ["wp-dispatch"]`, so a DAG dispatcher starts wp-router as soon as wp-dispatch completes. v1.3 is not in this tree. | wp-router carries `inputs.hold` and `inputs.external_prerequisites` (`metadata` is schema-closed), the package description opens with the hold, tasks.md and proposal Sequencing state it, and task 2.0 fails fast when v1.3 is absent from `openspec/changes/`. |
| 11 | consistency | medium | The contracts do not enforce that `fallback` is present exactly when the reason is the configured fallback (description only, `v1.4.yaml:587`, record schema `:111`); the record schema title still says v1.2; `ExcludedAssignment.reason` pattern (`v1.4.yaml:436`) cannot carry the `cost-policy:` prefix `api.py:602-604` emits; top-level `fallback: bool` (offline route) vs `retention.fallback` is ambiguous. | Both schemas gain `if reason == configured-fallback then required [fallback] else fallback absent`; title bumped; `cost-policy` added to the pattern (recorded in README as a v1.4 difference); D6 and the spec state top-level `fallback` stays `false`. 2.1 gains negative tests; 3.5 asserts top-level `fallback`. |
| 12 | completeness | medium | `agent-coordinator/CLAUDE.md` (reason list, `:296-297`) is in wp-router `write_allow` with no task. NFR "Observability … Integration test on the migrated DB" names `fallback_order` and has no producing task; `test_fresh_database_migration.py` is in `write_allow` though there is no migration. | Task 3.7 updates the reason list. NFR re-pointed to the 3.5 service-level persistence test and renamed to `order_applied`; the migration test path dropped from `write_allow`. |
| 13 | feasibility | medium | Task 1.5 [XS] underestimates `smoke_provider_dispatch`: the caller's provider picks the smoke phase, gates the `local` trust boundary and the Claude-alias check (`:74-75,84,98-113,127`). Switching only the dispatch pair would skip those for a resolved `local`. | 1.5 sized [S]: re-run alias and trust checks against the resolved provider; report caller and resolved provider. 1.3 covers routed-to-local and routed-away-from-local. |
| 14 | assumptions | medium | D2 says provider-less behavior changes "in exactly one way", but a concrete incumbent newly enables `challenger-evidenced-above-margin`, `exploration-evidenced` and the fallback. `_selected_provider` changes from `str \| None` to `str`, affecting callers that branch on `None` (`phase_agent.py:1039,1108`). | D2 restated with the newly enabled outcomes and the caller audit; task 1.2 names the callers. |
| 15 | completeness | medium | `_retain_incumbent` rebuilds `retention` from four fixed fields (`api.py:770-775`), so `retention.fallback` is lost unless `RetentionDecision` carries it; the invariant that `choose_evidenced` cannot disturb a fallback pick (no evidenced challenger ⇒ `others` empty) is implicit. | D6: `RetentionDecision.fallback` carries the record; tasks 3.4/3.6 thread it. 3.3 asserts `allow_exploration=True` leaves the pick and reason unchanged. |
| 16 | testability | medium | Task 2.1 cites "the reason-parity check (from item 5)" without naming it; v1.3 exists only on `origin/openspec/split-no-evidence-retention-reason` (`e832cff5`), so the parity test and line targets move. | Task 2.0 (gate): rebase onto merged v1.3, record its SHA in the contracts README, regenerate v1.4 and diff. The parity test is named (`split` task 1.2: `RetentionReason` Literal equals the enum). |
| 17 | parallelizability | medium | In wp-dispatch, 1.2 and 1.4 both edit `phase_agent.py` with no dependency; 1.1 and 1.3 likely share `test_build_options.py`. 2.2 and 3.4 both define the reason set. | 1.4 depends on 1.2; 1.3 gets its own test module; 3.4 asserts the `RetentionReason` Literal equals the v1.4 enum. |
| 18 | consistency | low | agent-archetypes.8 WHEN is narrower than the behavior (permanent exclusions and transient-without-candidate also keep static); 4.1 tests only two branches. | WHEN reworded to "the configured-fallback scenario does not apply"; 4.1 adds the permanent case. |

Deferred, out of scope (recorded, not expanded):
- Metered-tier drift: cost-tier filtering runs before retention, so a fallback pool can be a worse tier than
  the incumbent's lane. Accepted as the owner's option-B trade-off; the tier is derivable from the persisted
  `selected.assignment` (location, endpoint_kind). Stated in D4; no new contract field.
- Static dispatch of a permanently excluded incumbent is pre-existing behavior (D3 non-goal).

Parallelizability (after fixes): `Independent: 4 (1.1, 1.3, 2.1, 3.1) | Sequential chains: 3
(1.1→1.2→1.4→1.6, with 1.3→1.4 and 1.3→1.5; 2.0→2.1→2.2→3.4; 3.1→3.2→3.3→3.4→3.5→3.6→3.7/3.8→4.1→4.2) |
Max parallel width: 2 within wp-dispatch (1.1‖1.3), 2 within wp-router (2.x‖3.1–3.3); wp-router runs
strictly after wp-dispatch and only after the v1.3 merge.` File-overlap: every pair touching
`phase_agent.py`, `api.py`, `resolver.py` is now explicitly serialized.

## Iteration 2 (2026-10-10T22:10Z, architect archetype, coordinated tier)

Re-review of the iteration-1 result by two fresh analysts (consistency; feasibility/testability).
`openspec validate --strict` and `validate_work_packages.py` passed before and after.

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | testability | high | agent-archetypes.5 claimed provider-less dispatch keeps "provider and model" with the flag off, but `resolve_provider_model_spec` passes the raw tier through when `provider` is falsy (`agents_config.py:2321`), so applying `claude_code` first maps `standard` → `sonnet`. Scenario .1 was also over-broad for provider-less callers. | D2 and both scenarios state the model change explicitly; 1.1 asserts `standard` → `sonnet` and the provider-unchanged invariant. |
| 2 | feasibility | high | Task 2.0 checked a literal `openspec/changes/split-…` path (moves to `archive/` on cleanup) and "SHA matches" a branch commit that a squash merge never preserves. | 2.0 resolves the change with `change_dir()`, requires `origin/main` as ancestor, compares `git hash-object` blob ids pinned in the README, and asserts the v1.3 code (`no-evidenced-challenger`) is present. 3.1 now depends on 2.0 so both chains are gated. |
| 3 | feasibility | high | `install.sh --check` diffs `skills/` against gitignored mirrors absent in an isolated package worktree, so the per-package step fails as written. | Removed from both packages' verification; task 4.2 runs it from the feature worktree after `install.sh --mode copy --force --deps none --python-tools none`; recorded in design Risks. |
| 4 | consistency | medium | D7's resolution-time guard persisted a routed `local` decision while dispatching static: the attribution gap used to reject Approach 2. | D7 now enforces in the router first (`vendor_registry._lane` advertises `archetypes ∩ LOCAL_TRUSTED_ARCHETYPES` for `local` agents, so the lane is `lane:archetype-ineligible`), keeping the guard as defense in depth applied to `_routed_provider(selected)`, with the exact refusal reason string and equality (not identity) semantics. `vendor_registry.py` joins wp-router scope. |
| 5 | consistency | medium | `order_applied` left three lists optional and `vendor_order` without `uniqueItems`, so two different implementations validated. | All four lists required, non-empty, unique in v1.4 OpenAPI, record schema and `models.py`; D6 says "verbatim copy of `policy.document.fallback`". |
| 6 | completeness | medium | Task 1.4 "call `_build_options` with the selected provider" was implementable two ways (env-only vs new kwarg). | D1/1.4: `provider: str \| None = None` on `run_phase_subagent` and `make_phase_callback`; 1.3 tests explicit and env paths. |
| 7 | testability | medium | agent-archetypes.7 named no exception type and no runner exists to test. | `UnservableProviderError` and the reference adapter `claude_agent_runner(agent_fn, supported={"claude_code"})` are defined in D1; 1.3 tests the adapter and escalation. |
| 8 | ambiguity | medium | "Every considered candidate must have an assignment" (D3) vs "at least one … has an assignment" (spec). | A candidate without an assignment is ineligible (skipped); the fallback is disabled only when assignments are disabled. D3, 3.3 and model-routing.8 aligned. |
| 9 | feasibility | medium | D5 said "the client loader" rejects unknown vendor types but did not name the function or error, and `load_routing_policy_document` does not read `agents.yaml`. | D5/3.1/3.2 name `load_routing_policy_document`, the `_agents_yaml_path` read (only when the key is present) and the `ValueError` text; the fixture builder gains a populated-key case. |
| 10 | testability | medium | wp-dispatch verification ran only `skills/tests/autopilot`, while 1.4/1.5 are covered by `phase-record-compaction/test_phase_agent.py` and `vendor-neutral-autopilot/test_smoke_provider_dispatch.py`; smoke output keys were unnamed. | Both directories added to verification and `write_allow`; smoke keeps `provider` (caller) and adds `resolved_provider`. |
| 11 | completeness | low | Contracts did not enforce that the configured-fallback reason implies a non-null `selected`. | Conditional added to `SelectModelResponse` and the record schema; negative test in 2.1. |
| 12 | consistency | low | model-routing.9's allowlist clause was vacuous (selected already null); 1.6's prose guard named no file or block-identification rule; test files for 2.1/3.1/3.3/3.5/4.1 unnamed; parity assertion claimed by both 2.1 and 3.4. | Clause moved to .8; `test_skill_dispatch_provider_prose.py` modelled on `test_prose_free_gates.py` with an expected count of seven blocks; every test task names its module; 2.1 owns parity. |

Deferred (unchanged from iteration 1): metered-tier drift; static dispatch of a permanently excluded
incumbent.

Parallelizability (after fixes): `Independent: 4 (1.1, 1.3, 2.0, 3.1 after 2.0) | Sequential chains: 3
(1.1→1.2→1.4→1.6 with 1.3→1.4 and 1.3→1.5; 2.0→2.1→2.2→3.4; 2.0→3.1→3.2→3.3→3.4→{3.5→3.6, 3.7, 3.8}→4.1→4.2)
| Max parallel width: 3 (3.5 ‖ 3.7 ‖ 3.8 after 3.4; 2 in wp-dispatch) | File-overlap conflicts: none
unserialized (phase_agent.py 1.2→1.4; api.py/resolver.py 3.4→3.6; test modules named per task).`

Residual findings at or above medium after iteration 2: 0 (all 10 fixed; 2 low fixed as well).

## Vendor Review (2026-10-10T21:37Z) and Remediation Cycle

Dispatch: antigravity, codex, grok, pi (claude_code excluded as primary; quorum 4/2). Results:
codex OK (gpt-5.6-sol, 359 s, 10 findings); antigravity timeout at 500 s; grok failed (CLI 1.0.5
rejected with HTTP 426, needs 1.0.13); pi reported as failed by the dispatcher because it wrote
`review_findings.json` to the repository root instead of the output directory — that file was
removed as a stray artifact before its contents were fully read (its first finding, "scenario .8
omits the cost-policy precedence", is already covered by the WHEN clause). The dispatcher marked
the phase DEGRADED (1 of 2 required vendors). Consensus (`reviews/consensus-plan.json`) over the
primary findings (4 low, accept) and codex: 14 findings, 0 confirmed, 14 unconfirmed, 0 blocking.

Per the single-vendor-criticals rule, each codex finding was adjudicated by the orchestrator
against the documents and code rather than dropped or auto-escalated:

| Codex # | Criticality | Verdict | Action |
|---|---|---|---|
| 1 GATEKEEPER block left provider-less | critical | Valid: the GATEKEEPER block follows a `build-dispatch` call and says "prompt/model" only; the prose test counted seven blocks | D1 and task 1.6 cover all eight `build-dispatch` blocks; the test counts eight |
| 2 Event schema lacks reason⇒selected conditional | high | **Rejected**: the record schema's top-level `allOf` already carries the conditional (added in iteration 2; third entry) | None; noted here as evidence |
| 3 Generated model: no retained/reason parity; explicit `fallback: null` accepted | high | Valid | `Retention` gains a parity validator; presence validator uses `model_fields_set` so explicit null is rejected; 2.1 gains the negative cases |
| 4 OpenAPI: configured fallback does not pin top-level `fallback: false` | high | Valid | Conditional extended; 2.1 negative test; record schema already has `fallback: const false` |
| 5 Hold not enforced by the work-package graph | critical | Valid: the scheduler derives readiness from `depends_on` only and the schema has no hold field | `wp-router` moved out of `work-packages.yaml` into `work-packages.held.yaml` (schema-valid, loaded by nothing); task 2.0 promotes it; D8 rewritten |
| 6 Task 2.0 checks the working tree, not `origin/main`; wp-dispatch merge unproven | critical | Valid | 2.0 reads blobs with `git rev-parse origin/main:<path>`, uses `git grep` on `origin/main` for the v1.3 and wp-dispatch markers |
| 7 Scope denies `openspec/changes/archive/**` that 2.0 must read | high | Valid as written; moot once 2.0 reads the git object store | 2.0 reads from `origin/main` via git; D8 notes the deny governs the working tree |
| 8 wp-router verification omits ruff and the feature-level checks | medium | Valid in part: ruff was missing; the skill suites and install check are feature-level by design | `ruff_clean` step added to the held manifest; 4.2 restated as the feature-level gate run by the validation phase |
| 9 Sortedness enforced only by the generated model | medium | Valid | Sorting defined as a producer invariant (asserted in 3.5); all three contracts validate uniqueness only; D6, README, spec aligned |
| 10 Resolver-unavailable scenario unqualified for provider-less callers | medium | Valid | agent-archetypes.2 qualified like .1; 1.1 covers it |

Remediation cycle: one iterate pass (no re-dispatch), committed as `refine(plan): vendor-review
remediation`. Residual findings at or above medium after remediation: 0.

## PLAN_REVIEW convergence, pass 1 (2026-10-10T22:03Z, reviewer archetype, `converge()`)

Engine: `convergence_loop.converge()` (plan, quorum 2, max 3 rounds, fact-check on). Panel:
`claude-local` (fable, 169 s, 10 findings) and `codex-local` (gpt-5.6-sol, 76 s, 5 findings);
antigravity (500 s print timeout), grok (CLI 1.0.5, HTTP 426) and pi (writes findings to cwd) were
left out of the panel on the evidence of the earlier dispatch. Two dispatcher defects had to be
worked around in the driver: the 230 KB review packet exceeds the 128 KB single-argv limit
(codex now takes the prompt on stdin), and codex echoes the prompt to stderr, where a literal
`401` in the packet made `classify_error` label a valid findings payload `auth_required`.
Fact-check removed nothing. Consensus: 15 unconfirmed, 0 blocking (every finding judgment-class,
single-vendor); `converge()` returned `adjudication_required` for the four single-vendor
high/critical items, adjudicated here against the documents and the code (#550 rule):

| Ledger # | Vendor | Criticality | Verdict | Action |
|---|---|---|---|---|
| 11 (= claude #1) | codex | critical | Valid: a task of the held package cannot promote the package, since no scheduler loads the held file | Promotion is tasks.md step P0 (operator/orchestrator, feature worktree, after wp-dispatch merges); 2.0 is the in-package fail-fast re-check; D8, held manifest, proposal Sequencing, README aligned |
| 12 | codex | high | Valid for the record schema (`persistedRequest.incumbent` exists; v1.3 required `retention` only for a null `selected`); not expressible in `SelectModelResponse`, which carries no request | Record schema gains `request.incumbent object ⇒ retention required` (README difference 4, D6 bullet, 2.1 test case); the response-level rule stays the `api.py` invariant asserted by 3.5 |
| 13 | codex | high | Valid: `apply_incumbent_retention` reaches the infeasible branch only with `matches` empty and the key in `excluded_identities`; scenario .8 never said so | .8 WHEN states "infeasible: no feasible row, at least one excluded row" plus an AND clause; D3 precondition paragraph; 3.3 test bullet |
| 15 (= claude #6) | codex | high | **Rejected**: the module is `agent-coordinator/tests/model_routing/test_resolver.py`, inside `agent-coordinator/tests/model_routing/**` and run by the "Model-routing suite" step | 3.8 spells the full path so the next reviewer does not guess |

Also fixed in the same pass, on the cited files only: requirement/scenario disagreement on
provider-less callers (codex #14, claude #9); README gate paragraph still describing a
working-tree check (claude #3); proposal claims of online/offline agreement and "no behavior
change" for `routing_fallback.py` (claude #4, #5); D1 citing a foreign "D8" (claude #10); "replace
the packages list" losing the wp-dispatch record (claude #1). Left open as advisory: the
decision-timeline index (claude #2, generated artifact), the historical review JSON (claude #7),
and the retry-budget consumption on `UnservableProviderError` (claude #8, pre-existing path).

## PLAN_REVIEW convergence, pass 2 (2026-10-10T22:14Z)

Delta round on the pass-1 fix commit (`9ff51335`): claude-local returned 8 findings (192 s);
codex returned a findings payload that failed schema validation and, because this change's
vocabulary (`quota:exhausted`, `lane:model-rate-limited`) matches the dispatcher's capacity
patterns, `classify_error` labelled it `capacity_exhausted` instead of sending the repair prompt,
so quorum was lost (1/2) before synthesis. The driver now treats a body that parses as a
findings object as never an error body, which restores the repair path. Claude's eight findings
never reached the ledger, so they were fixed ahead of pass 3 on the cited files: 2.1's parity
case is `xfail` until 3.4 (#1, medium); Risks said "task 2.0 regenerates" (#2); P0 moved to its
own non-package section and the section-4 heading names 4.2's owner (#3); new scenario
agent-archetypes.11 anchors the SKILL.md harness rule and task 1.6 cites it (#4);
`UnservableProviderError` is now non-retryable (#8, also ledger #8). Procedure deviation (#5):
all plan-iteration and plan-review handoffs were written as local fallback files because the
coordinator handoff RPC failed (`rpc_failed: unspecified coordinator error`); recorded here so
the audit trail shows why `handoffs/*.json` exist. Still open, advisory: the generated decision
timelines (#6 = ledger #2) and the historical review JSON (#7 = ledger #7).

## PLAN_REVIEW convergence, pass 3 (2026-10-10T22:21Z)

Delta round on `02816cb2` with the JSON-aware classifier: claude-local 7 findings (213 s),
codex-local 5 findings (146 s), fact-check removed nothing, 12 unconfirmed, 0 blocking, four
single-vendor high items → `adjudication_required`, adjudicated here:

| Ledger # | Vendor | Criticality | Verdict | Action |
|---|---|---|---|---|
| 16 | claude | high | Valid: nothing said the change must stay un-archived between the two runs; `cleanup-feature` step 5 migrates open tasks and `openspec archive` would move the held manifest and P0 | D8 "the change stays active across the two runs"; P0 checks the directory is still active; tasks header, proposal Sequencing, held header say `cleanup-feature` is withheld until `wp-router` merges |
| 23 (= ledger 7) | codex | high | Valid in part: the committed JSON did identify no change and could be read as converged | Identity fields corrected (`change_id`/`target`), `degraded: true` and provenance/quorum notes added to the three files; findings untouched |
| 24 | codex | high | Valid: "phase 2 changes nothing" and the Compatibility NFR ignored D2 (concrete alias) and D7 (`local` excluded for untrusted archetypes) | Proposal names both deliberate differences; NFR row scopes the zero-difference claim to retention outcomes and pins D2 to 1.1 and D7 to 3.8 |
| 25 | codex | high | Valid: one `git grep` marker proved only task 1.4 | P0 and 2.0 check one marker per dispatch surface (1.4 `UnservableProviderError`, 1.5 `resolved_provider`, 1.6 the prose-guard module present and passing on `origin/main`); D8 updated |

Also fixed: 2.1 retargets any v1.3 Literal-parity assertion to v1.4 in place (#17); P0 and 2.0
run `validate_work_packages.py` on the held file and the promoted manifest (#18); every
`order_applied` entry is `minLength: 1` in both wire schemas and the generated model, README and
2.1 updated (#26); wp-dispatch gains a ruff step and the whole change directory in `write_allow`
(#19, #20). Parked as out of scope (tooling, not this plan): the decision timelines mark
superseded entries `active` because `archive_index.py --emit-decisions` does not read the
`supersedes:` tag `phase_record.py` writes (#2, #21, #22). The Plan Review session-log entry
(written at the end of this phase, after the last pass) carries `supersedes:` tags on the
decisions that reverse earlier ones; the generated index will not show them until
`archive_index.py` learns the tag. Candidate follow-up: teach it the tag and order same-date
entries by phase.

## PLAN_REVIEW convergence, pass 4 (2026-10-10T22:32Z)

Delta round on `8d5aea25`: claude-local 5 findings (233 s), codex-local 4 (96 s), 9
unconfirmed, 0 blocking, three single-vendor high items → `adjudication_required`:

| Ledger # | Vendor | Criticality | Verdict | Action |
|---|---|---|---|---|
| 32 | codex | high | Valid: the record schema never said configured-fallback ⇒ `request.incumbent` object | Reverse conditional added; README difference (4) is now both directions; D6; 2.1 negative cases for absent and null incumbent |
| 34 (= claude #31) | codex | high | Valid: 2.0 cannot execute the prose-guard test (package denies `skills/autopilot/**`, no second checkout) | 2.0 re-runs object-store checks only (`git grep`, `git cat-file -e`); P0 alone runs the test, from the rebased feature worktree, and records command and result in the promotion commit; D8 |
| 35 | codex | high | Valid in part: the hold was prose at the lifecycle boundary | Named the two fail-closed mechanisms in D8: `cleanup-feature` step 5 stops on unchecked tasks 2.x–4.x and asks (tasks header tells the operator to stop); a `DONE` loop-state is terminal, so P0 moves it to `loop-state.run-1.json` and refuses to promote while a run is in flight; run-1 manifest header says completing it does not complete the change |

Also fixed: second-run re-entry semantics (claude #27, same loop-state mechanism); D7 is
coordinator-wide and flag-independent for every `select_model` caller (claude #29); the three
lane-attribute lists of `order_applied` are enum-typed in all three contracts (claude #30,
codex #33). Claude #28 (parking rationale rested on a session-log entry not yet in the branch)
is addressed by the wording above and by the Plan Review entry this phase writes.

Trend across passes (unique findings / blocking / single-vendor high-or-critical):
15/0/4 → 8 (unsynthesized) → 12/0/4 → 9/0/3. Every finding in every pass was single-vendor
judgment-class; the ledger never held a blocking item. After the pass-4 adjudication the ledger
has no open, no blocking and no adjudication items, which is the engine's converged state.
