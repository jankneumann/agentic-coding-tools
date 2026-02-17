# Architecture Impact

<!-- Commit: short SHA
     Branch: openspec/<change-id>
     Base: merge-base SHA against main -->

## Changed Files

<!-- List files changed on this branch relative to main (git diff --name-only main...HEAD) -->

## Structural Diff

<!-- Output of make architecture-diff BASE_SHA=<merge-base-sha>
     Report: new nodes, removed nodes, new edges, removed edges, new cycles -->

### New Cross-Layer Flows

<!-- Flows that didn't exist in the baseline. Format:
     entrypoint -> intermediate -> ... -> terminal (new/modified) -->

### Broken Cross-Layer Flows

<!-- Flows that existed in the baseline but are now broken or disconnected -->

### New High-Impact Nodes

<!-- Nodes with many transitive dependents that were introduced or promoted by this change -->

## Validation Findings

<!-- Output of make architecture-validate scoped to changed files
     Errors: must fix before merge
     Warnings: should investigate
     Info: awareness only -->

| Severity | Category | Description | File |
|----------|----------|-------------|------|
|          |          |             |      |

## Parallel Zone Impact

<!-- Which parallel zones from parallel_zones.json are affected by this change?
     Did any zones merge (previously independent modules now coupled)?
     Did any new zones form? -->

## Recommendations

<!-- Summary: safe to merge, needs investigation, or blocking issues found -->
