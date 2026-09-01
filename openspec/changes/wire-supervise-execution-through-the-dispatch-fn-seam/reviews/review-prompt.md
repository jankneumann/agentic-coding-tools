# Independent plan review request

Review the OpenSpec change `wire-supervise-execution-through-the-dispatch-fn-seam`.

Read-only inputs:

- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/proposal.md`
- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/design.md`
- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/tasks.md`
- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/specs/**/spec.md`
- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/contracts/**`
- `openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/work-packages.yaml`

Pay particular attention to:

1. Whether the prepare/apply host bridge genuinely uses the existing `dispatch_fn` seam without introducing a second per-change phase machine.
2. Whether the durable acknowledgement/go barrier prevents pre-ack Autopilot entry, pre-go takeover is generation-safe, and post-go absence becomes non-resumable quarantine unless positive death evidence exists.
3. Whether all package writes (including integration and runtime mirrors) are classified conservatively, and intersecting or ambiguous globs fail closed to a schema-valid serial request.
4. Whether only pending-gate or policy-pause parking is approval-resumable, while unknown liveness uses distinct quarantine with an unreleased uncertain lease.
5. Whether state/outcome conditionals, exact success/parked isolation evidence, recursively bounded case-insensitive secret-sanitized context, and the concrete two-child parent-event capture adapter are fully specified and TDD-owned.
6. Whether explicit prepare_delegated_batch/apply_delegated_batch semantics truthfully keep dispatch_fn synchronous and once per result, with concurrency measured only at host task handles.
7. Spec/contract/task/work-package traceability, TDD order, DAG validity, package scope, and compatibility.

Output only one JSON object conforming to `openspec/schemas/review-findings.schema.json`.
Set `review_type` to `plan`, `target` to the exact change ID, and populate
`reviewer_vendor`. Every finding must include `axis`, `severity`, and a description
whose prefix matches severity. If no defect is found, emit at least two positive
`severity: "none"` observations on different axes.

Do not modify repository files.
