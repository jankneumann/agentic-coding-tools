Review the implementation plan for OpenSpec change `add-dispatch-sandbox-enforcement`.

Read every artifact under:

- `openspec/changes/add-dispatch-sandbox-enforcement/proposal.md`
- `openspec/changes/add-dispatch-sandbox-enforcement/design.md`
- `openspec/changes/add-dispatch-sandbox-enforcement/specs/`
- `openspec/changes/add-dispatch-sandbox-enforcement/contracts/`
- `openspec/changes/add-dispatch-sandbox-enforcement/tasks.md`
- `openspec/changes/add-dispatch-sandbox-enforcement/work-packages.yaml`

Then inspect the referenced current code, especially the dg-03/dg-05/dg-06 contracts,
`agent-coordinator/src/network_policies.py`, `agent-coordinator/src/audit.py`,
`agent-coordinator/src/agents_config.py`,
`skills/parallel-infrastructure/scripts/review_dispatcher.py`, and
`skills/autopilot/scripts/provider_dispatch.py`.

Evaluate correctness, architecture, security, resilience, observability, compatibility,
testability, work-package DAG/scope, and whether the plan can actually satisfy every acceptance
scenario. Pay special attention to immutable routing-decision consumption, SRT 0.0.77 lifecycle,
policy precedence/wildcards, fail-open durability, subprocess coverage, linked-worktree Git
metadata, environment/proxy handling, and real-runtime validation.

Do not edit anything. Report only actionable plan findings; do not repeat issues already resolved
by the plan. Evidence must name real paths and line ranges. A zero-finding review is allowed if the
plan is implementation-ready.

This is a pre-implementation plan review. Do not report that a planned module, migration, test,
package directory, or behavior is absent from the current code when the tasks and work-package
scope already require creating it. Report only omissions, contradictions, unsafe decisions, or
unexecutable/untestable work in the plan itself.

REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
`id` MUST be a JSON integer (1, 2, 3...), not a string label.
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.
