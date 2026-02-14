## Context

AI coding agents working on multi-layer codebases (Python + TypeScript + Postgres) lack structural context about how components relate across layers. The original proposal provides thorough tooling for per-language analysis but treats each layer as an independent silo. The primary user complaint—disconnected flows and inconsistent patterns—requires cross-layer understanding.

This design addresses: tool selection, cross-layer tracing strategy, artifact format for AI consumption, validation workflow, and integration with the existing Task()-based parallel execution model.

## Goals / Non-Goals

- Goals:
  - Generate machine-readable architecture artifacts consumable by Claude Code and other AI agents
  - Trace end-to-end flows across frontend, backend, and database layers
  - Validate implementation completeness after code changes
  - Identify safe parallel modification zones for Task() agents
  - Support both live Postgres connections and migration-file-based schema extraction
  - Keep external dependencies minimal; prefer stdlib AST analysis over third-party tools

- Non-Goals:
  - Runtime profiling or dynamic analysis (static analysis only)
  - Visualization/SVG/HTML output (machine-readable JSON is the primary target; visualization can be added later)
  - Replacing existing linters or type checkers (mypy, ruff, ESLint)
  - Real-time incremental analysis (batch refresh is sufficient for the initial version)
  - Supporting languages beyond Python and TypeScript

## Decisions

### Decision 1: Custom AST analysis over external call-graph tools

**Choice**: Use Python's `ast` stdlib and `ts-morph` for TypeScript as the primary analysis engines. Do not depend on PyCG, Pyan3, importlab, or Madge in the core workflow.

**Alternatives considered**:
- PyCG: Function-level call graphs but poor handling of dynamic dispatch, decorators, and metaclasses. Unmaintained since 2023.
- Pyan3: Visualization-focused, limited JSON output, unmaintained.
- Madge: Module-level only (no function/component-level detail). Useful as an optional supplement but not a primary tool.
- dependency-cruiser: Rule-enforcement focus, heavy configuration. Better suited for CI enforcement than AI context generation.

**Rationale**: Custom AST analysis gives full control over what metadata is extracted (decorators, async markers, docstrings, line numbers). External tools add fragile dependencies and produce output formats that require post-processing. The custom scripts from the original proposal are already well-structured; they just need cross-layer extensions.

**Optional supplements**: Madge and dependency-cruiser can be added as optional validation checks in CI, but the core analysis pipeline should not depend on them.

### Decision 2: Cross-layer flow tracing via convention-based matching

**Choice**: Trace flows by matching frontend API call patterns (fetch/axios URLs) to backend route decorators (@app.get("/path")) to database access patterns (ORM model usage, raw SQL) within those handlers.

**Alternatives considered**:
- OpenTelemetry traces: Requires instrumented running application, heavy infrastructure.
- Manual annotation: Requires developers to maintain flow maps.
- Type-system-based tracing: TypeScript's type system doesn't extend to Python; no shared type contracts.

**Rationale**: Convention-based matching works without runtime instrumentation. Most full-stack apps follow predictable patterns: frontend calls an API URL, backend registers that URL as a route, the route handler calls service functions that access the database. Static analysis can follow these conventions with reasonable accuracy. False positives are acceptable since the output is advisory context for AI agents, not enforcement.

### Decision 3: Migration-file-based schema extraction as primary, live DB as optional

**Choice**: Extract Postgres schema from SQL migration files (e.g., `supabase/migrations/*.sql`) by default. Support live `psycopg2` connection as an optional enhancement.

**Alternatives considered**:
- Live DB only: Requires running database, which may not be available in all environments (CI, fresh clones, Claude Code web sessions).
- ORM model introspection: Ties analysis to specific ORM (SQLAlchemy, Prisma). Not all projects use ORMs.

**Rationale**: Migration files are always available in the repository. They represent the intended schema (not a potentially-drifted live instance). The `agent-coordinator/supabase/migrations/` directory already contains 11 migration files that demonstrate this approach works for this project. Live DB analysis adds value for query pattern extraction but should be optional.

### Decision 4: JSON artifacts designed for token-efficient AI consumption

**Choice**: Produce two tiers of output per analyzer: a `*_summary.json` (compact, <2KB, suitable for CLAUDE.md reference) and a `*_analysis.json` (full detail, queried on demand).

**Alternatives considered**:
- Single comprehensive output: Too large for routine context loading (>100KB for medium codebases).
- Markdown output: Human-readable but harder to query programmatically.
- SQLite database: Powerful querying but adds dependency and isn't natively readable by AI agents.

**Rationale**: AI agents should load summaries by default and drill into full analysis only when investigating specific areas. This mirrors how the existing `openspec show` command provides summary vs. `--json` detail levels. The summary includes entry points, hot functions, component hierarchy overview, and table relationships—enough to make informed planning decisions without consuming excessive context tokens.

### Decision 5: Validation as a separate script consuming analysis artifacts

**Choice**: `validate_implementation.py` takes architecture artifacts + a change description (file list or spec reference) and reports completeness findings.

**Alternatives considered**:
- Integrated into analysis scripts: Mixes concerns (analysis vs. validation).
- Claude Code skill: Would limit to Claude Code only; should be usable by any agent or CI.
- Pre-commit hook: Too slow for per-commit validation; better as a manual or CI step.

**Rationale**: Separation of concerns: analyzers produce artifacts, validator consumes them. The validator can check: (1) all layers affected by a change are modified, (2) new API endpoints have corresponding frontend calls, (3) new DB tables have corresponding model/query code, (4) modified functions have test coverage. This is the key artifact that addresses the user's stated problem of insufficient end-to-end validation.

### Decision 6: NetworkX for graph operations, not custom graph code

**Choice**: Use `networkx` for dependency graph analysis (connected components, ancestors/descendants, cycle detection).

**Alternatives considered**:
- Custom graph traversal: More code to maintain, likely buggier.
- igraph: Faster for large graphs but heavier dependency.

**Rationale**: NetworkX is the standard Python graph library. The graph sizes involved (hundreds to low thousands of nodes) are well within its performance range. It provides tested implementations of all needed algorithms (weakly connected components, BFS/DFS, transitive closure).

## Risks / Trade-offs

- **False positives in cross-layer tracing** — Convention-based matching will produce false matches (e.g., a frontend URL string that happens to match a backend route but isn't actually called). Mitigation: Mark confidence levels on traced flows; provide the raw match data so agents can verify.

- **Stale artifacts** — Analysis artifacts can drift from code. Mitigation: Include a `generated_at` timestamp and a `source_commit` hash in every artifact. The refresh script should warn if artifacts are >N commits behind HEAD.

- **Migration file parsing limitations** — SQL migration files may use complex PL/pgSQL, dynamic DDL, or vendor-specific syntax that a simple parser can't handle. Mitigation: Start with CREATE TABLE/ALTER TABLE/CREATE INDEX parsing; skip unparseable statements with warnings.

- **Large codebase performance** — AST analysis of thousands of files could be slow. Mitigation: Support `--include` and `--exclude` glob patterns to scope analysis. Parallelize file parsing within each analyzer.

- **ts-morph initialization overhead** — Loading a full TypeScript project via ts-morph can be slow (10-30s for large projects). Mitigation: Support a lightweight regex-based mode for quick summaries, with ts-morph as the thorough mode.

## Open Questions

- Should `.architecture/` artifacts be committed to the repo (providing consistent context across clones) or gitignored (avoiding churn from regeneration)?
- Should the `validate_implementation.py` output be integrated into the `openspec validate` workflow, or remain a standalone tool?
- What confidence threshold should cross-layer flow traces have before being included in summaries?
