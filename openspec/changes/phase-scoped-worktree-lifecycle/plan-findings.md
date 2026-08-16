# Plan Findings

## Iteration 1

<!-- Date: 2026-08-15 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | consistency | critical | The design required session-scoped release, but the registry schema forbade `session_id`, used a different lifecycle-mode field, and the CLI omitted `release-session`. | Standardized `lifecycle_mode`; added nullable `session_id`, exact session release, exit/output semantics, and contract-fixture tasks. |
| 2 | feasibility | critical | Owner equality did not fence an expired zombie that resumed under the same owner, and release-before-teardown allowed another owner to acquire a worktree that the prior owner could then remove. | Added a single-acquisition `lease_id`, boundary assertions, new-id-on-reacquire, and owner/token-checked disposal holding the registry lock through Git removal. |
| 3 | feasibility | critical | Markdown-only skill edits could not implement the promised background renewal and guaranteed finalization behavior. | Defined portable `worktree_lifecycle.py` plus executable `phase_lifecycle.py` controller boundaries, process-level tests, session-hook reuse, and package scopes. |
| 4 | completeness | high | Failed dirty/non-durable work could become idle and be silently adopted; teardown also treated a pushed-but-unmerged proposal as unsafe. | Added `recovery_required` quarantine and explicit adoption; safety now checks dirtiness/submodules and remote reachability, not merge-to-main status. |
| 5 | consistency | high | Delivery rules disagreed about missing markers and whether implementation plus plan refinements was mixed. | Added an ordered truth table: missing optional marker warns, missing primary evidence blocks, a governing base plan yields implementation, and no base plan plus a new head plan yields mixed. |
| 6 | testability | high | Classifier contracts could not serialize diff completeness, base/head SHAs and state, marker warnings/status, unknown paths, or auditable author-vendor evidence. | Expanded the classification schema and exhaustive fixture/test tasks; unverified vendor claims now take conservative independent-review routing. |
| 7 | consistency | high | The merge-plan definition was declared immutable while live reclassification had nowhere to persist, and operator disposition lacked an interface contract. | Kept the discovery snapshot immutable, added `state.latest_delivery_classification`, and specified actor/stage/rationale/timestamp override plus SHA revalidation. |
| 8 | consistency | high | Added deltas coexisted with active requirements that still required permanent planning pins, proposal-worktree reuse, package pins, and unconditional OpenSpec cleanup. | Replaced those exact active requirements under `MODIFIED Requirements` and retained new concerns only as added requirements. |
| 9 | feasibility | high | The promised shared registry interpreter had no module/package path and would be absent from the coordinator runtime image. | Located it in `skills/shared/worktree_lifecycle.py`, added install/container import contracts, Dockerfile scope, and source/container tests. |
| 10 | parallelizability | high | Two active changes write the same merge and validation paths, but prose coordination did not stop parallel dispatch. | Added mandatory baseline-SHA/rebase no-dispatch gates and package inputs for `add-merge-plan-orchestration` and `validate-feature-findings-gate`. |
| 11 | completeness | high | Fresh-description autopilot could not acquire before PLAN because change-id, branch, and worktree bootstrap were unspecified. | Defined deterministic pre-mutation change-id resolution, continuous implementation-branch setup, persisted fenced identity, and operator escalation on ambiguous IDs. |
| 12 | testability | medium | Schema checks only validated metaschemas, scenario identifiers were overloaded, and integration gates omitted the promised regression/static/diff coverage. | Added representative format/reference fixture tasks, targeted regression/static/mypy/diff gates, semantic requirement names, and an unambiguous legacy-cleanup scenario name. |

### Quality Checks

- `openspec validate phase-scoped-worktree-lifecycle --strict`: pass.
- Work-package schema, references, DAG, and lock-key validation: pass.
- Architecture package scope/lock overlap validation: pass.
- Draft 2020-12 schema self-validation: pass.
- Representative v2 registry, delivery-classification, and cross-file
  merge-plan instances with reference resolution and date-time format checking:
  pass.
- `git diff --check`: pass.
- Every requirement has success and failure/edge coverage; corrupt registry,
  expired writer, disposal race, quarantine, missing marker, incomplete evidence,
  and operator override paths are explicit.
- Task/spec/contract/design traceability was updated for every finding.

