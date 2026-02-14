## ADDED Requirements

### Requirement: Python Call Graph Analysis

The system SHALL analyze Python source files using the `ast` standard library to extract function-level call graphs, class hierarchies, import graphs, and metadata (decorators, async markers, line numbers, docstrings).

- The analyzer SHALL produce a `python_analysis.json` containing all functions, classes, modules, and an import graph
- The analyzer SHALL produce a `python_summary.json` containing entry points (decorator-detected API routes), hot functions (most called-by), dead code candidates (unreferenced non-decorated functions), and async function counts
- The analyzer SHALL populate bidirectional relationships: each function's `calls` list and `called_by` list
- The analyzer SHALL support `--include` and `--exclude` glob patterns to scope analysis to specific directories or files
- The analyzer SHALL skip `__pycache__` directories and handle `SyntaxError` gracefully with warnings

#### Scenario: Analyze a FastAPI backend
- **WHEN** the analyzer is run against a directory containing Python files with `@router.get`, `@app.post` and similar decorators
- **THEN** `python_summary.json` SHALL list those decorated functions as entry points with their file paths and line numbers
- **AND** `python_analysis.json` SHALL contain call chains from those entry points through service and data access functions

#### Scenario: Detect dead code candidates
- **WHEN** the analyzer finds functions that have no `called_by` references and no route/handler decorators
- **THEN** `python_summary.json` SHALL list them under `potentially_dead_code`

#### Scenario: Handle syntax errors gracefully
- **WHEN** a Python file contains a syntax error
- **THEN** the analyzer SHALL log a warning and continue processing remaining files
- **AND** the output SHALL not include partial results from the failed file

### Requirement: TypeScript Component and Dependency Analysis

The system SHALL analyze TypeScript and React source files using ts-morph to extract component hierarchies, hook usage, import graphs, and function metadata.

- The analyzer SHALL produce a `ts_analysis.json` containing all functions, components, modules, import graph, and custom hooks
- The analyzer SHALL produce a `ts_summary.json` containing top components by usage, top hooks by usage, complex components (by hook + child count), and custom hook inventory
- The analyzer SHALL identify React components by PascalCase naming convention and custom hooks by `use` prefix convention
- The analyzer SHALL extract JSX child component references from component render output
- The analyzer SHALL skip `node_modules`, `.test.`, and `.spec.` files

#### Scenario: Analyze a React frontend
- **WHEN** the analyzer is run against a TypeScript React project with a valid `tsconfig.json`
- **THEN** `ts_analysis.json` SHALL contain component entries with their hooks, child components, props, and export status
- **AND** `ts_summary.json` SHALL rank components by usage frequency and complexity

#### Scenario: Extract custom hook dependencies
- **WHEN** a component uses custom hooks (functions matching `use[A-Z]` pattern)
- **THEN** the component's `hooks` array SHALL include those custom hook names
- **AND** `ts_summary.json` SHALL include those hooks in `topHooks` ranked by usage count

#### Scenario: Build import graph for internal modules
- **WHEN** modules import from relative paths (starting with `.`)
- **THEN** `ts_analysis.json` SHALL include those relationships in `importGraph`
- **AND** external package imports SHALL be recorded in module metadata but excluded from the internal import graph

### Requirement: Database Schema Analysis

The system SHALL extract Postgres schema information from SQL migration files as the primary source, with optional live database connection as a secondary source.

- The analyzer SHALL parse `CREATE TABLE`, `ALTER TABLE ADD COLUMN`, `ALTER TABLE ADD CONSTRAINT`, and `CREATE INDEX` statements from migration files
- The analyzer SHALL extract foreign key relationships to build a table relationship graph
- The analyzer SHALL extract stored functions and triggers from `CREATE FUNCTION` and `CREATE TRIGGER` statements
- The analyzer SHALL produce `postgres_tables.json` (full schema), `postgres_relationships.json` (FK graph), and `postgres_summary.json`
- When the `--live` flag is provided or `PGHOST` environment variable is set, the analyzer SHALL connect to the database for authoritative schema extraction and optionally extract query patterns from `pg_stat_statements`

#### Scenario: Extract schema from migration files
- **WHEN** the analyzer is pointed at a directory containing numbered SQL migration files
- **THEN** it SHALL parse them in order and produce a cumulative schema representation
- **AND** `postgres_relationships.json` SHALL contain nodes (tables) and edges (foreign key relationships)

#### Scenario: Handle unparseable SQL gracefully
- **WHEN** a migration file contains PL/pgSQL or vendor-specific syntax that the parser cannot handle
- **THEN** the analyzer SHALL log a warning for the skipped statement
- **AND** continue processing subsequent statements in the same file and remaining files

#### Scenario: Live database extraction
- **WHEN** `--live` flag is provided and database connection succeeds
- **THEN** the analyzer SHALL extract schema from `information_schema` and `pg_catalog`
- **AND** the output SHALL include `row_count_estimate` from `pg_class.reltuples`

#### Scenario: No database connection available
- **WHEN** `--live` flag is not provided and `PGHOST` is not set
- **THEN** the analyzer SHALL use migration-file parsing only
- **AND** SHALL NOT attempt any database connection

### Requirement: Cross-Layer Flow Tracing

The system SHALL trace end-to-end flows across frontend, backend, and database layers by matching API call patterns in TypeScript to route handlers in Python to database operations in those handlers.

- The tracer SHALL consume analysis artifacts from the Python, TypeScript, and Postgres analyzers
- The tracer SHALL match frontend API calls (fetch URLs, axios calls, typed API client methods) to backend route decorator paths
- The tracer SHALL follow call chains from matched route handlers through service functions to identify database table access
- Each traced flow SHALL include: `frontend_component`, `api_url`, `http_method`, `backend_handler`, `service_functions`, `db_tables`, `db_operations`, and `confidence` score
- Confidence levels SHALL be: `high` (exact URL path match), `medium` (parameterized path match), `low` (heuristic/pattern match)

