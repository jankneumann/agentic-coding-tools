# Change: Add Codebase Analysis Architecture

## Why

When implementing complex features across a multi-layer codebase (Python backend, TypeScript/React frontend, Postgres database), AI agents frequently produce inconsistent patterns across modules, fail to connect flows end-to-end (UI -> API -> service -> DB), and generate tests that don't sufficiently exercise the intended functionality. This happens because agents lack a structural understanding of the codebase—they see individual files but not the architectural relationships between them.

Static analysis and call graph generation can produce machine-readable architecture artifacts that serve two purposes: (1) **planning input** that gives agents accurate context about how the codebase is structured, what patterns are used, and where modification boundaries lie, and (2) **implementation validation** that verifies code changes are complete, consistent, and properly connected across all layers.

## What Changes

- **New capability: `codebase-analysis`** — analysis scripts and artifact generation for Python, TypeScript, and Postgres codebases
- **Python AST analyzer** (`scripts/analyze_python.py`) — extracts call graphs, function/class metadata, decorator-based entry points, import graphs, and called-by relationships
- **TypeScript AST analyzer** (`scripts/analyze_typescript.ts`) — extracts component hierarchy, hook usage, import graphs, JSX child relationships, and export structures using ts-morph
- **Database schema analyzer** (`scripts/analyze_postgres.py`) — extracts table definitions, FK relationships, indexes, and stored functions from either a live connection or migration files
- **Cross-layer flow tracer** (`scripts/trace_flows.py`) — connects frontend API calls to backend route handlers to database operations, producing end-to-end flow maps
- **Implementation validator** (`scripts/validate_implementation.py`) — given architecture artifacts and a change description, verifies completeness: all affected layers modified, patterns consistent, tests covering modified code paths
- **Parallel zone analyzer** (`scripts/parallel_zones.py`) — identifies independent subgraphs in dependency graphs for safe Task() agent assignment
- **Refresh orchestrator** (`scripts/refresh_architecture.sh`) — runs all analyzers and produces a combined `architecture_overview.json`
- **CLAUDE.md integration** — instructions for agents to consult `.architecture/` artifacts before planning or implementing

## Impact

- Affected specs: None (new capability)
- New spec: `codebase-analysis` — defines requirements for analysis, artifact format, cross-layer tracing, validation, and refresh workflow
- Affected code: New `scripts/` directory with analysis tools, new `.architecture/` output directory
- Affected skills: `plan-feature` and `implement-feature` should reference architecture artifacts (separate change)
- **BREAKING**: None — purely additive