### Parallelizability Assessment

- Independent implementation package roots: 2 (`wp-registry`, `wp-pr-delivery`
  after its external baseline gate).
- Sequential chains: 4 (`registry -> phase lifecycle -> integration`, `registry
  -> autopilot -> integration`, `registry + PR delivery -> coordinator ->
  integration`, and `PR delivery -> integration`).
- Max parallel width: 3 (`wp-phase-lifecycle`, `wp-autopilot`, and
  `wp-coordinator-projections` after their prerequisites settle).
- File overlap conflicts: none inside the package DAG; the two cross-change
  overlaps are blocked by explicit pre-dispatch baseline gates.

---

## Summary

- Total iterations: 1
- Total findings addressed: 12
- Remaining findings below threshold: none
- Termination reason: threshold met after semantic contract refinement
- Proposal readiness: strict-valid, contract-aligned, testable, and gated for
  safe parallel implementation after the two recorded external baselines land

---

## Iteration 2

<!-- Date: 2026-08-15 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | critical | An expired checkout could be ordinary-acquired after a crash without proving its preserved state safe. | Required a locked expired-takeover assessment of cleanliness, submodules, remote durability, and process evidence; unsafe or indeterminate entries enter recovery quarantine. |
| 2 | security | critical | Session release could clear ownership while leaving an in-flight or dirty checkout immediately adoptable. | Made session release quarantine every preserved matching checkout before clearing its lease; the hook remains non-destructive and explicit finalization is the only clean-disposal path. |
| 3 | contract mismatch | critical | Fresh v1 heartbeats did not define every required v2 lease field or exact post-migration alias behavior. | Defined deterministic owner/token derivation, all timestamps and metadata, one-hour TTL, v1 canonicalization, and explicit owner/token requirements after v2 conversion. |
| 4 | testability | medium | Registry and phase packages omitted their owned shared-controller tests. | Added `test_worktree_lifecycle.py` and `test_phase_lifecycle.py` to their package gates. |
| 5 | architecture | medium | The coordinator package could not write or run its assigned Docker import-contract test. | Added the test path to package scope and verification. |
| 6 | correctness | medium | Absent release and repeated teardown claimed unverifiable same-owner idempotency. | Defined observable no-op semantics without attesting prior ownership. |

### Review Context

- Codex produced 8 schema-valid findings: 3 critical, 3 nits, and 2 positive observations.
- Antigravity, Claude, and Grok timed out; Pi returned invalid JSON, so external quorum was not met and all findings remained unconfirmed.
- The critical findings were nevertheless concrete contract defects and were fixed before review retry.

---

## Iteration 3

<!-- Date: 2026-08-15 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | architecture | critical | Expired takeover referenced process evidence without defining identity, storage, PID reuse, or cross-host behavior. | Added a versioned process-evidence schema and atomic lease-bound records with PID/start/host/controller identity; live and indeterminate evidence quarantines, while stale same-host evidence permits later safety checks. |
| 2 | contract mismatch | critical | Operator delivery overrides were not bound to the base/head state the operator inspected. | Added required base/head SHAs, ruleset version, and canonical-classification SHA-256 digest; any mismatch restores blocked ambiguous routing. |
| 3 | security | critical | Bulk `release-owner` could clear leases without quarantining preserved checkouts. | Applied quarantine-before-clear semantics and per-entry/quarantine counts to exact-owner recovery release. |
| 4 | correctness | medium | Package disposal did not define which remote ref proves an integrated child HEAD durable. | Required parent-feature push first and exact child-HEAD reachability from that expected parent remote ref. |
| 5 | resilience | medium | A crash between Git removal and registry replacement left an unreconciled live orphan entry. | Made exact owner/lease repeated teardown reconcile the one-sided missing-checkout state and process evidence. |
| 6 | contract mismatch | medium | Explicit recovery adoption did not define its complete schema-v2 lease result. | Defined every manual `RECOVERY` lease field, TTL/timestamps, state clearing, output, and conflict exits. |

### Review Context

- The second retry again had no valid external vendor result; Codex supplied 3 critical blockers, 3 nits, and 2 positive observations.
- All six actionable findings were incorporated before the next convergence attempt.

---

## Iteration 4

