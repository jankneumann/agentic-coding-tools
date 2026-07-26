# Architecture Impact

<!-- Commit: 6ce11776
     Branch: openspec/add-revision-aware-semantic-index-registry
     Implementation base: 7f9af1f1
     Main merge-base: 18d07a8a -->

## Changed Files

The capability change adds migration 029, the registry persistence module,
the pure registry model module, focused tests, contracts, and the code-search
operator guide. The generated architecture artifacts were refreshed because
their prior snapshot predated this implementation.

Core implementation files:

- `agent-coordinator/database/migrations/029_revision_aware_code_search_indexes.sql`
- `packages/code-search/src/code_search_pkg/registry.py`
- `packages/code-search/src/code_search_pkg/registry_models.py`
- `packages/code-search/src/code_search_pkg/identifiers.py`
- `packages/code-search/src/code_search_pkg/__init__.py`

## Structural Diff

`make architecture-diff BASE_SHA=7f9af1f1` reported:

- 201 nodes added, 1 removed
- 114 edges added, 14 removed
- 1 new dependency cycle
- 3 new high-impact modules
- 4 newly visible untested routes
- 3 newly visible database tables

The architecture baseline was from May 2026, so this is a catch-up diff rather
than a feature-only diff. The feature-relevant additions are
`public.code_search_indexes`, its two indexes, and its storage/canonical
triggers. `public.issue_comments`, the rediscovered legacy
`public.code_search_registry`, the `audit`/`audit_triage` cycle, all three
high-impact Python nodes, and all four routes predate this implementation.

### New Cross-Layer Flows

No runtime cross-layer flow is added in this registry-foundation change. The
future incremental indexer will consume:

`resolved Git revision -> SemanticIndexRegistry -> code_search_indexes -> isolated storage`

The current architecture graph records the SQL boundary but not the
`packages/code-search` Python module.

### Broken Cross-Layer Flows

None in the changed-file scope. Scoped flow validation reported zero errors,
warnings, or informational findings.

### New High-Impact Nodes

No feature-relevant high-impact node was introduced. The three reported nodes
(`audit_triage`, `_run_git`, and `_parse_h1_title`) are stale-baseline catch-up.

## Validation Findings

| Severity | Category | Description | File |
|----------|----------|-------------|------|
| resolved | structure | Split the 593-line registry into a 413-line persistence module and a 205-line pure model module. | `packages/code-search/src/code_search_pkg/registry.py` |
| warning | analyzer coverage | The default Python analyzer scans `agent-coordinator/src` only, so the new package modules are absent from the canonical graph. | `Makefile` |
| warning | validator wiring | `make architecture-validate` points to a removed `validate_schema.py`; direct sibling-skill validators passed. | `Makefile` |
| info | baseline | Global diff findings include unrelated changes accumulated since the May architecture snapshot. | `docs/architecture-analysis/architecture.diff.json` |

Direct validation evidence:

- architecture graph schema: pass
- changed-file flow validation: 0 findings
- changed-file structural linters: pass
- full graph flow validation: 0 errors, 2,378 warnings, 92 informational findings

## Parallel Zone Impact

The SQL table, indexes, and triggers form a new persistence zone linked to the
legacy repository registry. No previously independent runtime Python zones
merge in this change because the registry module is not yet called by the
indexer or query path. The package analyzer blind spot prevents canonical zone
IDs for `registry.py` and `registry_models.py`; their separation remains
enforced by imports, tests, and the structural linter.

## Recommendations

**Safe to merge with recorded validation warnings.** The feature-scoped graph
and structural checks pass, and the global cycle/high-impact/route findings are
not caused by this change. Follow-up work should repair architecture validator
wiring and include `packages/code-search` in multi-root analysis so future
refreshes can represent the Python-to-registry boundary.
