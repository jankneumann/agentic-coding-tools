# dg-04 plan review

Independently review the OpenSpec plan for change `implement-the-task-router-vendor-x-location-x-model` in this checkout. Read proposal.md, design.md, tasks.md, work-packages.yaml, specs/task-routing/spec.md, and every file under contracts/. Check completeness, internal consistency, feasibility, testability, compatibility, security, observability, and package parallelizability.

The review must enforce these boundaries:

- Extend only the existing `POST /routing/select_model` and MCP mirror; introducing `POST /route/task` is a blocking contract error.
- Use dg-01 `VendorRegistryService` in-process with exact lane-to-catalog association. Name or publisher heuristics are forbidden.
- Make task profile, execution location, isolation, and dispatch mode explicit and typed.
- Apply registry feasibility before dg-00 utility scoring and preserve dg-00 static fallback equality.
- Use a strict, versioned `routing.yaml` policy.
- Keep assignment/provenance additive and persist an authoritative routing decision plus an honestly linked durable coordinator audit event.
- Local fallback provenance must state it was local and not durably persisted.
- Do not pull dg-05 admission controls or dg-06 approval workflows into scope.

For every finding, cite the precise file and existing text when possible. Report no finding when the plan already resolves the concern.

REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
The `id` field MUST be an integer, not a string label.
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.
