Review the OpenSpec plan for `write-durable-state-artifacts-guide` as read-only input.

Read exactly these planning artifacts first:

- `openspec/changes/write-durable-state-artifacts-guide/proposal.md`
- `openspec/changes/write-durable-state-artifacts-guide/design.md`
- `openspec/changes/write-durable-state-artifacts-guide/tasks.md`
- `openspec/changes/write-durable-state-artifacts-guide/specs/skill-workflow/spec.md`
- `openspec/changes/write-durable-state-artifacts-guide/contracts/README.md`
- `openspec/changes/write-durable-state-artifacts-guide/work-packages.yaml`

This is a fresh canonical plan review after four noisy rounds. Review the plan itself, not implementation quality or whether completed task checkboxes should already be merged. The change is intentionally documentation-only and uses one sequential package because the guide, skill references, generated mirrors, and structural tests form one semantic drift boundary.

Evaluate specification completeness, cross-document consistency, task traceability and sizing, work-package scope/DAG validity, testability, compatibility, resilience, security, performance, observability, and the exact eight-step rehydration-order contract. A finding must cite concrete artifact evidence and explain a user-visible or implementation-relevant consequence. Do not invent requirements for runtime/API/database behavior that the proposal explicitly excludes. Do not report style preferences or already-resolved historical review commentary as blockers.

Output ONLY valid JSON conforming to `openspec/schemas/review-findings.schema.json`, with `review_type: "plan"` and target `write-durable-state-artifacts-guide`. Every finding must include `axis`, `severity`, `type`, `criticality`, `description`, `resolution`, and `disposition`; descriptions must use the severity prefix required by the schema. If there is no actionable issue, include a small set of `severity: "none"`, `disposition: "accept"` positive observations across at least two relevant axes to prove the review was substantive.
