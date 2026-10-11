# Plan Findings: amend-skill-workflow-spec-for-policy-authorized-sync-windows

Threshold: medium. Baseline `openspec validate --strict`: valid.

## Iteration 1

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | consistency | high | `skill-workflow` "Merge Conductor Invokes Iterate Skills" still says "The merge skill remains the user-invoked sync-point for merges into `main`", contradicting the amended sync-point requirement. | Added a MODIFIED delta for that requirement (base scenarios preserved) plus a scheduled-conductor scenario; Impact updated to two MODIFIED requirements. |
| 2 | feasibility | high | A2/D3 cite `discover_prs.py` as the origin vocabulary, but origins are emitted by `skills/shared/github_classifier.classify_pr` and exist only as string literals, so the promised parity test had nothing to pin against. | New task 2.0 exports `PR_ORIGINS` from `github_classifier.py` with a coverage test; parity test pins `SYNC_SOURCES == PR_ORIGINS`; A2, D3, Impact and write scope corrected. Detailed (not folded PR-card) origins chosen and justified. |
| 3 | consistency | medium | D5 kept declared window order in the digest, contradicting the existing digest invariant that front-matter ordering does not change the digest. | Windows are sorted by `id` before hashing; spec scenario asserts reorder-invariance. |
| 4 | testability | medium | The `skill-workflow` scheduled-invocation scenarios assume a skill can detect a non-user trigger; no scheduled caller or invocation signal exists in this change, so they cannot be verified here. | Scenario reworded to put the obligation on the trigger (must name a window id) and on the skill (must call the authorization check). D6 gains an explicit verification boundary naming ri-12/ri-13 as owners of call-site tests; task 1.1 records the trace. |
| 5 | assumptions | medium | Unstated relation between a sync window and gate dispositions (notably `merge`): does a window imply `auto`? | Decided fail-closed: a window is necessary, never sufficient (new A5, D8, and a spec scenario). Not surfaced interactively (supervised child run); recorded as a decision. |
| 6 | completeness | medium | Spec silent on `null` windows, non-list container, non-mapping entries, empty or repeated list values, and the kebab-case `id` pattern; unclassified PR kinds were fail-closed only in design. | Spec requirement and scenarios extended (new "Malformed sync_windows container is rejected" scenario); ceiling scenario rejects unknown kinds. |
| 7 | assumptions | medium | Including windows in the single digest changes how the supervisor treats a window edit: `posture_block` reuse is re-evaluated and in-flight children lose `auto` until rebased. Not stated. | New A6 and a design Risk documenting the consequence and the rejected alternative (separate digest); template guidance task 3.1 updated; digest-consumer test suites added to verification. |
| 8 | completeness | medium | Task 1.1 asked to "author" deltas that already exist; verification ran only `skills/shared/tests`, missing digest consumers (`supervise`, `autopilot`) and the merge-skill classifier tests. | 1.1 restated as confirm-and-validate; checkpoint and `work-packages.yaml` verification extended; `plan_revision` bumped to 2. |
| 9 | clarity | low | Source/ceiling bounds read as applying to every sync-point skill even when it selects no PRs. | Bounded to "whenever it selects, remediates, or merges pull requests". |
| 10 | testability | low | `show` output change had no test. | Added to task 2.1 test list. |

## Iteration 2

Re-read of all artifacts after iteration 1 fixes. `openspec validate --strict`
valid; `validate_work_packages.py` VALID; baseline of the declared verification
suites green (1448 passed).

| # | Type | Criticality | Description | Disposition |
|---|------|-------------|-------------|-------------|
| 1 | parallelizability | low | Single sequential package; max parallel width 1 (2.0 is independent of 2.1 but tiny). | Accepted: ~350 LOC, shared test file and shared `SyncWindow` shape make splitting a net loss. Documented at the top of tasks.md. |
| 2 | completeness | low | Cadence validation is shape-only; out-of-range values such as `99 * * * *` pass. | Accepted per D4; next-fire computation belongs to ri-13, which will reject unschedulable expressions. |
| 3 | scope | low | Session-log open question on `@daily` macros remains. | Deferred to ri-13. |

No findings at or above medium. Converged.
