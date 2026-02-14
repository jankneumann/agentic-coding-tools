## ADDED Requirements

### Requirement: Canonical Architecture Graph Schema

The system SHALL define a single normalized JSON schema for architecture artifacts that all per-language analyzers feed into. The canonical graph SHALL be the single source of truth for architectural relationships across all languages and layers.

- The schema SHALL include four top-level objects: `nodes[]`, `edges[]`, `entrypoints[]`, and `snapshots[]`
- Each node SHALL have: `id` (stable, format `{language}:{qualified_name}`), `kind` (function, class, component, hook, table, module), `language` (python, typescript, sql), `name`, `file`, `span` (start/end line numbers), `tags[]`, and `signatures` (language-specific metadata)
- Each edge SHALL have: `from` (node ID), `to` (node ID), `type` (call, import, api_call, db_access, fk_reference, component_child, hook_usage), `confidence` (high, medium, low), and `evidence` (string describing how the edge was detected)
- Each entrypoint SHALL have: `node_id`, `kind` (route, cli, job, event_handler, migration), `method` (HTTP method if applicable), and `path` (URL path if applicable)
- Each snapshot SHALL have: `generated_at` (ISO 8601), `git_sha`, and `tool_versions` (map of tool name to version string)
- The system SHALL provide a schema validation script that verifies any `architecture.graph.json` conforms to the schema

#### Scenario: Validate a well-formed graph
- **WHEN** `architecture.graph.json` contains valid nodes, edges, entrypoints, and snapshots conforming to the schema
- **THEN** the schema validator SHALL report success with no errors

#### Scenario: Reject a graph with missing confidence on edges
- **WHEN** an edge in `architecture.graph.json` lacks a `confidence` or `evidence` field
- **THEN** the schema validator SHALL report a validation error identifying the malformed edge

#### Scenario: Stable node IDs across runs
- **WHEN** the same codebase is analyzed twice without changes
- **THEN** the node IDs in both runs SHALL be identical

### Requirement: Python Call Graph Analysis

The system SHALL analyze Python source files using the `ast` standard library to extract function-level call graphs, class hierarchies, import graphs, decorator-based entry points, and database access patterns.

- The analyzer SHALL produce a `python_analysis.json` intermediate output containing all functions, classes, modules, import graph, and database access patterns
- The analyzer SHALL populate bidirectional relationships: each function's `calls` list and `called_by` list
- The analyzer SHALL detect entry points via decorator patterns (FastAPI/Flask route decorators, CLI commands, event handlers)
- The analyzer SHALL detect database access patterns: SQLAlchemy model usage, raw SQL strings, query builder calls
- The analyzer SHALL support `--include` and `--exclude` glob patterns to scope analysis
- The analyzer SHALL skip `__pycache__` directories and handle `SyntaxError` gracefully with warnings

#### Scenario: Analyze a FastAPI backend
- **WHEN** the analyzer is run against a directory containing Python files with `@router.get`, `@app.post` and similar decorators
- **THEN** `python_analysis.json` SHALL list those decorated functions as entry points with their file paths and line numbers
- **AND** SHALL contain call chains from those entry points through service and data access functions

#### Scenario: Detect database access patterns
- **WHEN** a Python function contains SQLAlchemy model queries, raw SQL strings, or query builder calls
- **THEN** `python_analysis.json` SHALL record the accessed table names in that function's metadata

#### Scenario: Detect dead code candidates
- **WHEN** the analyzer finds functions that have no `called_by` references and no route/handler decorators
- **THEN** the intermediate output SHALL flag them as potentially dead code

#### Scenario: Handle syntax errors gracefully
- **WHEN** a Python file contains a syntax error
- **THEN** the analyzer SHALL log a warning and continue processing remaining files
- **AND** the output SHALL not include partial results from the failed file

### Requirement: TypeScript Component and Dependency Analysis

