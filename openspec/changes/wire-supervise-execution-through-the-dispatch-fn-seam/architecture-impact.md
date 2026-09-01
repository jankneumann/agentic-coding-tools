# Architecture Impact

**Commit**: 3b5a1fb06d8ae3662414985d06092016015a6c96
**Branch**: openspec/wire-supervise-execution-through-the-dispatch-fn-seam
**Base**: ae9576a56638d5c165792654c1b00c7451bafead

## Changed Files

The PR changes 81 tracked files relative to its roadmap base, primarily the roadmap-runtime scheduler/checkpoint model, Autopilot roadmap orchestration, the supervise host adapter/protocol, schemas, OpenSpec evidence, and focused tests.

## Structural Diff

The repository-specific architecture producer completed successfully and a second ensure reported fresh. The baseline graph diff reported:

- Nodes: +0 / -0
- Edges: +0 / -0
- New cycles: 0
- New high-impact modules: 0
- Untested new routes: 0
- New database tables: 0

The changed skill scripts sit outside the agent-coordinator graph's Python source root, so the graph has no feature-attributable node or edge delta.

### New Cross-Layer Flows

No service-layer flow was added. The intended skills-layer direction remains roadmap-runtime scheduler -> autopilot-roadmap orchestrator -> supervise ExecutionAdapter -> host callback, with structured outcomes returning through dispatch_fn.

### Broken Cross-Layer Flows

None. Scoped validation covered 81 changed files and reported 0 errors, warnings, or informational findings.

### New High-Impact Nodes

None reported.

## Validation Findings

| Severity | Category | Description | Files |
|----------|----------|-------------|-------|
| none | graph diff | No new cycles, high-impact modules, untested routes, or tables | docs/architecture-analysis/architecture.diff.json |
| none | scoped flows | 0 findings across 81 changed files | docs/architecture-analysis/architecture.diagnostics.scoped.json |
| medium (advisory nit) | file size | Seven generated context checkpoint JSON files exceed 500 lines | openspec/changes/wire-supervise-execution-through-the-dispatch-fn-seam/context-checkpoints/*.json |
| medium (advisory nit) | file size | Three touched schema artifacts exceed 500 lines | delegated-dispatch-attempt.schema.json and checkpoint schema mirrors |
| medium (advisory nit) | file size | Three touched Python modules exceed 500 lines | orchestrator.py, models.py, execution.py |
| medium (advisory nit) | file size | Two touched test modules exceed 500 lines | test_supervised_dispatch.py, test_execution.py |

Architecture gating is configured as advisory. The 15 file-size findings are reported and not suppressed.

## Parallel Zone Impact

The package DAG, scope-overlap, lock-overlap, and parallel-zone validation all pass. Runtime batching admits concurrency only for affirmatively disjoint effective write scopes; no repository architecture zones were merged by the graph.

## Recommendations

The architecture graph and flow results do not block merge. The feature as a whole is not merge-ready because validation independently found a spec-compliance defect in second-request overlap proof and incomplete durable work-package evidence; resolve those findings and re-run validation.
