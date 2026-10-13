# Plan Findings: multiplayer-principles-guide

Threshold: medium. Max iterations: 3.

## Iteration 1

Baseline: the change was a `plan-roadmap` scaffold (`openspec validate --strict` passed,
but proposal, design, tasks, and spec carried template placeholders). A prior
PLAN_ITERATE attempt rewrote all four documents before its container restarted; those
edits (commit `f4e388e`, never pushed) were restored onto the feature branch and
re-reviewed in full rather than trusted. Every repository path and change-id they cite
was checked against the tree.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | completeness | critical | Scaffold proposal lacked Why / What Changes / Impact; tasks were template placeholders; design had only open questions | Restored rewrite (f4e388e): full proposal, design D1-D8, five traced tasks |
| 2 | testability | high | Scaffold requirements restated acceptance outcomes as "WHEN implemented THEN ..." with no failure path | Restored rewrite: six requirements, each with success and failure scenarios checked by a guard test |
| 3 | assumptions | high | Solo vs team mode undefined; roadmap's "solo mode adds nothing" guarantee contradicted siblings that add passive output in solo mode | Restored rewrite: design D2 (resolver-based definition plus passive-output clause) |
| 4 | feasibility | high | Guard test directory `skills/tests/multiplayer-collaboration` was not registered in `skills/pyproject.toml` `testpaths`; `tests/ci_coverage/test_ci_test_coverage.py` fails for any unreached test directory, and the planned verify step (naming the directory) bypasses `testpaths`, so the gap was invisible locally | New requirement *Guard test runs in the default CI sweep*; task 1.2; Impact and D7 updated |
| 5 | testability | medium | *Addressed by* / *Delivered by* cells said "name a change-id" without a parseable format | Spec: every backticked token in those cells is a change-id; at least one per cell |
| 6 | testability | medium | "finds the terms principal, solo mode, and team mode defined" was not mechanically checkable | Spec: bold-term definitions `**Principal**`, `**Solo mode**`, `**Team mode**` |
| 7 | testability | medium | Principle titles "from the roadmap" could only be checked by reading a file that moves on archival | Spec: test checks `### P<n>. ` prefix and order; title wording is a review check |
| 8 | testability | medium | Scenario *Archival of a cited change does not fail the guard* had no test that exercises it before any sibling archives | Spec scenario and task 1.1: `tmp_path` case with an archived-only change dir |
| 9 | consistency | medium | tasks.md cited "D1-D7" while design.md defines D8 | Corrected to D1-D8 |
| 10 | testability | medium | Per-skill "Unchanged" convention was listed as a test assertion but cannot be checked mechanically (the test cannot know which skills are unaffected) | Spec/design: test checks non-empty cells; non-"Unchanged" solo cells limited to passive output; accuracy is a review check |
| 11 | completeness | low | D3 mapping omitted `attention-budgets-digests` (P1, P3) and `trust-posture-calibration` (P8), which inherit their split capability's *Serves* list | Added; D3 states the split-capability inheritance rule |
| 12 | clarity | low | Link targets with `#fragment` would fail path resolution | D7 / task 1.1: strip fragment before resolving |

Parallelizability: Independent 4 (1.2, 2.1, 3.1, 4.1 after 1.1) | Sequential chains 1 |
Max parallel width 4 | File overlap: none.

## Iteration 2

Re-read all documents after iteration 1 edits. No findings at or above medium.

Remaining low findings (not fixed):
- No sibling roadmap item declares `depends_on: [ri-01]` (recorded in design.md *Open
  Questions*; a `/refine-roadmap` concern, out of scope for this change).
- The guide is not shipped by `install.sh` (recorded; candidate for `toolkit-consistency`).