The system SHALL analyze TypeScript and React source files using ts-morph to extract component hierarchies, hook usage, import graphs, API client call sites, and function metadata.

- The analyzer SHALL produce a `ts_analysis.json` intermediate output containing all functions, components, modules, import graph, custom hooks, and API call sites
- The analyzer SHALL identify React components by PascalCase naming convention and custom hooks by `use` prefix convention
- The analyzer SHALL extract JSX child component references from component render output
- The analyzer SHALL detect API client call sites: URLs from fetch, axios, typed API client methods, and GraphQL client calls
- The analyzer SHALL skip `node_modules`, `.test.`, and `.spec.` files

#### Scenario: Analyze a React frontend
- **WHEN** the analyzer is run against a TypeScript React project with a valid `tsconfig.json`
- **THEN** `ts_analysis.json` SHALL contain component entries with their hooks, child components, props, export status, and API call sites

#### Scenario: Extract API call sites
- **WHEN** a component or hook calls `fetch("/api/users")` or `axios.get("/api/users")` or a typed API client method
- **THEN** `ts_analysis.json` SHALL record the URL pattern and HTTP method (if determinable) in that component's API call sites

#### Scenario: Build import graph for internal modules
- **WHEN** modules import from relative paths (starting with `.`)
- **THEN** `ts_analysis.json` SHALL include those relationships in the import graph
- **AND** external package imports SHALL be recorded in module metadata but excluded from the internal import graph

### Requirement: TypeScript Architectural Guardrails

The system SHALL enforce architectural rules in TypeScript codebases using dependency-cruiser and optionally Semgrep OSS.

- The system SHALL provide a dependency-cruiser configuration with rules for: layer boundary enforcement (e.g., no components importing from pages), circular dependency detection, and orphan module detection
- Dependency-cruiser rule violations SHALL be reported as architectural violation edges in the canonical graph
- Semgrep OSS MAY be used for simple intra-procedural pattern rules (e.g., "services must not import from API layer")

#### Scenario: Detect circular dependencies
- **WHEN** dependency-cruiser finds circular import chains in the TypeScript codebase
- **THEN** the system SHALL report them as `warning` findings in `architecture.diagnostics.json`
- **AND** include them as edges of type `circular_dependency` in the canonical graph

#### Scenario: Enforce layer boundaries
- **WHEN** a TypeScript module in `src/components/` imports from `src/pages/`
- **THEN** the system SHALL report a `warning` finding: "Layer boundary violation: component imports from pages"

### Requirement: Database Schema Analysis

The system SHALL extract Postgres schema information from SQL migration files as the primary source, with optional live database connection as a secondary source.

- The analyzer SHALL parse `CREATE TABLE`, `ALTER TABLE ADD COLUMN`, `ALTER TABLE ADD CONSTRAINT`, `CREATE INDEX`, `CREATE FUNCTION`, and `CREATE TRIGGER` statements from migration files
- The analyzer SHALL construct a cumulative schema by parsing migrations in order
- The analyzer SHALL extract foreign key relationships to build a table relationship graph
- The analyzer SHALL produce `postgres_analysis.json` intermediate output with full table definitions, FK graph, and stored functions
- When the `--live` flag is provided or `PGHOST` environment variable is set, the analyzer SHALL connect to the database for authoritative schema extraction

#### Scenario: Extract schema from migration files
- **WHEN** the analyzer is pointed at a directory containing numbered SQL migration files
- **THEN** it SHALL parse them in order and produce a cumulative schema representation
- **AND** the output SHALL contain nodes for each table and edges for each foreign key

#### Scenario: Handle unparseable SQL gracefully
- **WHEN** a migration file contains PL/pgSQL or vendor-specific syntax that the parser cannot handle
- **THEN** the analyzer SHALL log a warning for the skipped statement
- **AND** continue processing subsequent statements and remaining files

