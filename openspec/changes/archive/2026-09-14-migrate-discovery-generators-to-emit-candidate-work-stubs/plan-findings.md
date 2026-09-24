# Plan Findings

## Iteration 1

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | consistency | high | Delta modified nonexistent canonical requirements. | Classified them as added requirements. |
| 2 | architecture | high | Validator ownership coupled producers to a consumer skill. | Added a shared validation and atomic-write boundary. |
| 3 | feasibility | high | Intake omitted required fields and collision semantics. | Defined one-stub input, fields, resolution, and transaction routing. |
| 4 | clarity | high | Producer eligibility and mappings were implicit. | Added executable per-producer rules. |
| 5 | testability | high | Ranking lacked total ordering and dependency behavior. | Defined a separate lane, topology, tie-breakers, and refusals. |
| 6 | security | medium | Discovery strings could be interpreted by renderers. | Required inert rendering and opaque provenance URIs. |

No findings at or above medium remain.

## Parallel Review Round 1

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | architecture | high | The executable work-package DAG let candidate ranking start before all three producer adapters, contrary to task 2.1 and the integration contract. | Added `wp-producers` to `wp-prioritize.depends_on`; `wp-integration` now receives that prerequisite transitively. |
| 2 | architecture | medium | The producer package could update bug-scrub and improve-harness skill docs but not their canonical skill-contract tests. | Added both test directories to `wp-producers.write_allow`. |
| 3 | infrastructure | high | An initially bounded dispatch timed out before independent results arrived. | A documented-timeout retry produced substantive 4/4 external-vendor results; combined with the primary Codex review, consensus met 5/5 quorum. |
| 4 | correctness | high | Producer priorities were not comparable, explore-feature could emit schema-invalid prefixes, and prose blockers could become permanent dependency edges. | Defined one shared five-band scale, canonical prefix normalization, and exact-ID-only dependency projection with inert prose fallback. |
| 5 | correctness | high | New-roadmap intake omitted required envelope and capability data; existing-roadmap intake could introduce duplicate execution priorities. | Required roadmap ID/capability and a complete envelope in new mode; existing mode omits execution priority so refine-roadmap assigns max+1 while retaining source priority in rationale. |
| 6 | compatibility | high | New shared-runtime consumers lacked install-manifest declarations and package write scope for the manifest guard. | Added manifest/test ownership to `wp-contracts` and made the declaration part of task 0.2 and validation. |
| 7 | architecture | low | Contract and producer package gates omitted writable canonical tests. | Added the validator test to `wp-contracts` scope and the canonical producer skill-test directories to the producer gate. |

All consensus blocking defects were remediated and strict plan/package validation is
green. A confirmation dispatch was started but stopped on the supervising agent's
bounded-round instruction, so the recorded phase outcome remains `not_converged`
pending an independent review of revision 3.

## Parallel Review Round 2

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | medium | The exhaustive bug-scrub effort table used shorthand rather than the eight exact `Category` literal values. | Named every literal exactly and retained fail-closed behavior for values outside the closed set. |
| 2 | architecture | medium | Task 3.3 consumed the shared validator without a task-level dependency on 0.2. | Added 0.2 to the task dependency list, matching the executable package DAG. |
| 3 | infrastructure | high | The documented 600-second vendor dispatch exceeded the supervising round bound before any external result was persisted. | Reaped the dispatcher and recorded all four external reviewers as interrupted; substantive quorum was 1/5 including the primary Codex review. |

The two locally detected defects are fixed in plan revision 4. Round 2 remains
`not_converged` because no independent vendor confirmation reached the artifact
boundary before the enforced bound.

## Parallel Review Round 3

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | low | Codex and Antigravity independently confirmed that revision 4 names the exact producer mappings and preserves fail-closed normalization and persistence. | Accepted as a positive observation; no plan edit required. |
| 2 | architecture | low | Codex and Antigravity independently confirmed task/package dependency alignment and refine-roadmap transaction ownership. | Accepted as a positive observation; no plan edit required. |
| 3 | infrastructure | high | Antigravity returned substantive valid findings, but Pi returned a schema-invalid payload with invalid IDs and enum values. | The dispatcher rejected Pi's payload; retained the validation error in the manifest and did not retry or expand the final bounded panel. |

Round 3 has zero blocking plan findings, but the required external quorum is only
1/2. The final bounded review therefore ends as `max_iter`, not false convergence.


