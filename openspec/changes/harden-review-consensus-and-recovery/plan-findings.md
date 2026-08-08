# Plan Findings

## Iteration 1

<!-- Date: 2026-08-01 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | consistency | high | The base convergence requirement still used confirmation status as the exit gate, contradicting evidence-backed adjudication and fail-closed policy counts. | Added a modified convergence requirement that gates only on eligible quorum plus `convergence_blocking_count == 0`, with explicit inconclusive/escalated exhaustion. |
| 2 | completeness | high | Valid zero-finding reviews could disappear from checkpoint replay because the base layout inferred eligibility from non-empty findings. | Modified quorum and checkpoint requirements so every terminal logical result is indexed and the shared eligibility predicate alone computes quorum. |
| 3 | feasibility | high | Quorum eligibility had four consumers but no dependency-neutral implementation owner or file scope. | Added shared `review_result_policy.py`/attempt/checkpoint ownership, consumer dependencies, and dedicated tests. |
| 4 | security | high | `accepted_risk` authorization was forgeable as arbitrary text. | Replaced it with structured human authorization plus a trusted approval reference/resolver; vendor- or synthesizer-originated waivers fail closed. |
| 5 | consistency | high | The attempt schema allowed failed records with null errors and successful records without schema validation. | Replaced it with a logical-request/attempt-chain contract containing mutually exclusive success/failure invariants, one terminal attempt, deadline/budget, and exact quorum eligibility. |
| 6 | completeness | high | The frozen consensus contract omitted stable identity, match evidence, summary fields, quorum, and adjudication lifecycle. | Expanded it to a complete revision-2 report contract and specified an atomic stable-fingerprint adjudication ledger. |
| 7 | clarity | high | Replacement-vendor selection and global retry bounds were promised but unspecified. | Defined one corrective attempt on the initial model, one attempt per deduplicated fallback, one monotonic deadline, and at most one deterministic undispatched replacement. |
| 8 | consistency | high | `provisional`/`unconfirmed` and effective/compatibility blocker counts were inconsistent across artifacts. | Made `provisional_count` canonical, retained `unconfirmed_count` as its exact deprecated alias, and made `blocking_count == effective_blocking_count` over a unique set union. |
| 9 | assumptions | high | Review callers without autopilot phases had no routing precedence, and quick-task could accidentally inherit reviewer routing. | Documented explicit context > review phase > review-mode reviewer default > static fallback; quick mode stays static unless explicitly overridden. This follows the selected config-driven approach without adding a new product choice. |
| 10 | testability | medium | Unsupported thinking translation and fallback thinking behavior were not measurable. | Added provider-configured translation outcomes, explicit/inherited fallback thinking, fail-closed configuration errors, and requested/applied provenance scenarios. |
| 11 | performance | medium | All-pairs matching was unbounded and weak transitive bridges could merge unrelated concerns. | Added 500-finding/2-MiB defaults, structural candidate buckets, stable anchored complete-membership checks, and scale/bridge fixtures. |
| 12 | parallelizability | high | Compatibility callers were out of task scope; checkpoint edits conflicted; two same-file tasks could run concurrently; and the 720-LOC dispatcher package mixed three concerns. | Added caller tests/scopes, made checkpoints coordinator-owned, ordered consensus tasks, and split attempt core, routing, and transport integration into isolated packages with explicit shared-policy dependencies. |

### Quality Checks

- `openspec validate harden-review-consensus-and-recovery --strict`: passed after refinement.
- Both frozen JSON contracts parse and pass Draft 2020-12 meta-schema checks.
- Work-package schema, dependency references, DAG cycle, and lock-key validation: passed after refinement.
- Parallel package scope and lock overlap validation: passed.
- Coordinator handoff/memory reads were attempted but the configured MCP endpoint was unavailable; iteration continued with the on-disk handoff.

### Parallelizability Assessment

- Independent root packages: 2 (`wp-review-attempt-core`, `wp-review-routing`)
- Independent initial tasks: 3 (`1.1`, `2.1`, `2.2`); package grouping conservatively waits for the shared quorum helper before consensus work
- Sequential chains: 3
- Max package parallel width: 2
- File overlap conflicts: none among packages that can be ready concurrently
- Coordinator-owned checkpoints: package agents do not edit `tasks.md`
- Dependency shape: attempt core feeds consensus; attempt+routing join at dispatcher integration; consensus+dispatcher join at convergence; final integration is serial

