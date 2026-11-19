# Architecture Impact: audit-vendor-headless-auth-and-terms

Commit: c15c3d6
Branch: claude/eloquent-edison-tn8alg
Base: f8a7da6 (merge-base against main)

## Changed Files

- `docs/guides/vendor-auth-audit.yaml` (new): the audit table
- `docs/guides/vendor-auth-audit.md` (new): the guide
- `docs/guides/documentation.md`: index entry
- `docs/proposals/factory-local-cloud-split.md`: one corrected statement
- `openspec/roadmaps/sandboxed-flow/claude-auth-strategy.md`: corrected quotes and a verification note
- `skills/vendor-status/scripts/observe_vendor_auth.py` (new) and its runtime copies
- `skills/tests/vendor-status/` (new): three test files
- `skills/pyproject.toml`: test path

## Structural Diff

`make architecture-diff BASE_SHA=f8a7da6`: +150/-40 nodes, +43/-3 edges, 0 new
cycles, 2 new high-impact modules, 3 routes without tests, 2 database tables.
These figures match the previous item's run and come from baseline staleness.
This change adds no module that another module imports.

### New Cross-Layer Flows

None.

### Broken Cross-Layer Flows

None.

### New High-Impact Nodes

None from this change.

## Validation Findings

`validate_flows.py` on the changed files: 0 entrypoints, 0 findings.

`run_architecture_linters.py` on the changed files:

| Severity | Category | Description | File |
|---|---|---|---|
| nit | architecture | 771 lines, over the 500-line limit; the length predates this change | `docs/proposals/factory-local-cloud-split.md` |

## Parallel Zone Impact

None. The script is standalone and stdlib-only.

## Recommendations

- Later roadmap items should read `vendor-auth-audit.yaml` rather than the
  guide, and should refuse to depend on a mechanics field whose `evidence` is
  not `observed`.
