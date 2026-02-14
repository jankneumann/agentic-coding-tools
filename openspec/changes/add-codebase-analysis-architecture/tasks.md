## 1. Canonical Graph Schema

- [x] 1.1 Define JSON schema for `architecture.graph.json` with `nodes[]`, `edges[]`, `entrypoints[]`, `snapshots[]`
- [x] 1.2 Define stable node ID convention: `{prefix}:{qualified_name}` where prefix is `py` (Python), `ts` (TypeScript), `pg` (Postgres) — e.g., `py:backend.api.routes.get_user`, `ts:UserProfile`, `pg:public.users`
- [x] 1.3 Define edge types: `call`, `import`, `api_call`, `db_access`, `fk_reference`, `component_child`, `hook_usage`
- [x] 1.4 Define confidence levels (`high`, `medium`, `low`) and evidence string format
- [x] 1.5 Write schema validation script or JSON Schema definition
- [x] 1.6 Write unit tests for schema validation

## 2. Python Backend Analyzer

- [x] 2.1 Create `scripts/analyze_python.py` with AST-based extraction of functions, classes, imports, decorators, async markers, and docstrings
- [x] 2.2 Implement call graph extraction (function calls within function bodies, attribute chains)
- [x] 2.3 Implement post-processing to populate `called_by` reverse relationships
- [x] 2.4 Implement entry point detection via decorator patterns (FastAPI/Flask route decorators, CLI commands, event handlers)
- [x] 2.5 Implement ORM/SQL pattern detection: identify functions that access database tables (SQLAlchemy models, raw SQL strings, query builder patterns)
- [x] 2.6 Implement summary generation (hot functions, dead code candidates, async function count, entry points)
- [x] 2.7 Output intermediate `python_analysis.json` to `.architecture/`
- [x] 2.8 Add `--include` and `--exclude` glob pattern support for scoping analysis
- [x] 2.9 Write unit tests for the Python analyzer

## 3. TypeScript/React Frontend Analyzer

- [x] 3.1 Create `scripts/analyze_typescript.ts` using ts-morph for AST analysis
- [x] 3.2 Implement component extraction (function components, arrow function components, class components)
- [x] 3.3 Implement hook usage extraction (built-in and custom hooks per component)
- [x] 3.4 Implement JSX child component relationship extraction
- [x] 3.5 Implement API client call site detection: extract URLs from fetch, axios, typed API client methods, and GraphQL client calls
- [x] 3.6 Implement import graph construction (internal module dependencies)
- [x] 3.7 Implement summary generation (top components, top hooks, complex components, custom hooks list)
- [x] 3.8 Output intermediate `ts_analysis.json` to `.architecture/`
- [x] 3.9 Write unit tests for the TypeScript analyzer

## 4. TypeScript Architectural Guardrails

- [x] 4.1 Create `.dependency-cruiser.js` configuration with layer boundary rules (e.g., no components→pages, no UI→DB)
- [x] 4.2 Add circular dependency detection rules
- [x] 4.3 Add orphan module detection
- [x] 4.4 Optionally add Semgrep OSS rules for simple intra-procedural pattern checks
- [x] 4.5 Integrate dependency-cruiser output into the canonical graph as architectural violation edges

## 5. Database Schema Analyzer

- [x] 5.1 Create `scripts/analyze_postgres.py` with migration-file parser for CREATE TABLE, ALTER TABLE, CREATE INDEX, CREATE FUNCTION, CREATE TRIGGER statements
- [x] 5.2 Implement cumulative schema construction by parsing migrations in order
- [x] 5.3 Implement foreign key relationship extraction from DDL
- [x] 5.4 Build FK relationship graph with nodes (tables) and edges (foreign keys)
- [x] 5.5 Implement optional live-database mode using psycopg2 (activated by `--live` flag or PGHOST env var)
- [x] 5.6 Implement summary generation (table count, most-referenced tables, widest tables)
- [x] 5.7 Output intermediate `postgres_analysis.json` to `.architecture/`
- [x] 5.8 Write unit tests for the schema analyzer (including migration file parsing)

## 6. Graph Compiler (Normalize + Link)

- [x] 6.1 Create `scripts/compile_architecture_graph.py` that reads per-language intermediate outputs
- [x] 6.2 Implement node normalization: map every function/class/component/table to a stable `{prefix}:{qualified_name}` node ID (using `py`, `ts`, `pg` prefixes)
- [x] 6.3 Implement edge normalization: convert per-language call/import/FK edges into canonical edge format with type, confidence, evidence
- [x] 6.4 Implement Frontend→Backend cross-language linking: match TS API call URLs to Python route decorator paths (exact match = high, parameterized = medium, heuristic = low)
- [x] 6.5 Implement Backend→Database cross-language linking: match Python ORM model usage and SQL patterns to DB table names
- [x] 6.6 Implement Frontend→Database indirect flow inference: chain endpoint→service→query→table paths
- [x] 6.7 Populate `entrypoints[]` from detected routes, CLI commands, event handlers, jobs
- [x] 6.8 Include `snapshots[]` with `generated_at`, `git_sha`, and `tool_versions`
- [x] 6.9 Output `architecture.graph.json` (full canonical graph) and `architecture.summary.json` (compact, adaptive confidence threshold)
- [x] 6.10 Optionally emit `architecture.sqlite` for queryable storage
- [x] 6.11 Write unit tests for the compiler with mock per-language outputs