<!-- Date: 2026-08-16 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | security | critical | Same owner/lease retries did not bind the live controller, allowing two resumed controllers to pass fencing checks concurrently. | Added `controller_instance_id` to automatic leases, exact-triple assertions, same-controller-only retry, parent-only renewal, and a separate resume transition that rejects live or indeterminate prior evidence. |
| 2 | durability | critical | Expired takeover could not identify the authoritative remote ref, especially for package worktrees whose durable boundary is the parent feature ref. | Added entry-level remote/ref identity, canonical remote URL hashing, package-parent targets, refresh-outside-lock plus generation revalidation, and stored-target-only takeover/disposal checks. |
| 3 | security | critical | Process evidence keyed only by client-supplied lease id could collide across registry entries. | Keyed evidence by a versioned length-prefix encoding of entry identity plus lease, added entry identity to the evidence schema, and required exact entry/owner/lease/controller validation before every evidence operation. |
| 4 | correctness | critical | A pre-existing unleased or legacy entry bypassed safety assessment and was acquired immediately. | Added atomic setup-and-acquire publication plus entry generations; every separately visible unleased entry now uses full durability, cleanliness, and prior-process assessment or enters quarantine. |
| 5 | security | critical | Recovery adoption after owner/session release could race a still-running former controller because release discarded its evidence. | Added durable recovery context, preserved matching evidence on quarantine release, required stale same-host proof for normal adoption, and isolated missing/cross-host handling behind an audited force-adopt command. |
| 6 | resilience | critical | Autopilot clean teardown on ESCALATE/exception left no defined way to resume because state lived in the removed checkout. | Moved resumable run state outside disposable worktrees, added finalization-intent and checkout-state reconciliation, and specified verified durable-ref recreation with a new controller-bound lease. |
| 7 | security | critical | Operator disposition could override a clear implementation classification to proposal and bypass implementation gates. | Schema- and command-constrained overrides to the latest ambiguous classification, enforced selected/effective-stage equality, and required live reclassification before disposition and execution. |
| 8 | determinism | high | “Canonical classification digest” did not define a byte-level algorithm. | Defined `pr-delivery-v1+jcs-sha256`: semantic projection excluding only `classified_at`, UTF-8 byte sorting for set arrays, no Unicode normalization, RFC 8785 JCS, lowercase SHA-256, and a fixed Unicode-aware fixture. |
| 9 | testability | high | Oversized tasks and incomplete gates hid controller, install-hook, merge-script, formatting, and external-baseline failures. | Split lifecycle, routing, and resume work into test-first M/S units; added executable ancestry gates, missing suites, Ruff format checks across all changed surfaces, and narrowed integration write scope. |

### Review Context

- Three independent read-only refinement passes converged on the controller,
  durability, recovery, autopilot-resume, override, digest, and gate changes.
- The persisted autopilot loop state intentionally remains `ESCALATE`; this
  refinement resolves the recorded blockers but does not claim a new review
  quorum or authorize implementation.

### Quality Checks

- Strict OpenSpec validation: pass.
- Work-package schema, references, DAG, lock, and scope-overlap checks: pass.
- Architecture parallel-zone validation: pass.
- All change-local Draft 2020-12 schemas self-validate: pass.
- Representative registry, external autopilot recovery, clear-classifier,
  ambiguous-override, and selected-stage-mismatch instances validate with
  cross-file reference resolution and date-time format checking: pass.
- `git diff --check`: pass after session-log normalization.

### Parallelizability Assessment

- Independent roots: 2 (`wp-registry` and baseline-gated `wp-pr-delivery`).
- Sequential chains: 3 (`registry -> phase lifecycle -> autopilot ->
  integration`, `registry + PR delivery -> coordinator -> integration`, and PR
  delivery direct to integration).
- Maximum parallel width: 2 after controller propagation made autopilot depend
  on the phase-lifecycle package.
- Intra-change file and lock overlaps: none; cross-change paths are protected by
  executable recorded-SHA ancestry gates before dispatch.

---

## Iteration 5