## Recovery Review Round 1 (2026-09-13)

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | high | Collision handling depended on batch membership and contradicted duplicate-ID refusal. | Derived IDs now always include a canonical-provenance hash; explicit hints are normalized as-is; duplicate final IDs fail. |
| 2 | correctness | high | Explore-feature mapped shortlist rank directly to cross-generator priority. | Fixed weighted-score bands now map semantic evidence to priorities 2-5; priority 1 requires explicit critical/immediate evidence. |
| 3 | correctness | medium | Dependency mapping, topological ordering, and blocked propagation were ambiguous. | Intake now requires one exact target-roadmap item; ranking uses specified Kahn traversal with transitive blocked status. |
| 4 | correctness | medium | Improve-harness fabricated effort from severity. | Effort now derives from affected-skill count; severity controls priority only. |
| 5 | compatibility | medium | Mirror manifests were outside integration write scope and mirror verification was unpublished. | Added both manifest paths, a `skills/install.sh --check` gate, and complete result keys. |
| 6 | testability | medium | Several scenarios were traced only to the catch-all integration task. | Assigned every behavior to focused producer, ranking, or intake RED tests and narrowed the integration task. |
| 7 | infrastructure | high | Three harnesses failed before launch because the copied review history made the packet exceed host argv limits. | Historical runtime artifacts remain on the original failed branch but were removed from this clean recovery branch; the next packet contains only canonical plan artifacts. |

Plan revision 5 passes strict OpenSpec validation, package schema/DAG/scope/overlap validation, and mirror-payload validation.


## Recovery Review Round 2 (2026-09-13)

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | high | Whole-provenance hashing includes rank, report path, and growing source-entry sets, so derived IDs can drift. | **Resolved by operator adjudication:** hash only `generator` plus the producer-specific immutable source ID; explicit hints remain unsuffixed; duplicate final IDs fail. |
| 2 | correctness | high | Ranking accepted completed external dependencies that intake could not represent, especially for a new roadmap. | Defined explicit local `depends_on`, cross-roadmap `external_depends_on`, and satisfied-archive rationale mappings. |
| 3 | correctness | medium | Existing-roadmap replay, duplicate item change IDs, and stale next IDs were not tied to refine-roadmap guards. | Required fresh preview, existing duplicate-change guard, omitted-priority max+1 behavior, and stale-base refusal. |
| 4 | testability | medium | Revision-5 priority, effort, prefix, blocked-propagation, and missing-generator rules lacked normative scenarios. | Added focused scenarios and task ownership for each behavior. |
| 5 | correctness | medium | Explore score formula/range and priority-1 behavior were unstated. | Pinned the existing formula and 1.0..3.3 range; explore never emits priority 1. |
| 6 | correctness | medium | Missing optional generator and active OpenSpec dependency resolution were undefined. | Added the empty-string generator tie key and active-change dependency stage. |
| 7 | consistency | medium | Priority provenance/rationale and improve severity vocabulary diverged. | Standardized on request rationale and improve `max_severity`; bug effort is category-only. |
| 8 | infrastructure | high | Antigravity had a flag mismatch, Codex repair remained schema-invalid, and Pi timed out; Claude and Grok supplied substantive 2/5 quorum. | Preserved every terminal result; harness failures did not count as reviews. |

Plan revision 7 resolves every confirmed finding and the operator-approved immutable source-identity decision. It is ready for the final all-harness convergence round.

## Recovery Review Round 3 and Operator Adjudication (2026-09-13)

All five configured local harnesses were attempted. Claude Code, Codex, and Grok produced schema-valid substantive reviews (3/5 quorum); Antigravity failed its output-format preflight and Pi returned schema-invalid string IDs. The terminal gate identified four unconfirmed high-impact judgment findings and one confirmed testability finding.

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | spec gap | high | Three producer sidecars had no hand-edit-free merge path. | **Operator accepted:** `--candidate-work PATH` is repeatable; the shared loader validates each file, merges in argument order, and rejects union duplicates. |
| 2 | resilience | high | Generic adjacent filenames could overwrite another producer batch. | **Operator accepted:** defaults are producer-specific and an explicit destination containing another generator fails unchanged. |
| 3 | correctness | high | Registry lookup order could resolve lifecycle duplicates inconsistently between ranking and intake. | **Operator accepted:** one shared resolver collapses completed/archive lineage records, preserves exactly one live match, and fails multiple live matches. |
| 4 | correctness | high | Mutable titles still influenced derived IDs despite immutable hashes. | **Operator accepted:** both derived base and hash use only the immutable source ID, with an exact ASCII slug algorithm and fallback. |
| 5 | testability | medium | Cross-producer atomic/deterministic scenarios and refine-roadmap verification were incomplete. | **Fixed:** every producer test owns those scenarios and the roadmap package runs both plan-roadmap and refine-roadmap suites. |
| 6 | consistency | medium | Existing-roadmap item-ID ownership and `source_proposal` were ambiguous. | **Fixed:** the helper assigns the next free ID from a fresh load immediately before preview; refine validates it; `source_proposal` is `provenance.source_artifact`. |
| 7 | consistency | low | Pretty-print serialization and the resolved historical question were stale or incomplete. | **Fixed:** contracts pin `indent=2`, sorted keys, and trailing newline; Plan Iteration 3 is marked resolved. |

Plan revision 8 incorporates the terminal operator adjudication and is approved for implementation.
