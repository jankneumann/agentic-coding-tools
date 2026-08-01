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
