## 1. Python Backend Analyzer

- [ ] 1.1 Create `scripts/analyze_python.py` with AST-based extraction of functions, classes, imports, decorators, async markers, and docstrings
- [ ] 1.2 Implement call graph extraction (function calls within function bodies, attribute chains)
- [ ] 1.3 Implement post-processing to populate `called_by` reverse relationships
- [ ] 1.4 Implement entry point detection via decorator patterns (FastAPI/Flask route decorators)
- [ ] 1.5 Implement summary generation (hot functions, dead code candidates, async function count, entry points)
- [ ] 1.6 Output `python_analysis.json` and `python_summary.json` to `.architecture/`
- [ ] 1.7 Add `--include` and `--exclude` glob pattern support for scoping analysis
- [ ] 1.8 Write unit tests for the Python analyzer

## 2. TypeScript/React Frontend Analyzer

- [ ] 2.1 Create `scripts/analyze_typescript.ts` using ts-morph for AST analysis
- [ ] 2.2 Implement component extraction (function components, arrow function components, class components)
- [ ] 2.3 Implement hook usage extraction (built-in and custom hooks per component)
- [ ] 2.4 Implement JSX child component relationship extraction
- [ ] 2.5 Implement import graph construction (internal module dependencies)
- [ ] 2.6 Implement summary generation (top components, top hooks, complex components, custom hooks list)
- [ ] 2.7 Output `ts_analysis.json` and `ts_summary.json` to `.architecture/`
- [ ] 2.8 Write unit tests for the TypeScript analyzer

## 3. Database Schema Analyzer

- [ ] 3.1 Create `scripts/analyze_postgres.py` with migration-file parser for CREATE TABLE, ALTER TABLE, CREATE INDEX statements
- [ ] 3.2 Implement foreign key relationship extraction from migration DDL
- [ ] 3.3 Implement stored function/trigger extraction from migration files
- [ ] 3.4 Implement optional live-database mode using psycopg2 (activated by `--live` flag or PGHOST env var)
- [ ] 3.5 Build FK relationship graph with nodes (tables) and edges (foreign keys)
- [ ] 3.6 Implement summary generation (largest tables, most-referenced tables, widest tables)
- [ ] 3.7 Output `postgres_tables.json`, `postgres_relationships.json`, and `postgres_summary.json` to `.architecture/`
- [ ] 3.8 Write unit tests for the schema analyzer (including migration file parsing)

## 4. Cross-Layer Flow Tracer

- [ ] 4.1 Create `scripts/trace_flows.py` that consumes analysis artifacts from steps 1-3
- [ ] 4.2 Implement frontend-to-backend matching: extract API call URLs from TypeScript (fetch, axios, custom API client patterns) and match to Python route decorators
- [ ] 4.3 Implement backend-to-database matching: trace from route handlers through service functions to ORM model usage or raw SQL queries
- [ ] 4.4 Produce end-to-end flow records: `{frontend_component, api_url, backend_handler, service_functions, db_tables, db_operations}`
- [ ] 4.5 Assign confidence scores to matches (exact URL match = high, pattern match = medium, heuristic = low)
- [ ] 4.6 Output `cross_layer_flows.json` and include flow summary in `architecture_overview.json`
- [ ] 4.7 Write unit tests for the flow tracer with mock analysis artifacts

## 5. Implementation Validator

- [ ] 5.1 Create `scripts/validate_implementation.py` that consumes architecture artifacts and a change scope (file list or glob)
- [ ] 5.2 Implement layer completeness check: if backend route is added/modified, verify corresponding frontend call and DB access exist
- [ ] 5.3 Implement pattern consistency check: compare decorator usage, naming conventions, and error handling patterns against codebase norms
- [ ] 5.4 Implement test coverage check: verify modified functions/components have corresponding test files
- [ ] 5.5 Implement orphan detection: find new code that isn't reachable from any entry point or test
- [ ] 5.6 Output validation report as JSON with findings categorized by severity (error, warning, info)
- [ ] 5.7 Write unit tests for the validator

## 6. Parallel Zone Analyzer

- [ ] 6.1 Create `scripts/parallel_zones.py` that loads dependency graphs and computes independent subgraphs using NetworkX
- [ ] 6.2 Implement leaf module identification (no dependents, safe to modify independently)
- [ ] 6.3 Implement impact radius computation (transitive dependents of a given module)
- [ ] 6.4 Output `parallel_zones.json` with independent groups, leaf modules, and high-impact modules
- [ ] 6.5 Write unit tests for the parallel zone analyzer

## 7. Refresh Orchestrator and Integration

- [ ] 7.1 Create `scripts/refresh_architecture.sh` that runs all analyzers and produces `architecture_overview.json`
- [ ] 7.2 Include `generated_at` timestamp and `source_commit` hash in all artifacts
- [ ] 7.3 Add stale-artifact warning (compare source_commit to current HEAD)
- [ ] 7.4 Add architecture context section to CLAUDE.md referencing `.architecture/` artifacts
- [ ] 7.5 Add `.architecture/` to `.gitignore` (artifacts are regenerated, not committed)
- [ ] 7.6 Document refresh workflow in a `scripts/README.md`

## 8. Dependencies and Configuration

- [ ] 8.1 Add Python dependencies: `networkx>=3.0` (graph operations), `psycopg2-binary>=2.9.0` (optional live DB)
- [ ] 8.2 Add Node dependencies: `ts-morph` (TypeScript AST analysis)
- [ ] 8.3 Verify all scripts work without optional dependencies (graceful degradation when psycopg2 or ts-morph unavailable)
