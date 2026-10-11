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

## PLAN_REVIEW (autopilot, multi-vendor `converge()`)

Round 1 of `converge(review_type="plan", min_quorum=2)`: 5 vendors dispatched;
`claude_code` (fable) and `pi` (nemotron-3-ultra) succeeded, so quorum 2/2 was met.
`codex` returned findings that failed the review-findings schema (string ids),
`antigravity` timed out at 240s, and `grok` failed because its CLI is too old
(HTTP 426, 1.0.5 < 1.0.13). Consensus: 0 confirmed, 12 unconfirmed, 0 blocking,
so the loop converged in round 1. Checkpoint: `.review-cache/round-1/`.

The orchestrator then adjudicated the single-vendor findings, including the
two `high` findings from codex's schema-rejected output, and applied them as a
PLAN_FIX sub-step:

| Source | Criticality | Finding | Disposition |
|--------|-------------|---------|-------------|
| claude_code#1 + codex#R1-002 | medium/high | The no-window scenario carried the general trigger and check obligations, and the check was required only "before touching main", so an unauthorized run could still discover, remediate, or write branches. | Fixed: new scenario "Scheduled invocation names a window and passes authorization first" (check before any work); the no-window scenario is reduced to check-fails, main untouched. D6 updated. |
| codex#R1-001 | high | The cadence was declared but nothing required a trigger to observe it. | Fixed: the trigger MUST start only at times the cadence permits; enforcement belongs to the scheduler (ri-13). D6 notes that the check does not consult cadence. |
| claude_code#2 | medium | "(including the `merge` gate)" implied a gate applicability that the base spec does not define for sync-point skills. | Fixed: the window changes no disposition; gate applicability is defined by the change that adds the scheduled caller (ri-12/ri-13). Proposal updated. |
| claude_code#3 | medium | `write_allow` omitted `docs/decisions/{skill-workflow,trust-posture}.md`, which the plan diff already writes. | Fixed in work-packages.yaml. |
| codex#R1-003 | medium | The spec called `cadence` a cron expression, but D4 validates shape only. | Fixed: the spec defines a cron-shaped string and requires the scheduler to refuse unschedulable windows; D4 states the gap explicitly. |
| codex#R1-004 | medium | The kebab-case `id` constraint had no scenario coverage. | Fixed: added to the requirement text and the malformed-window scenario. |
| codex#R1-005 | medium | The schema tests did not pin null, `[]`, or wrong-type parity with the loader. | Fixed: task 2.3 extended. |
| claude_code#4 | low | "not a list" conflicted with `null` = no windows. | Fixed: "neither `null` nor a list". |
| claude_code#5 | low | Unknown-skill `ValueError` and absent-posture input were missing from the spec. | Fixed: spec requirement and scenario; D6; task 2.1. |
| claude_code#6,#7,#8; pi#1-4 | low | README filed under the openapi contract sub-type; source and ceiling are mandatory for non-PR skills; loop-state gate signals are stale or the audit sink failed; restatements of accepted D4 and single-package decisions. | Accepted, no change (all low; pi items restate decisions already recorded above). |

Post-fix: `openspec validate --strict` valid; `validate_work_packages.py` VALID.
