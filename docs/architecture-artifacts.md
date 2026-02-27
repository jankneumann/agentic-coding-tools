# Architecture Artifacts

The `docs/architecture-analysis/` directory contains auto-generated structural analysis of the codebase. These artifacts are committed and should be consulted by agents during planning and validation.

## Key Files

### Layer 1 — Code Analysis
- `docs/architecture-analysis/python_analysis.json` — Python module/class/function extraction
- `docs/architecture-analysis/ts_analysis.json` — TypeScript component/hook/route extraction
- `docs/architecture-analysis/postgres_analysis.json` — SQL table/index/function/trigger extraction

### Layer 2 — Graph & Insights
- `docs/architecture-analysis/architecture.graph.json` — Full canonical graph (nodes, edges, entrypoints)
- `docs/architecture-analysis/architecture.summary.json` — Compact summary with cross-layer flows, stats, disconnected endpoints
- `docs/architecture-analysis/architecture.diagnostics.json` — Validation findings (errors, warnings, info)
- `docs/architecture-analysis/parallel_zones.json` — Independent module groups for safe parallel modification
- `docs/architecture-analysis/treesitter_enrichment.json` — Tree-sitter pattern analysis (comments, exceptions, type hints, security)
- `docs/architecture-analysis/comment_insights.json` — TODO/FIXME hotspots, documentation coverage, node-marker map
- `docs/architecture-analysis/pattern_insights.json` — Exception handling summary, type hint coverage, security findings

### Layer 3 — Reports & Views
- `docs/architecture-analysis/architecture.report.md` — Narrative architecture report
- `docs/architecture-analysis/views/` — Auto-generated Mermaid diagrams

## Usage
- **Before planning**: Read `architecture.summary.json` to understand component relationships and existing flows
- **Before implementing**: Check `parallel_zones.json` for safe parallel modification zones
- **Code quality review**: Read `pattern_insights.json` for exception handling, type coverage, and security findings
- **Tech debt tracking**: Read `comment_insights.json` for TODO/FIXME hotspots and documentation coverage
- **After implementing**: Run `make architecture-validate` to catch broken flows
- **Refresh**: Run `make architecture` to regenerate all artifacts

## Refresh Commands
```bash
make architecture              # Full refresh (includes tree-sitter enrichment if available)
make architecture-enrichment   # Tree-sitter enrichment only (requires scripts venv)
make architecture-validate     # Validate only
make architecture-views        # Regenerate views only
make architecture-report       # Generate narrative report
make architecture-diff BASE_SHA=<sha>  # Compare to baseline
make architecture-feature FEATURE="file1,file2"  # Feature slice
make scripts-setup             # Install scripts venv (tree-sitter + analysis deps)
```

## Tree-sitter Enrichment

The enrichment pipeline uses tree-sitter for concrete syntax tree (CST) analysis:

1. **SQL Analyzer** (`scripts/analyze_sql_treesitter.py`) — CST-based SQL migration parsing, replaces regex when available
2. **Enrichment Engine** (`scripts/enrich_with_treesitter.py`) — Cross-language pattern extraction (Python + TypeScript)
3. **Comment Linker** (`scripts/insights/comment_linker.py`) — Maps comments/TODOs to architecture graph nodes
4. **Pattern Reporter** (`scripts/insights/pattern_reporter.py`) — Aggregates findings into actionable insights

Setup: `make scripts-setup` (installs tree-sitter dependencies in `scripts/.venv`)