---

## Summary

- Total iterations: 1
- Total findings addressed: 12 (9 high, 3 medium)
- Remaining findings below threshold: none
- Termination reason: threshold met

## PLAN_REVIEW Remediation 1

<!-- Date: 2026-08-01 -->

The routed Codex review produced six medium-or-higher actionable findings. External vendor dispatch was denied before egress, so this is not a multi-vendor convergence claim; the next PLAN_REVIEW still requires independent quorum.

| # | Criticality | Finding | Resolution |
|---|---|---|---|
| 1 | critical | A replacement vendor could later satisfy its own scheduled slot and impersonate independent quorum. | Added a one-vendor/one-logical-slot round allocation invariant, deterministic slot transfer/cancellation, manifest provenance, and a no-double-vote scenario. |
| 2 | high | A successful attempt could validate with a null terminal model or mismatched terminal vendor. | Required a non-null model on the unique terminal successful attempt and made terminal-vendor equality a producer/shared-predicate invariant with a negative scenario. |
| 3 | high | A per-vendor disposition map could overwrite two same-vendor source findings in one group. | Made disposition mandatory on every source finding and retained the vendor map only as a deprecated derived summary. |
| 4 | high | The convergence package could neither edit nor execute its checkpoint regression. | Added `test_convergence_checkpoint.py` to package scope and its verification command. |
| 5 | medium | The item contract still used `unconfirmed` while the spec made `provisional` canonical. | Changed the item enum to `provisional`; only the deprecated summary-count alias remains `unconfirmed_count`. |
| 6 | medium | Capacity, authentication, transient, and configuration behavior lacked cross-transport acceptance scenarios. | Added normative CLI/SDK/async scenarios and expanded recovery characterization/engine task traceability. |

The optional pre-parse streaming limit remains below the remediation threshold and is recorded as residual risk; the required 2 MiB post-parse matching guard remains in scope.

## PLAN_REVIEW Remediation 2

<!-- Date: 2026-08-01 -->

Approved external dispatch requested four reviewers but produced zero eligible results: Antigravity exceeded the documented per-vendor bound inside its model-fallback loop, and the sequential dispatcher never reached Claude Code, Grok, or Pi. The legacy local consensus reported `blocking_count=0`; this was rejected because quorum was not met and four actionable primary findings remained.

| # | Criticality | Finding | Resolution |
|---|---|---|---|
| 1 | high | Revision-2 consensus removed legacy envelope and per-finding fields used by current readers. | Made revision 2 additive: retained derived legacy reviewers, flat quorum, item identifiers/match/type/criticality/disposition, and legacy `status`; added canonical `policy_status` and alias-validation requirements. |
| 2 | critical | Nested quorum could validate `met=true` with no eligible results. | Added `minimum_required` and unique eligible vendors plus mandatory `validate_consensus_report()` invariants for received/requested, distinct vendors, threshold truth, and flat/nested equality. |
| 3 | high | The attempt schema recorded budgets without constraining attempt chains. | Added expressible JSON Schema limits and mandatory `validate_review_attempt_chain()` checks for ordering, indexes, fallback membership, deadlines, vendor transitions, terminal attribution, and post-success attempts. |
| 4 | medium | The consensus package did not execute its owned policy test suite. | Added `test_consensus_policy.py` to the package verification command. |
| 5 | observed blocker | The public per-vendor timeout reset for each model attempt and prevented later vendors from running. | Defined one monotonic deadline for the entire vendor/model chain, outer enforcement, progressive terminal persistence, and continuation to later scheduled vendors. |

The optional pre-parse output cap remains below threshold and is carried as residual risk. Independent vendor quorum remains required after implementation fixes the dispatcher behavior; the current apparatus cannot manufacture convergence from its zero count.

### Independently bounded bootstrap review

To avoid the broken sequential dispatcher, Antigravity, Claude Code, Grok, and Pi were dispatched concurrently with reviewer/premium models, fallbacks disabled, and one 300-second hard limit per vendor. Results were Antigravity invalid JSON (`error_class=null`, 230.80s), Pi invalid JSON (`error_class=null`, 1.54s), Claude timeout (300.04s), and Grok timeout (300.03s). Quorum remained 0/4. The run is durable at `reviews/independent-bootstrap-manifest.json` and does not change the fail-closed `not_converged` outcome.
