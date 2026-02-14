# Change: Add Codebase Analysis Architecture

## Why

When implementing complex features across a multi-layer codebase (Python backend, TypeScript/React frontend, Postgres database), AI agents frequently produce inconsistent patterns across modules, fail to connect flows end-to-end (UI -> API -> service -> DB), and generate tests that don't sufficiently exercise the intended functionality. This happens because agents lack a structural understanding of the codebase — they see individual files but not the architectural relationships between them.

The core problem is not that agents can't analyze individual files — it's that there is no **system map** connecting the layers. Three separate analysis reports (Python call graph, TS dependency graph, Postgres schema) don't solve the "disconnected flows" problem. What's needed is a single canonical graph with cross-language linking edges, confidence tracking, and validation loops that verify both connectivity and test coverage.

Static analysis and call graph generation can produce machine-readable architecture artifacts that serve three purposes: (1) **planning input** that gives agents accurate context about how the codebase is structured, what patterns are used, and where modification boundaries lie, (2) **implementation validation** that verifies code changes are complete, consistent, and properly connected across all layers, and (3) **CI diagnostics** that catch broken flows, missing tests, and architectural drift before merge.

## What Changes

- **New capability: `codebase-analysis`** — analysis scripts, canonical graph compiler, and validation tooling for multi-layer codebases
- **Canonical graph schema** — a single normalized JSON model (`architecture.graph.json`) with `nodes[]`, `edges[]`, `entrypoints[]`, and `snapshots[]` that all per-language analyzers feed into
- **Python AST analyzer** (`scripts/analyze_python.py`) — extracts call graphs, function/class metadata, decorator-based entry points, import graphs, and called-by relationships using Python's `ast` stdlib
- **TypeScript analyzer** (`scripts/analyze_typescript.ts`) — extracts component hierarchy, hook usage, import graphs, JSX child relationships, and API client call sites using ts-morph
- **TypeScript guardrails** — dependency-cruiser configuration for architectural rule enforcement (layer boundaries, forbidden dependencies, circular dependency detection)
- **Database schema analyzer** (`scripts/analyze_postgres.py`) — extracts table definitions, FK relationships, indexes, and stored functions from migration files (live DB optional)
- **Graph compiler** (`scripts/compile_architecture_graph.py`) — reads per-language outputs, normalizes into canonical schema, performs cross-language linking (TS→Python routes, Python→DB tables), and emits the unified graph with confidence/evidence on every edge
- **Flow validator** (`scripts/validate_flows.py`) — checks reachability (every entrypoint has a downstream path), test coverage alignment (critical flows have at least one test), and reports diagnostics
- **View generator** — produces Mermaid diagrams from the canonical graph: container view, component views, DB ERD, and feature slice views
- **CI integration** — `make architecture` for full generation, `make architecture:diff` for baseline comparison, diagnostics as CI gate
- **Committed artifacts** — `.architecture/` artifacts committed to track structural evolution; summaries for agent context, full graph for deep analysis
- **Skill integration** — `plan-feature`, `implement-feature`, and `validate-feature` skills updated to consult and validate against architecture artifacts

## Impact

- Affected specs: None directly modified (skill integration is defined as part of the new codebase-analysis capability spec)
- New spec: `codebase-analysis` — canonical graph schema, per-language analysis, cross-language linking, flow validation, CI gates, view generation
- Affected code: New `scripts/` directory with analysis tools, new `.architecture/` output directory, updated skill prompts
- Affected skills: `plan-feature` (consult artifacts for planning context), `implement-feature` (run validation before PR), `validate-feature` (include architecture diagnostics)
- **BREAKING**: None — purely additive
