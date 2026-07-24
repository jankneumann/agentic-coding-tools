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

### Provenance & Freshness (revision-aware)
- `docs/architecture-analysis/architecture.provenance.json` — Records the exact
  analyzed Git SHA, dirty-input state, architecture producer version, relevant
  **input fingerprint**, generation mode, and SHA-256 digests of every owned
  artifact. Written by every successful `make architecture-refresh`.

Freshness is **content-based and mtime-independent**: an artifact is stale only
when a relevant input changed, the producer/tool identity changed, or an owned
artifact's bytes drifted from the recorded digest — never merely because the
graph file is "old". Two refreshes of the same revision and inputs produce
byte-identical artifacts (deterministic clock via `SOURCE_DATE_EPOCH`), so a
repeat refresh yields no repository diff.

Durable cross-process status is owned by `project-context-runtime`
(`add-durable-context-refresh-records`): the architecture adapter records one
canonical `producer_id=architecture` `ProducerResult` per `(repository, revision)`
operation and projects it onto the legacy refresh RPC status. The architecture
producer never finalizes the whole project-context operation.

Commands:
- `make architecture-refresh` — deterministic stage → validate → promote → write
  provenance. A failed generation preserves the last known-good committed set.
- `make architecture-check` — read-only freshness check; exits 0 only when
  `fresh`, and prints exact drift reason codes and stale artifact paths.
- `affected_tests.py --repo-root <path>` — content-based provenance gate for
  merge-train test selection (falls back to the full suite when not fresh).

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
make architecture-enrichment   # Tree-sitter enrichment only (requires skills venv)
make architecture-validate     # Validate only
make architecture-views        # Regenerate views only
make architecture-report       # Generate narrative report
make architecture-diff BASE_SHA=<sha>  # Compare to baseline
make architecture-feature FEATURE="file1,file2"  # Feature slice
cd skills && uv sync --all-extras  # Install skills venv (tree-sitter + analysis deps)
```

## Tree-sitter Enrichment

The enrichment pipeline uses tree-sitter for concrete syntax tree (CST) analysis:

1. **SQL Analyzer** (`skills/refresh-architecture/scripts/analyze_sql_treesitter.py`) — CST-based SQL migration parsing, replaces regex when available
2. **Enrichment Engine** (`skills/refresh-architecture/scripts/enrich_with_treesitter.py`) — Cross-language pattern extraction (Python + TypeScript)
3. **Comment Linker** (`skills/refresh-architecture/scripts/insights/comment_linker.py`) — Maps comments/TODOs to architecture graph nodes
4. **Pattern Reporter** (`skills/refresh-architecture/scripts/insights/pattern_reporter.py`) — Aggregates findings into actionable insights

Setup: `cd skills && uv sync --all-extras` (installs tree-sitter dependencies in `skills/.venv`)