<!-- Date: 2026-08-16 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | critical | Autopilot released its lease before a teardown command that required the still-live exact ownership triple. | Made successful finalization checkpoint then teardown while the triple is live; unsafe teardown atomically quarantines and clears ownership, with no second release. |
| 2 | security | critical | Force-adopt authorization lived only in recovery context and vanished when successful adoption cleared quarantine. | Added append-only top-level recovery audit, atomically recording actor, rationale, termination confirmation, generation, and old/new identities so entry teardown cannot erase it. |
| 3 | resilience | critical | Setup-and-acquire claimed impossible atomicity across Git, evidence, and registry writes without a crash protocol. | Added caller-id/generation-fenced setup reservations, explicit side-effect checkpoints, sync-point blocking, and exact retry/quarantine transitions. |
| 4 | security | critical | Durability remote, URL digest, and ref were independently supplied and could identify different authorities. | Defined `git-remote-url-v1`, credential stripping, exact remote/ref binding, current URL verification, outside-lock fetch, and generation-bound observed-tip revalidation. |
| 5 | compatibility | critical | Mandatory durability arguments broke existing setup and left separately visible manual entries semantically unclear. | Preserved the complete legacy setup signature/output with nullable target and made it an explicitly manual, non-ordinarily-adoptable compatibility path. |
| 6 | architecture | critical | The all-write-skills invariant omitted many live pin, heartbeat, and registry consumers. | Replaced the vague scope with a checked-in mutating-skill inventory, scan-based completeness tests, and a dedicated lifecycle-consumer package. |
| 7 | security | critical | External recovery identifiers and redundant owner/branch/path fields were not cross-bound before path construction. | Added safe identifier patterns, derived-path/equality checks before I/O, and canonical-state change-id verification. |
| 8 | resilience | critical | External recovery writes lacked lock/CAS/fsync semantics and removed resume accepted stale reachable ancestors. | Added per-run lock, generation CAS, atomic durable replace, exact blob hashing, and exact fetched-tip recreation with advanced/rewound/missing refusal. |
| 9 | contract mismatch | critical | The installed convergence schema and root mirror did not validate actual persisted LoopState and had no owner package for parity. | Assigned schema-v5 source ownership to autopilot, root mirror ownership to integration, real-state migration tests, and byte-parity validation. |
| 10 | architecture | critical | Baseline ancestry metadata was not scheduler-enforced and trusted arbitrary recorded SHAs. | Added an authoritative-PR preflight package and evidence schema; dependent worktrees wait for verified merged/base/ancestry/surface evidence. |
| 11 | correctness | critical | Repository-wide Ruff formatting was guaranteed to fail on unrelated baseline debt. | Added a baseline-bound changed-Python helper that includes committed and working-tree paths and routes files through the correct project environment. |
| 12 | architecture | critical | The PR package could not author its required JCS golden fixture. | Moved the single fixture into the PR package's owned test tree and made integration consume, not author, it. |
| 13 | observability | medium | Clearing a stale operator override erased the operator and invalidation evidence. | Added append-only override history with recorded/honored/invalidated events and coordinator projection tests. |
| 14 | consistency | medium | Normative teardown scenarios omitted controller identity and the state diagram retained a removed nonce. | Propagated the exact triple plus destructive entry generation through commands, outputs, scenarios, and replaced nonce with reservation transitions. |
| 15 | security | critical | Envelope generation CAS did not itself stop a stale controller that loaded the latest generation from overwriting recovery state. | Required every present/pending write to authorize against the exact live registry triple and entry generation; post-teardown reconciliation is limited to an identity-bound pending-to-removed CAS. |
| 16 | compatibility | critical | Legacy and compatibility entries with a null durability target had no command capable of establishing one for safe recovery. | Added complete remote/ref arguments to both adoption commands, with outside-lock validation/fetch, generation revalidation, and atomic target establishment. |
| 17 | correctness | critical | A setup reservation embedded a complete timestamped lease, so the initial lease could age or expire before active publication. | Replaced it with a timestamp-free `leaseIntent`; the final locked publication derives acquisition, heartbeat, and expiry from one publication time. |
| 18 | consistency | critical | Reservation blocking, active projection, and active-agent prose disagreed over whether provisioning could pass a sync point. | Defined reservations as non-active, indeterminate sync-point blockers and added local plus coordinator projection coverage. |
| 19 | compatibility | critical | The v2 null-controller legacy heartbeat path was described as ordinary renew even though renew requires a controller. | Defined a narrow compatibility handler for the exact stored manual `LEGACY` synthetic lease; all other v2 leases require controller-bound renew. |
| 20 | correctness | critical | Explicit release could not always create schema-valid quarantine because its reason was optional. | Defined a stable `explicit-release` recovery source and deterministic default reason while preserving a supplied non-empty reason. |
| 21 | architecture | critical | Merge sync-point migration was inventoried but excluded from the lifecycle-consumer package and absent from its owning PR package. | Assigned canonical-guard migration and tests to `wp-pr-delivery`, made it depend on `wp-registry`, and sequenced integration after the migration. |
| 22 | architecture | critical | Isolated preflight completion did not guarantee its evidence commit was present in dependent worktree bases, and initial prose did not assign the scheduler enforcement code. | Moved the root preflight to the managed shared feature worktree; assigned the implement-feature/DAG scheduler completion barrier, exact dependent-base recording, and no-early-dependent tests to the preflight package. |
| 23 | security | critical | Force-adopt promised to audit a newly established durability target, but the strict audit schema had no field for it. | Added a required nullable target snapshot to each force-adopt audit event and tests for both newly established and pre-existing targets. |
| 24 | compatibility | medium | Required override history would reject pre-revision merge-plan nodes before they could be upgraded. | Added locked initialization of a missing legacy history to `[]` before schema-valid rewrite and fixture coverage. |
| 25 | testability | medium | Changed-file Ruff rules did not say how generated Python mirrors were routed. | Excluded generated mirrors only after byte-for-byte drift validation and added drift-failure/exclusion tests; every remaining Python path is environment-routed. |
| 26 | consistency | medium | Integration task dependencies omitted the completed inventory-consumer migration. | Added task `2.9` and merge migration `3.10` as explicit canonical-spec/documentation prerequisites. |
| 27 | consistency | medium | Several shorthand sentences omitted generation/controller fields or mixed pre-I/O identity validation with post-fetch blob validation. | Aligned evidence, release, recovery, and validation prose with exact generation/triple and split pre-I/O envelope checks from post-fetch canonical-state checks. |
| 28 | correctness | medium | The prerequisite schema accepted invalid 41-63-character object IDs through a broad length range. | Restricted every Git identity to exactly 40 or 64 lowercase hexadecimal characters and added invalid-length fixtures. |
| 29 | contract mismatch | medium | A `present` external recovery envelope could carry null lease and registry generation despite live-registry authorization requirements. | Schema-constrained both fields to non-empty strings whenever checkout state is `present` and added representative state fixtures. |