#### Scenario: Trace a CRUD operation end-to-end
- **WHEN** a TypeScript component calls `fetch("/api/users")` and a Python handler is decorated with `@router.get("/api/users")` and that handler calls a function that queries the `users` table
- **THEN** the tracer SHALL produce a flow record connecting the component to the handler to the table
- **AND** the confidence SHALL be `high` (exact URL match)

#### Scenario: Detect disconnected flows
- **WHEN** a backend route handler exists but no frontend component calls its URL
- **THEN** the tracer SHALL report it as an unmatched backend endpoint
- **AND** include it in the flow summary under `disconnected_endpoints`

#### Scenario: Detect frontend calls without backend handlers
- **WHEN** a frontend component makes an API call to a URL that matches no backend route
- **THEN** the tracer SHALL report it as an unmatched frontend call
- **AND** include it in the flow summary under `disconnected_frontend_calls`

### Requirement: Implementation Completeness Validation

The system SHALL validate that code changes are complete and consistent across all layers by consuming architecture artifacts and a change scope.

- The validator SHALL accept a change scope as a file list, glob pattern, or git diff
- The validator SHALL check layer completeness: if a backend route is added or modified, verify corresponding frontend integration and database access exist in the cross-layer flow map
- The validator SHALL check pattern consistency: compare decorator usage, naming conventions, and structural patterns in modified code against codebase-wide norms from the analysis artifacts
- The validator SHALL check test coverage: verify that modified or added functions/components have corresponding test files
- The validator SHALL detect orphaned code: new functions or components that are unreachable from any entry point or test
- The validator SHALL output a JSON report with findings categorized as `error` (likely incomplete), `warning` (potential issue), or `info` (observation)

#### Scenario: Detect missing frontend integration
- **WHEN** a new backend API endpoint is added but no frontend component calls it
- **THEN** the validator SHALL report a `warning` finding: "New endpoint /api/foo has no frontend caller"

#### Scenario: Detect missing test coverage
- **WHEN** a function is modified and no test file imports or references that function
- **THEN** the validator SHALL report a `warning` finding indicating the function lacks test coverage

#### Scenario: Detect orphaned code
- **WHEN** a new function is added that is not called by any other function, not decorated as an entry point, and not referenced by any test
- **THEN** the validator SHALL report an `info` finding: "Function bar appears unreachable"

#### Scenario: Validate a complete change
- **WHEN** a change adds a backend endpoint, a frontend component that calls it, database access for the relevant table, and a test for the handler
- **THEN** the validator SHALL report no `error` findings for that change scope

### Requirement: Parallel Modification Zone Analysis

The system SHALL identify independent subgraphs in dependency graphs to determine which modules can be safely modified in parallel by separate Task() agents.

- The analyzer SHALL compute weakly connected components in the import/dependency graph
- The analyzer SHALL identify leaf modules (no dependents) as unconditionally safe for parallel modification
- The analyzer SHALL compute impact radius for any given module (transitive set of dependents)
- The analyzer SHALL identify high-impact modules (many transitive dependents) that require single-agent ownership
- The output SHALL include `parallel_zones.json` with independent groups, leaf modules, and high-impact modules for both Python and TypeScript

#### Scenario: Identify independent module groups
- **WHEN** the dependency graph contains two weakly connected components (e.g., `auth/*` and `billing/*` with no shared imports)
- **THEN** `parallel_zones.json` SHALL list them as separate independent groups
- **AND** each group MAY be assigned to a different Task() agent without conflict risk

#### Scenario: Compute impact radius
- **WHEN** an agent requests the impact radius for module `services/user_service.py`
- **THEN** the analyzer SHALL return the set of all modules that transitively depend on `user_service.py`

#### Scenario: Flag high-impact modules
- **WHEN** a module has more than 10 transitive dependents
- **THEN** it SHALL appear in `high_impact_modules` with its dependent count

### Requirement: Architecture Artifact Refresh

The system SHALL provide a refresh orchestrator that runs all analyzers and produces a combined `architecture_overview.json` with metadata.

- The refresh script SHALL run Python, TypeScript, and Postgres analyzers in sequence (or in parallel where independent)
- Every generated artifact SHALL include a `generated_at` ISO 8601 timestamp and a `source_commit` git hash
- The refresh script SHALL produce an `architecture_overview.json` that aggregates summaries from all analyzers
- The system SHALL warn when artifacts are stale (source_commit differs from current HEAD by more than a configurable threshold)
- All artifacts SHALL be written to the `.architecture/` directory

#### Scenario: Full refresh
- **WHEN** `scripts/refresh_architecture.sh` is run with no arguments
- **THEN** all analyzers SHALL execute and produce their respective output files in `.architecture/`
- **AND** `architecture_overview.json` SHALL contain the combined summaries plus `generated_at` and `source_commit`

#### Scenario: Stale artifact detection
- **WHEN** an agent reads an architecture artifact whose `source_commit` is more than 20 commits behind HEAD
- **THEN** the artifact metadata SHALL allow detection of this staleness
- **AND** the refresh script, when run, SHALL log a warning about stale artifacts before regenerating

#### Scenario: Partial refresh on analyzer failure
- **WHEN** the TypeScript analyzer fails (e.g., missing tsconfig.json) but Python and Postgres analyzers succeed
- **THEN** the refresh script SHALL log the TypeScript failure
- **AND** produce `architecture_overview.json` with available summaries and a note about the missing TypeScript analysis