#### Scenario: Live database extraction
- **WHEN** `--live` flag is provided and database connection succeeds
- **THEN** the analyzer SHALL extract schema from `information_schema` and `pg_catalog`
- **AND** the output SHALL include `row_count_estimate` from `pg_class.reltuples`

#### Scenario: No database connection available
- **WHEN** `--live` flag is not provided and `PGHOST` is not set
- **THEN** the analyzer SHALL use migration-file parsing only
- **AND** SHALL NOT attempt any database connection

### Requirement: Cross-Language Graph Compilation

The system SHALL compile per-language intermediate outputs into a single canonical `architecture.graph.json` by normalizing nodes/edges and performing cross-language linking.

- The compiler SHALL read `python_analysis.json`, `ts_analysis.json`, and `postgres_analysis.json` intermediate outputs
- The compiler SHALL normalize all symbols into stable node IDs using the `{language}:{qualified_name}` convention
- The compiler SHALL perform Frontend→Backend linking: match TypeScript API call URLs to Python route decorator paths
- The compiler SHALL perform Backend→Database linking: match Python database access patterns to Postgres table names
- The compiler SHALL infer Frontend→Database indirect flows by chaining endpoint→service→query→table paths
- Every cross-language edge SHALL include confidence (high = exact URL match, medium = parameterized path match, low = heuristic) and evidence (description of how the link was detected)
- The compiler SHALL produce `architecture.graph.json` (full graph) and `architecture.summary.json` (compact, using adaptive confidence threshold for flow inclusion)

#### Scenario: Link a frontend component to a backend route
- **WHEN** a TypeScript component calls `fetch("/api/users")` and a Python handler is decorated with `@router.get("/api/users")`
- **THEN** `architecture.graph.json` SHALL contain an edge of type `api_call` from the component node to the handler node
- **AND** the edge confidence SHALL be `high` with evidence `"string_match:/api/users"`

#### Scenario: Link a backend handler to a database table
- **WHEN** a Python route handler calls a service function that queries `User.query.filter_by(...)` or executes `SELECT * FROM users`
- **THEN** `architecture.graph.json` SHALL contain an edge of type `db_access` from the handler (or service function) node to the `pg:public.users` table node

#### Scenario: Infer end-to-end flow
- **WHEN** a frontend component calls an API URL that matches a backend route, and that route's call chain reaches a database table
- **THEN** `architecture.summary.json` SHALL include the complete flow: `{frontend_component, api_url, backend_handler, service_functions, db_tables}`

#### Scenario: Adaptive summary threshold
- **WHEN** the canonical graph contains 200 cross-language flow traces (50 high, 80 medium, 70 low confidence)
- **THEN** `architecture.summary.json` SHALL include all 50 high-confidence traces
- **AND** SHALL include medium-confidence traces until reaching the configured limit (default 50 total entries)
- **AND** full details for all 200 traces SHALL remain available in `architecture.graph.json`

#### Scenario: Report disconnected endpoints
- **WHEN** a backend route handler exists but no frontend component calls its URL
- **THEN** the compiler SHALL flag it in `architecture.summary.json` under `disconnected_endpoints`

#### Scenario: Report disconnected frontend calls
- **WHEN** a frontend component makes an API call to a URL that matches no backend route
- **THEN** the compiler SHALL flag it in `architecture.summary.json` under `disconnected_frontend_calls`

### Requirement: Flow Validation and Diagnostics

The system SHALL validate flow connectivity and test coverage alignment by consuming the canonical graph, and produce actionable diagnostics.

- The validator SHALL check reachability: for each entrypoint, verify at least one downstream service + DB/side-effect dependency exists, or the entrypoint is explicitly tagged as "pure"
- The validator SHALL check test coverage alignment: for each critical flow (configurable list), verify at least one test is mapped to the flow's key edges
- The validator SHALL detect orphaned code: new functions or components unreachable from any entrypoint or test
- The validator SHALL check pattern consistency: compare decorator usage, naming conventions, and structural patterns in modified code against codebase-wide norms
- The validator SHALL support change-scoped validation: accept a file list, glob pattern, or git diff to focus findings on changed code
- The validator SHALL output `architecture.diagnostics.json` with findings categorized as `error` (likely broken), `warning` (potential issue), or `info` (observation)