### Review Context

- Three authorized read-only agents independently covered registry/recovery,
  autopilot/session state, and workflow/package scope; their critical findings
  were merged and deduplicated before edits.
- Configured external-vendor dispatch was attempted locally but failed on
  sandbox/home-state access. The required escalation was rejected because it
  would export repository artifacts to third-party services, so no external
  content was sent and vendor quorum remains unavailable.

### Quality Checks

- Strict OpenSpec validation: pass.
- Work-package schema, dependency references, DAG, lock keys, scopes, and
  architecture parallel-zone checks: pass.
- All change-local Draft 2020-12 schemas self-validate; YAML contracts parse.
- Canonical design registry example validates against the full registry schema.
- `git diff --check`: pass.

### Parallelizability Assessment

- Independent roots: 2 (`wp-baseline-preflight` and `wp-registry`); preflight
  runs in the managed shared feature worktree and its completion barrier records
  exact feature HEAD before downstream worktrees exist.
- Sequential chains: 3 (`preflight + registry -> phase lifecycle -> consumers ->
  integration`, `registry -> phase lifecycle -> autopilot -> integration`, and
  `preflight + registry -> PR delivery -> coordinator -> integration`).
- Maximum parallel width: 3 (`wp-lifecycle-consumers`, `wp-autopilot`, and
  `wp-coordinator-projections` after their respective dependencies complete).
- Intra-change file and lock overlaps: none; package validation reports every
  declared parallel pair safe.

---

## Iteration 6

