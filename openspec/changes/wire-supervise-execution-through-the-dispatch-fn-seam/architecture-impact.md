# Architecture Impact

**Commit**: 1b75daca
**Branch**: openspec/wire-supervise-execution-through-the-dispatch-fn-seam
**Base**: ae9576a56638d5c165792654c1b00c7451bafead

## Changed Files

The implementation changes the roadmap-runtime scheduler and checkpoint model, the Autopilot roadmap orchestrator, the supervise host adapter and protocol, dispatch schemas, and their contract/unit/integration tests. The full path mapping is recorded in [change-context.md](./change-context.md).

## Structural Diff

The changed skill scripts are outside the architecture graph Python source root (`agent-coordinator/src`), so the graph reports no feature-attributable node or edge changes. A refreshed diagnostic run found no new cycles, high-impact modules, routes, or database tables attributable to this change. The refresh also discovered 90 pre-existing TypeScript nodes because analyzer dependencies became available; that analyzer-availability delta is unrelated to this feature and its generated repository-wide artifacts were not committed.

### New Cross-Layer Flows

No service-layer flow was added. Within the skills layer, the intentional direction is `roadmap-runtime dispatch scheduler -> autopilot-roadmap orchestrator -> supervise ExecutionAdapter -> host callback`, with structured results returning through the existing `dispatch_fn` seam.

### Broken Cross-Layer Flows

None. Scoped flow validation covered 43 changed files and reported 0 findings.

### New High-Impact Nodes

None reported.

## Validation Findings

| Severity | Category | Description | File |
|----------|----------|-------------|------|
| none | flow | 0 errors, 0 warnings, 0 informational findings across 43 changed files | `docs/architecture-analysis/architecture.diagnostics.scoped.json` |
| none | dependency direction | Neutral roadmap-runtime helpers do not import the orchestrator or host adapter | `skills/roadmap-runtime/scripts/dispatch_scheduler.py` |
| none | state ownership | Orchestrator remains the phase owner; ExecutionAdapter owns host lease and launch transitions | `skills/autopilot-roadmap/scripts/orchestrator.py` |

## Parallel Zone Impact

The package DAG and overlap validator passed with no invalid parallel pair or lock overlap. Runtime concurrency is admitted only for work packages whose effective write scopes are affirmatively disjoint; missing, invalid, empty, boundless, or ambiguous scope serializes. No previously independent repository architecture zone was merged.

## Recommendations

Safe to open for review. No blocking architecture issue was found; merge-time validation should preserve the scheduler-to-orchestrator-to-host dependency direction and rerun the focused supervised-dispatch integration suite.