#### Scenario: Detect broken flow — missing service layer
- **WHEN** a new backend route handler directly accesses the database without going through a service layer, violating the codebase's established pattern
- **THEN** the validator SHALL report a `warning` finding about pattern inconsistency

#### Scenario: Detect missing test coverage for critical flow
- **WHEN** an entrypoint's downstream flow (route→service→DB) has no test that references any function in the chain
- **THEN** the validator SHALL report a `warning` finding: "Flow from endpoint /api/foo has no test coverage"

#### Scenario: Detect orphaned code
- **WHEN** a new function is added that is not called by any other function, not decorated as an entrypoint, and not referenced by any test
- **THEN** the validator SHALL report an `info` finding: "Function bar appears unreachable"

#### Scenario: Validate a complete change
- **WHEN** a change adds a backend endpoint, a frontend component that calls it, database access for the relevant table, and a test for the handler
- **THEN** the validator SHALL report no `error` findings for that change scope

#### Scenario: Change-scoped validation
- **WHEN** the validator is run with a git diff specifying 3 modified files
- **THEN** findings SHALL be limited to flows and nodes affected by those files
- **AND** unrelated parts of the codebase SHALL not generate findings

### Requirement: Architecture View Generation

The system SHALL auto-generate visual diagrams from the canonical graph at multiple zoom levels using Mermaid format.

- The system SHALL generate a container view showing frontend, backend, database, and external services as high-level boxes with connection arrows
- The system SHALL generate a backend component view showing packages/modules with dependency edges
- The system SHALL generate a frontend component view showing modules with import edges
- The system SHALL generate a database ERD showing tables with FK relationships
- The system SHALL support feature slice views: given a file list or path pattern, extract the relevant subgraph and emit as both JSON and Mermaid
- All views SHALL be written to `.architecture/views/`

#### Scenario: Generate container view
- **WHEN** the view generator is run on a canonical graph containing frontend, backend, and database nodes
- **THEN** `.architecture/views/containers.mmd` SHALL contain a Mermaid diagram with boxes for each container and arrows for cross-container edges

#### Scenario: Generate feature slice view
- **WHEN** the view generator is given a file list from a PR (e.g., `backend/api/users.py`, `src/components/UserProfile.tsx`)
- **THEN** it SHALL extract only the nodes and edges touched by those files
- **AND** emit both `.architecture/views/feature_users.json` (subgraph) and `.architecture/views/feature_users.mmd` (Mermaid diagram)

#### Scenario: Generate DB ERD
- **WHEN** the canonical graph contains table nodes with FK edges
- **THEN** `.architecture/views/db_erd.mmd` SHALL contain a Mermaid entity-relationship diagram showing tables and their relationships

### Requirement: Parallel Modification Zone Analysis

The system SHALL identify independent subgraphs in the canonical graph to determine which modules can be safely modified in parallel by separate Task() agents.

- The analyzer SHALL compute weakly connected components in the import/dependency subgraph
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

### Requirement: CI Integration and Baseline Diffing

The system SHALL provide CI-friendly commands for artifact generation, baseline comparison, and diagnostic gating.

- The system SHALL provide `make architecture` to generate all artifacts deterministically from a single command
- The system SHALL provide `make architecture:diff BASE_SHA=...` to compare the current graph to a baseline and report changes
- The diff report SHALL include: new dependency cycles introduced, new high-impact modules, routes added without tests, DB tables touched without corresponding migrations
- The system SHALL provide `make architecture:feature FEATURE=...` to extract a feature-scoped subgraph for PR review
- Every generated artifact SHALL include `generated_at`, `git_sha`, and `tool_versions` in a snapshot object
- The system SHALL warn when artifacts are stale (snapshot `git_sha` differs from current HEAD by more than a configurable threshold, default 20 commits)
- The refresh orchestrator SHALL handle partial analyzer failures gracefully: if one analyzer fails, produce available results with a note about the failure