<!-- Date: 2026-08-16 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | resilience | critical | A crashed setup reservation had no bounded retry window or safe operator escape. | Added fixed reservation expiry, exact completed-setup replay, and audited reconciliation that removes only side-effect-free intent or preserves attributable state in quarantine. |
| 2 | architecture | critical | Feature-HEAD completion ownership and current-run bootstrap ordering were ambiguous. | Made `contracts/prerequisites.yaml#execution_gate` the exact declaration; barrier tests and implementation land before scheduler reload, live evidence, and dependent dispatch. |
| 3 | correctness | critical | Shared preflight contradicted the universal dedicated-package-worktree rule. | Added the narrow declared feature-HEAD root exception; it inherits the managed feature checkout and parent fence while ordinary packages remain isolated. |
| 4 | compatibility | critical | Unleased, quarantined, and null-target legacy state lacked safe disposal or preservation paths, while coordinator kick depended on unsafe bare force. | Added safe recovery teardown, separately confirmed/audited force-teardown, null-controller legacy release, force-adopt inspection, and generation-fenced target binding; automatic teardown remains force-free. |
| 5 | architecture | critical | Coordinator API/SSE/sync-point surfaces, worktree infrastructure, context consumers, and session-hook mutation were absent or misclassified. | Expanded the inventory and package scopes, gave hooks `session_backstop`/`release-session-only`, and narrowed launcher migration to package-owned paths. |
| 6 | security | critical | A stale autopilot controller could not safely record quarantine after teardown cleared its lease. | Authorized only an identity-bound pending-to-quarantined CAS backed by matching immutable unsafe-finalization recovery context and no replacement lease. |
| 7 | correctness | high | A completed removed autopilot run could be recreated and redispatched. | Made `removed+done` a terminal tombstone, ordered canonical DONE durability before teardown, and restricted recreation to exception/escalate state. |
| 8 | resilience | medium | External recovery envelopes had no bounded retention or race-safe GC. | Added null-by-default `gc_eligible_at`, a 30-day DONE tombstone window, generic-GC exclusion, and dedicated global-then-run locked GC. |
| 9 | correctness | medium | Autopilot session ownership and generic session release behavior were unspecified. | Required continuous autopilot `session_id=null`; generic release-session never selects it. |
| 10 | correctness | medium | Setup response-loss retry conflicted with unconditional existing-entry refusal. | Stored nullable completed `setup_id` provenance and made the exact matching receipt replay success without mutation. |
| 11 | observability | medium | Coordinator sync blockers omitted unfinished setup reservations. | Added explicit non-active provisioning blockers to sync-point, API, and SSE scenarios. |
| 12 | contract mismatch | medium | Incomplete diff or base/head evidence was only prose-level ambiguous. | Added JSON Schema conditionals and negative fixtures forcing `delivery_stage=ambiguous`. |
| 13 | consistency | medium | Two task scenario references were nonexistent or misnamed. | Corrected them to `Worktrees are finalized after integration` and `Lease mutations short-circuit under harness isolation`. |

### Review Context

- The operator explicitly authorized repository export for this review.
- Antigravity, Claude, and Grok returned schema-valid reviews; Pi returned
  invalid JSON. External quorum was therefore met at 3/4 plus Codex.
- The mechanical consensus matcher reported 39 unconfirmed findings because it
  missed semantic duplicates; Claude and Grok independently identified the
  stale-controller quarantine gap. The raw reports and schema-valid consensus
  snapshot are preserved, and one non-recursive remediation pass addressed all
  distinct actionable findings.

### Quality Checks

- Strict OpenSpec validation: pass.
- Work-package schema, references, DAG, locks, scopes, and architecture zones: pass.
- All change-local Draft 2020-12 schemas and YAML contracts: pass.
- Representative registry, autopilot terminal/GC, classifier-negative, and review artifacts: pass.
- `git diff --check`: pass.

---

## Current Summary

- Plan revision: 6 across six recorded refinement iterations.
- External review quorum: met; all distinct critical/high/medium actionable
  concerns from the exported revision-5 review are remediated in revision 6.
- Deterministic readiness: strict-valid, schema-valid, package-DAG-valid,
  architecture-zone-valid, and representative-instance-valid.
- Review artifacts: raw vendor reports and consensus snapshot retained; final
  Codex re-audit reports no residual actionable finding.
- Implementation readiness: contract-ready, but dependent package dispatch
  remains blocked until both named prerequisite changes land and the ordered
  shared-feature completion barrier succeeds.