## 7. Flow Validator

- [x] 7.1 Create `scripts/validate_flows.py` that consumes `architecture.graph.json`
- [x] 7.2 Implement reachability check: for each entrypoint, verify at least one downstream service + DB/side-effect dependency exists (or explicit "pure" tag)
- [x] 7.3 Implement disconnected flow detection: backend routes with no frontend callers, frontend API calls with no backend handlers
- [x] 7.4 Implement test coverage alignment: verify modified/new functions have corresponding test files that reference them
- [x] 7.5 Implement orphan detection: new code unreachable from any entrypoint or test
- [x] 7.6 Implement pattern consistency check: compare decorator usage, naming conventions against codebase-wide norms
- [x] 7.7 Output `architecture.diagnostics.json` with findings categorized as `error`, `warning`, `info`
- [x] 7.8 Support change-scoped validation: accept file list, glob, or git diff to focus findings on changed code
- [x] 7.9 Write unit tests for the validator

## 8. View Generator

- [x] 8.1 Create `scripts/generate_views.py` that reads `architecture.graph.json`
- [x] 8.2 Implement container view (Mermaid): frontend, backend, DB, external services as boxes with connection arrows
- [x] 8.3 Implement component view for backend (Mermaid): packages/modules with dependency edges
- [x] 8.4 Implement component view for frontend (Mermaid): modules with import edges
- [x] 8.5 Implement DB ERD (Mermaid): tables with FK relationships
- [x] 8.6 Implement feature slice view: given a file list or path pattern, extract the subgraph and emit as JSON + Mermaid
- [x] 8.7 Output views to `.architecture/views/`
- [x] 8.8 Write unit tests for view generation

## 9. Parallel Zone Analyzer

- [x] 9.1 Create `scripts/parallel_zones.py` that loads canonical graph and computes independent subgraphs using NetworkX
- [x] 9.2 Implement leaf module identification (no dependents, safe to modify independently)
- [x] 9.3 Implement impact radius computation (transitive dependents of a given module)
- [x] 9.4 Output `parallel_zones.json` with independent groups, leaf modules, and high-impact modules
- [x] 9.5 Write unit tests for the parallel zone analyzer

## 10. CI Integration and Refresh Orchestrator

- [x] 10.1 Create `Makefile` targets: `architecture` (full generation), `architecture:diff` (baseline comparison), `architecture:feature FEATURE=...` (slice for PRs)
- [x] 10.2 Create `scripts/refresh_architecture.sh` that runs all analyzers → compiler → validator → view generator in sequence
- [x] 10.3 Implement baseline diff: compare current `architecture.graph.json` to a previous version and report new cycles, new high-impact modules, routes without tests, DB tables without migrations
- [x] 10.4 Add stale-artifact warning (compare `git_sha` in snapshot to current HEAD)
- [x] 10.5 Handle partial failure gracefully (if one analyzer fails, produce what's available with a note)
- [x] 10.6 Commit `.architecture/` artifacts to the repository with `.architecture/README.md` explaining artifact purpose and refresh workflow
- [x] 10.7 Add architecture context section to CLAUDE.md referencing `.architecture/` artifacts

## 11. Skill Workflow Integration

- [x] 11.1 Update `plan-feature` skill to consult `.architecture/architecture.summary.json` and cross-layer flows as planning context
- [x] 11.2 Update `implement-feature` skill to run `validate_flows.py` after implementation and before PR creation
- [x] 11.3 Update `validate-feature` skill to include architecture diagnostics in its validation report
- [x] 11.4 Add `make architecture` as a recommended pre-step in skill documentation

## 12. Dependencies and Configuration

- [x] 12.1 Add Python dependencies: `networkx>=3.0` (graph operations), `psycopg2-binary>=2.9.0` (optional live DB)
- [x] 12.2 Add Node dependencies: `ts-morph` (TypeScript AST), `dependency-cruiser` (architectural rules), `madge` (optional visualization)
- [x] 12.3 Optionally add Semgrep OSS for simple pattern guardrails
- [x] 12.4 Verify all scripts work without optional dependencies (graceful degradation when psycopg2, ts-morph, or dependency-cruiser unavailable)

## Acceptance Criteria

- A single `make architecture` command generates all artifacts deterministically
- At least 90% of routes are detected as entrypoints (configurable threshold)
- All DB tables from migration files appear in the schema graph
- "Flow broken" diagnostics catch missing route→service or service→query wiring
- All artifacts include `git_sha`, `generated_at`, `tool_versions`, and confidence/evidence fields
- `make architecture:diff` reports new cycles, new high-impact modules, and untested routes
