# Architecture Artifacts

The `docs/architecture-analysis/` directory contains auto-generated structural analysis of the codebase. These artifacts are committed and should be consulted by agents during planning and validation.

## Key Files
- `docs/architecture-analysis/architecture.summary.json` — Compact summary with cross-layer flows, stats, disconnected endpoints
- `docs/architecture-analysis/architecture.graph.json` — Full canonical graph (nodes, edges, entrypoints)
- `docs/architecture-analysis/architecture.diagnostics.json` — Validation findings (errors, warnings, info)
- `docs/architecture-analysis/parallel_zones.json` — Independent module groups for safe parallel modification
- `docs/architecture-analysis/architecture.report.md` — Narrative architecture report
- `docs/architecture-analysis/views/` — Auto-generated Mermaid diagrams

## Usage
- **Before planning**: Read `architecture.summary.json` to understand component relationships and existing flows
- **Before implementing**: Check `parallel_zones.json` for safe parallel modification zones
- **After implementing**: Run `make architecture-validate` to catch broken flows
- **Refresh**: Run `make architecture` to regenerate all artifacts

## Refresh Commands
```bash
make architecture              # Full refresh
make architecture-validate     # Validate only
make architecture-views        # Regenerate views only
make architecture-diff BASE_SHA=<sha>  # Compare to baseline
make architecture-feature FEATURE="file1,file2"  # Feature slice
```