#### Scenario: Full generation
- **WHEN** `make architecture` is run with no arguments
- **THEN** all analyzers, compiler, validator, and view generator SHALL execute
- **AND** `.architecture/` SHALL contain `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, and `views/` directory

#### Scenario: Baseline diff detects new cycle
- **WHEN** `make architecture:diff BASE_SHA=abc123` is run and the current graph contains a dependency cycle that did not exist at the baseline
- **THEN** the diff report SHALL list the new cycle with the involved modules

#### Scenario: Stale artifact detection
- **WHEN** an artifact's snapshot `git_sha` is more than 20 commits behind HEAD
- **THEN** the system SHALL log a warning about stale artifacts when the refresh command is run

#### Scenario: Partial analyzer failure
- **WHEN** the TypeScript analyzer fails (e.g., missing tsconfig.json) but Python and Postgres analyzers succeed
- **THEN** the refresh orchestrator SHALL log the TypeScript failure
- **AND** produce `architecture.graph.json` with available nodes/edges and a note in the snapshot about the missing TypeScript analysis

### Requirement: Committed Architecture Artifacts

The system SHALL commit architecture artifacts to the repository to track structural evolution and provide consistent context across environments.

- The `.architecture/` directory SHALL be committed to the repository (not gitignored)
- Committed artifacts SHALL include: `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, `parallel_zones.json`, and `views/` directory
- Per-language intermediate outputs (`python_analysis.json`, `ts_analysis.json`, `postgres_analysis.json`) MAY be committed or generated as CI artifacts
- The `.architecture/README.md` SHALL explain artifact purpose, refresh workflow, and how agents should use the artifacts
- CLAUDE.md SHALL reference `.architecture/` artifacts with instructions for agents to consult them before planning or implementing

#### Scenario: Consistent context across clones
- **WHEN** a developer clones the repository without analysis tool dependencies installed
- **THEN** `.architecture/architecture.summary.json` SHALL be available for reading without running any scripts

#### Scenario: Track structural evolution
- **WHEN** architecture artifacts are regenerated after a refactoring
- **THEN** `git diff .architecture/` SHALL show how the architectural structure changed (new nodes, removed edges, changed flows)

### Requirement: Skill Workflow Integration

The system SHALL integrate architecture artifacts into the `plan-feature`, `implement-feature`, and `validate-feature` skill workflows.

- The `plan-feature` skill SHALL consult `architecture.summary.json` and cross-layer flows as planning context before generating a proposal
- The `implement-feature` skill SHALL run the flow validator after implementation and before PR creation, including diagnostics in the PR description
- The `validate-feature` skill SHALL include architecture diagnostics in its validation report alongside existing checks
- Skill documentation SHALL recommend running `make architecture` as a pre-step when artifacts are stale

#### Scenario: Planning with architecture context
- **WHEN** the `plan-feature` skill is invoked for a feature that touches the users API
- **THEN** the skill SHALL read `architecture.summary.json` to understand which components, services, and tables are involved in user-related flows
- **AND** the generated proposal SHALL reference specific architectural nodes and flows

#### Scenario: Implementation validation before PR
- **WHEN** the `implement-feature` skill finishes implementation and prepares a PR
- **THEN** the skill SHALL run `validate_flows.py` with the changed files as scope
- **AND** any `error`-level findings SHALL be surfaced in the PR description

#### Scenario: Validation includes architecture diagnostics
- **WHEN** the `validate-feature` skill runs its validation suite
- **THEN** architecture diagnostics (broken flows, missing tests, orphaned code) SHALL be included alongside existing test and lint results
