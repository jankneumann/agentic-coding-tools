# codebase-analysis Specification

## Purpose
TBD - created by archiving change add-codebase-analysis-architecture. Update Purpose after archive.
## Requirements
### Requirement: Canonical Architecture Graph Schema

The system SHALL define a single normalized JSON schema for architecture artifacts that all per-language analyzers feed into. The canonical graph SHALL be the single source of truth for architectural relationships across all languages and layers.

- The schema SHALL include four top-level objects: `nodes[]`, `edges[]`, `entrypoints[]`, and `snapshots[]`
- Each node SHALL have: `id` (stable, format `{prefix}:{qualified_name}` where prefix is `py` for Python, `ts` for TypeScript, `pg` for Postgres), `kind` (function, class, component, hook, table, module), `language` (python, typescript, sql), `name`, `file`, `span` (start/end line numbers), `tags[]`, and `signatures` (language-specific metadata)
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
- The compiler SHALL normalize all symbols into stable node IDs using the `{prefix}:{qualified_name}` convention (where prefix is `py`, `ts`, or `pg`)
- The compiler SHALL be decomposed into Layer 2 insight modules: `graph_builder.py` for canonical graph construction, `cross_layer_linker.py` for frontend-to-backend linking, and `db_linker.py` for backend-to-database linking
- The compiler SHALL perform Frontend→Backend linking: match TypeScript API call URLs to Python route decorator paths
- The compiler SHALL perform Backend→Database linking: match Python database access patterns to Postgres table names
- The compiler SHALL infer Frontend→Database indirect flows by chaining endpoint→service→query→table paths
- Every cross-language edge SHALL include confidence (high = exact URL match, medium = parameterized path match, low = heuristic) and evidence (description of how the link was detected)
- The compiler SHALL produce `architecture.graph.json` (full graph) and `architecture.summary.json` (compact, using adaptive confidence threshold for flow inclusion)
- The compiler SHALL read TypeScript API call sites from the `api_call_sites` key in `ts_analysis.json` (not `api_calls`)
- The compiler SHALL read Postgres stored functions from the `stored_functions` key in `postgres_analysis.json` (not `functions`)
- The compiler SHALL NOT prepend schema to already-qualified table names from `postgres_analysis.json` when constructing FK edge node IDs

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

#### Scenario: Correct Postgres FK node IDs
- **WHEN** `postgres_analysis.json` contains a foreign key with `from_table: "public.users"` and `to_table: "public.orders"`
- **THEN** the compiler SHALL produce FK edge node IDs `pg:public.users` and `pg:public.orders`
- **AND** SHALL NOT produce malformed IDs like `pg:public.public.users`

#### Scenario: Read TypeScript API call sites correctly
- **WHEN** `ts_analysis.json` contains API call sites under the `api_call_sites` key
- **THEN** the compiler SHALL read them from that key for cross-language linking
- **AND** frontend-to-backend edges SHALL be created for matching URLs

#### Scenario: Read Postgres stored functions correctly
- **WHEN** `postgres_analysis.json` contains stored functions under the `stored_functions` key
- **THEN** the compiler SHALL ingest them as `stored_function` nodes in the canonical graph

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
- All views SHALL be written to `docs/architecture-analysis/views/`

#### Scenario: Generate container view
- **WHEN** the view generator is run on a canonical graph containing frontend, backend, and database nodes
- **THEN** `docs/architecture-analysis/views/containers.mmd` SHALL contain a Mermaid diagram with boxes for each container and arrows for cross-container edges

#### Scenario: Generate feature slice view
- **WHEN** the view generator is given a file list from a PR (e.g., `backend/api/users.py`, `src/components/UserProfile.tsx`)
- **THEN** it SHALL extract only the nodes and edges touched by those files
- **AND** emit both `docs/architecture-analysis/views/feature_users.json` (subgraph) and `docs/architecture-analysis/views/feature_users.mmd` (Mermaid diagram)

#### Scenario: Generate DB ERD
- **WHEN** the canonical graph contains table nodes with FK edges
- **THEN** `docs/architecture-analysis/views/db_erd.mmd` SHALL contain a Mermaid entity-relationship diagram showing tables and their relationships

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
- The system SHALL provide `make architecture-diff BASE_SHA=...` to compare the current graph to a baseline and report changes
- The diff report SHALL include: new dependency cycles introduced, new high-impact modules, routes added without tests, DB tables touched without corresponding migrations
- The system SHALL provide `make architecture-feature FEATURE=...` to extract a feature-scoped subgraph for PR review
- Every generated artifact SHALL include `generated_at`, `git_sha`, and `tool_versions` in a snapshot object
- The system SHALL warn when artifacts are stale (snapshot `git_sha` differs from current HEAD by more than a configurable threshold, default 20 commits)
- The refresh orchestrator SHALL handle partial analyzer failures gracefully: if one analyzer fails, produce available results with a note about the failure
- The refresh orchestrator SHALL execute the pipeline in three explicit stages: Layer 1 (code analysis, parallelizable), Layer 2 (insight synthesis, dependency-ordered), Layer 3 (report aggregation)
- The TypeScript analyzer invocation SHALL include the required `<directory>` positional argument
- The `make architecture` target SHALL include the tree-sitter enrichment pass when tree-sitter is available, executing it as a Layer 1.5 step between code analysis and insight synthesis. When tree-sitter is not available, the pipeline SHALL skip the enrichment pass without error.

#### Scenario: Full generation
- **WHEN** `make architecture` is run with no arguments
- **THEN** all analyzers, insight modules, and report aggregator SHALL execute in layer order
- **AND** `docs/architecture-analysis/` SHALL contain `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, `architecture.report.md`, and `views/` directory

#### Scenario: Full generation with tree-sitter
- **WHEN** `make architecture` is run with tree-sitter available
- **THEN** the pipeline SHALL execute: Layer 1 (analyzers including tree-sitter SQL) → Layer 1.5 (tree-sitter enrichment for Python + TypeScript) → Layer 2 (insights including comment linker and pattern reporter) → Layer 3 (report)
- **AND** `treesitter_enrichment.json`, `comment_insights.json`, and `pattern_insights.json` SHALL be generated

#### Scenario: Full generation without tree-sitter
- **WHEN** `make architecture` is run without tree-sitter installed
- **THEN** the pipeline SHALL execute the standard Layer 1 → Layer 2 → Layer 3 pipeline
- **AND** `treesitter_enrichment.json`, `comment_insights.json`, and `pattern_insights.json` SHALL not be generated
- **AND** no errors SHALL be raised

#### Scenario: Baseline diff detects new cycle
- **WHEN** `make architecture-diff BASE_SHA=abc123` is run and the current graph contains a dependency cycle that did not exist at the baseline
- **THEN** the diff report SHALL list the new cycle with the involved modules

#### Scenario: Partial analyzer failure
- **WHEN** the TypeScript analyzer fails (e.g., missing tsconfig.json) but Python and Postgres analyzers succeed
- **THEN** the refresh orchestrator SHALL log the TypeScript failure
- **AND** produce `architecture.graph.json` with available nodes/edges and a note in the snapshot about the missing TypeScript analysis
- **AND** the Layer 3 report SHALL note which analyzers were unavailable

### Requirement: Committed Architecture Artifacts

The system SHALL commit architecture artifacts to the repository to track structural evolution and provide consistent context across environments.

- The `docs/architecture-analysis/` directory SHALL be committed to the repository (not gitignored)
- Committed artifacts SHALL include: `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, `parallel_zones.json`, and `views/` directory
- Per-language intermediate outputs (`python_analysis.json`, `ts_analysis.json`, `postgres_analysis.json`) MAY be committed or generated as CI artifacts
- The `docs/architecture-analysis/README.md` SHALL explain artifact purpose, refresh workflow, and how agents should use the artifacts
- CLAUDE.md SHALL reference `docs/architecture-analysis/` artifacts with instructions for agents to consult them before planning or implementing

#### Scenario: Consistent context across clones
- **WHEN** a developer clones the repository without analysis tool dependencies installed
- **THEN** `docs/architecture-analysis/architecture.summary.json` SHALL be available for reading without running any scripts

#### Scenario: Track structural evolution
- **WHEN** architecture artifacts are regenerated after a refactoring
- **THEN** `git diff docs/architecture-analysis/` SHALL show how the architectural structure changed (new nodes, removed edges, changed flows)

### Requirement: Skill Workflow Integration

The system SHALL integrate architecture artifacts into the `plan-feature`, `implement-feature`, and `validate-feature` skill workflows.

- The `plan-feature` skill SHALL consult `docs/architecture-analysis/architecture.summary.json` and cross-layer flows as planning context before generating a proposal
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

### Requirement: Scripts Dependency Management

The scripts directory SHALL have a `scripts/pyproject.toml` managed by `uv` that declares external Python dependencies for architecture analysis tooling.

- The `pyproject.toml` SHALL declare `tree-sitter>=0.24.0`, `tree-sitter-sql>=0.3.0`, `tree-sitter-python>=0.24.0`, and `tree-sitter-typescript>=0.24.0` as dependencies
- The scripts venv SHALL be created at `scripts/.venv` using `uv sync`
- All tree-sitter-dependent scripts SHALL be executable via `scripts/.venv/bin/python`
- The `Makefile` SHALL include a target to set up the scripts venv (`make scripts-setup` or equivalent)

#### Scenario: Install scripts dependencies
- **WHEN** a developer runs `cd scripts && uv sync`
- **THEN** `scripts/.venv` SHALL be created with tree-sitter and grammar packages installed
- **AND** `scripts/.venv/bin/python -c "import tree_sitter; import tree_sitter_sql; import tree_sitter_python; import tree_sitter_typescript"` SHALL succeed

#### Scenario: CI installs scripts dependencies
- **WHEN** CI runs the architecture analysis pipeline
- **THEN** it SHALL install scripts dependencies via `uv sync` before running tree-sitter-based analyzers
- **AND** the pipeline SHALL complete without import errors

### Requirement: Tree-sitter SQL Analyzer

The system SHALL provide a tree-sitter-based SQL analyzer (`scripts/analyze_sql_treesitter.py`) that parses SQL migration files using the tree-sitter SQL grammar to extract schema information.

- The analyzer SHALL parse `CREATE TABLE`, `ALTER TABLE ADD COLUMN`, `ALTER TABLE ADD CONSTRAINT`, `CREATE INDEX`, `CREATE FUNCTION` (including PL/pgSQL bodies), and `CREATE TRIGGER` statements using tree-sitter's concrete syntax tree
- The analyzer SHALL produce `postgres_analysis.json` output conforming to the same schema as the existing regex-based analyzer for backward compatibility with Layer 2 consumers
- The analyzer SHALL construct a cumulative schema by parsing migration files in numbered order
- The analyzer SHALL extract foreign key relationships, column types, nullability, and default values from the CST
- The analyzer SHALL accept `--migrations-dir`, `--output`, and `--schema` CLI arguments matching the existing analyzer interface
- The analyzer SHALL handle PL/pgSQL function bodies that the regex parser silently skips, extracting function signatures, return types, and referenced table names

#### Scenario: Parse CREATE TABLE with foreign keys
- **WHEN** a migration file contains `CREATE TABLE orders (id SERIAL PRIMARY KEY, user_id INT REFERENCES users(id))`
- **THEN** `postgres_analysis.json` SHALL contain a table node for `orders` with columns `id` and `user_id`
- **AND** a foreign key relationship from `orders.user_id` to `users.id`

#### Scenario: Parse PL/pgSQL function body
- **WHEN** a migration file contains `CREATE FUNCTION claim_task(...) RETURNS JSONB AS $$ BEGIN ... END $$ LANGUAGE plpgsql`
- **THEN** `postgres_analysis.json` SHALL contain a stored function entry with the function name, parameter types, return type, and referenced table names extracted from the body
- **AND** the regex-based analyzer's silently-skipped PL/pgSQL content SHALL be captured

#### Scenario: Backward-compatible output schema
- **WHEN** the tree-sitter SQL analyzer produces `postgres_analysis.json`
- **THEN** the output SHALL be consumable by `insights/graph_builder.py` and `insights/db_linker.py` without modification
- **AND** the keys `tables`, `foreign_keys`, `indexes`, `stored_functions`, `triggers` SHALL be present

#### Scenario: Unparseable SQL statement
- **WHEN** a migration file contains vendor-specific SQL that tree-sitter cannot parse
- **THEN** the analyzer SHALL log a warning identifying the file and line number
- **AND** continue processing subsequent statements and remaining files
- **AND** the output SHALL include all successfully parsed artifacts

### Requirement: Graceful Tree-sitter Fallback

The architecture analysis pipeline SHALL gracefully fall back to existing analyzers when tree-sitter is unavailable.

- The refresh orchestrator SHALL detect whether tree-sitter is installed by attempting to import the package
- **WHEN** tree-sitter is available, the pipeline SHALL use `analyze_sql_treesitter.py` for SQL analysis
- **WHEN** tree-sitter is unavailable, the pipeline SHALL fall back to `analyze_postgres.py` (regex parser) with an informational warning
- The `TREESITTER_ENABLED` environment variable SHALL allow explicit opt-in (`true`) or opt-out (`false`), overriding auto-detection

#### Scenario: Tree-sitter available
- **WHEN** `scripts/.venv` exists with tree-sitter installed and `TREESITTER_ENABLED` is not set to `false`
- **THEN** the pipeline SHALL use `analyze_sql_treesitter.py`
- **AND** the snapshot metadata SHALL record `tree_sitter_sql: <version>`

#### Scenario: Tree-sitter unavailable
- **WHEN** tree-sitter is not installed and `TREESITTER_ENABLED` is not set to `true`
- **THEN** the pipeline SHALL use `analyze_postgres.py` (regex parser)
- **AND** log `INFO: tree-sitter not available, using regex SQL parser`
- **AND** the snapshot metadata SHALL record `tree_sitter_sql: null`

#### Scenario: Explicit opt-out
- **WHEN** `TREESITTER_ENABLED=false` is set
- **THEN** the pipeline SHALL use the regex parser even if tree-sitter is installed

### Requirement: Comment and Annotation Extraction

The system SHALL provide a tree-sitter enrichment pass (`scripts/enrich_with_treesitter.py`) that extracts comments, TODO markers, and documentation blocks from Python and TypeScript source code.

- The enrichment pass SHALL extract all comments from Python source files using the tree-sitter Python grammar and from TypeScript source files using the tree-sitter TypeScript grammar
- The enrichment pass SHALL classify comments as: `inline` (end-of-line), `block` (multi-line), `doc` (docstrings/JSDoc), or `marker` (TODO/FIXME/HACK/NOTE patterns)
- Each extracted comment SHALL be associated with the nearest enclosing function or class node from the architecture graph (by file path and line range)
- The enrichment pass SHALL produce `treesitter_enrichment.json` containing sections for `comments`, `python_patterns`, `typescript_patterns`, and `security_patterns`
- Comment entries SHALL have fields: `file`, `line`, `type`, `text`, `associated_node_id`, `language`
- The enrichment pass SHALL be idempotent: running it twice on the same input produces identical output

#### Scenario: Extract TODO markers from Python
- **WHEN** a Python file contains `# TODO: refactor this to use async` on line 42 inside function `process_request`
- **THEN** `treesitter_enrichment.json` SHALL contain a comment entry with `type: "marker"`, `text: "TODO: refactor this to use async"`, `line: 42`, `associated_node_id: "py:module.process_request"`, `language: "python"`

#### Scenario: Extract comments from TypeScript
- **WHEN** a TypeScript file contains `// TODO: add error handling` on line 15 inside function `fetchUsers`
- **THEN** `treesitter_enrichment.json` SHALL contain a comment entry with `type: "marker"`, `language: "typescript"`

#### Scenario: No comments in file
- **WHEN** a source file contains no comments
- **THEN** the enrichment pass SHALL produce no comment entries for that file
- **AND** SHALL not produce an error

### Requirement: Python Pattern Enrichment

The enrichment pass SHALL extract structural patterns from Python source code that `analyze_python.py` (using stdlib `ast`) does not capture.

- The enrichment pass SHALL detect exception handling patterns: bare `except:` clauses, broad `except Exception` catches, and empty `except` bodies (pass-only or ellipsis-only)
- The enrichment pass SHALL detect context manager usage: `with` blocks, identifying the context manager expression (file handles, DB transactions, locks) and associating them with enclosing functions
- The enrichment pass SHALL extract type hints: function parameter types and return type annotations that `analyze_python.py` currently ignores
- The enrichment pass SHALL detect assertion patterns: `assert` statements in non-test files
- Python pattern entries SHALL be stored in `treesitter_enrichment.json` under the `python_patterns` key with fields: `file`, `line`, `pattern_type`, `detail`, `associated_node_id`

#### Scenario: Detect bare except clause
- **WHEN** a Python function contains `except:` (bare except without an exception type)
- **THEN** `treesitter_enrichment.json` SHALL contain a python_pattern entry with `pattern_type: "bare_except"` and the enclosing function's node ID

#### Scenario: Extract type hints
- **WHEN** a Python function is defined as `def process(data: dict[str, Any]) -> bool:`
- **THEN** `treesitter_enrichment.json` SHALL contain a python_pattern entry with `pattern_type: "type_hints"`, including parameter types `{"data": "dict[str, Any]"}` and return type `"bool"`

#### Scenario: Detect context manager with DB transaction
- **WHEN** a Python function contains `with db.transaction() as tx:`
- **THEN** `treesitter_enrichment.json` SHALL contain a python_pattern entry with `pattern_type: "context_manager"`, `detail` containing the context expression `"db.transaction()"`

#### Scenario: File with no patterns
- **WHEN** a Python file contains no exception handlers, context managers, type hints, or assertions
- **THEN** the enrichment pass SHALL produce no python_pattern entries for that file

### Requirement: TypeScript Pattern Enrichment

The enrichment pass SHALL extract structural patterns from TypeScript source code that `analyze_typescript.ts` (using ts-morph) does not capture.

- The enrichment pass SHALL detect error handling patterns: try/catch blocks with empty catch bodies, catch clauses that don't type the error parameter, and catch clauses that silently swallow errors
- The enrichment pass SHALL detect dynamic import expressions (`import()`) that are not captured by the static import graph in `ts_analysis.json`
- TypeScript pattern entries SHALL be stored in `treesitter_enrichment.json` under the `typescript_patterns` key with fields: `file`, `line`, `pattern_type`, `detail`, `associated_node_id`

#### Scenario: Detect empty catch block
- **WHEN** a TypeScript function contains `catch (e) {}` (empty catch body)
- **THEN** `treesitter_enrichment.json` SHALL contain a typescript_pattern entry with `pattern_type: "empty_catch"`

#### Scenario: Detect dynamic import
- **WHEN** a TypeScript file contains `const module = await import("./heavy-module")`
- **THEN** `treesitter_enrichment.json` SHALL contain a typescript_pattern entry with `pattern_type: "dynamic_import"`, `detail` containing the import path `"./heavy-module"`

#### Scenario: No TypeScript files in project
- **WHEN** the project contains no TypeScript files
- **THEN** the enrichment pass SHALL produce no typescript_pattern entries
- **AND** SHALL not produce an error

### Requirement: Configurable Pattern Query Library

The system SHALL provide a configurable S-expression query library at `scripts/treesitter_queries/` that defines reusable patterns per language.

- The query library SHALL contain `.scm` files organized by language and concern: `python.scm`, `typescript.scm`, `security.scm`
- Each query file SHALL contain named S-expression patterns with capture names following the convention `@pattern_name.detail`
- The enrichment pass SHALL load query files from the library directory and execute them against parsed source trees
- New patterns SHALL be addable by creating or editing `.scm` files without modifying Python code
- The `security.scm` file SHALL contain cross-language security patterns: SQL built via string concatenation or f-strings, hardcoded secret patterns (variable names containing `password`, `secret`, `token`, `key` assigned string literals), and `eval()`/`exec()` usage
- Security pattern entries SHALL be stored in `treesitter_enrichment.json` under the `security_patterns` key

#### Scenario: Add a new pattern without code changes
- **WHEN** a developer adds a new S-expression query to `scripts/treesitter_queries/python.scm`
- **THEN** the next enrichment pass SHALL automatically execute the new query
- **AND** matching results SHALL appear in `treesitter_enrichment.json`

#### Scenario: Detect SQL string concatenation
- **WHEN** a Python function contains `query = "SELECT * FROM " + table_name`
- **THEN** `treesitter_enrichment.json` SHALL contain a security_pattern entry with `pattern_type: "sql_string_concat"`

#### Scenario: Detect hardcoded secret
- **WHEN** a Python file contains `API_SECRET = "sk-abc123def456"`
- **THEN** `treesitter_enrichment.json` SHALL contain a security_pattern entry with `pattern_type: "hardcoded_secret"`, identifying the variable name and file location

#### Scenario: Invalid query file
- **WHEN** a `.scm` file contains an invalid S-expression query
- **THEN** the enrichment pass SHALL log a warning identifying the file and invalid query
- **AND** continue processing remaining valid queries

### Requirement: Pattern Reporter Insight Module

The system SHALL provide a Layer 2 insight module (`scripts/insights/pattern_reporter.py`) that aggregates pattern query findings from the enrichment pass into actionable reports.

- The module SHALL follow the standard insight module interface: `--input-dir` and `--output` CLI arguments
- The module SHALL read `treesitter_enrichment.json` from the input directory
- The module SHALL produce `pattern_insights.json` containing: per-module pattern counts by category (exception handling, context managers, type coverage, security), top findings ranked by severity, and type hint coverage percentage (functions with type hints vs total functions)
- The module SHALL be independently executable and testable with fixture inputs

#### Scenario: Report type hint coverage
- **WHEN** `treesitter_enrichment.json` contains type hint entries for 30 out of 100 functions
- **THEN** `pattern_insights.json` SHALL report `type_hint_coverage: 0.30` and list the 70 uncovered functions

#### Scenario: Report security findings
- **WHEN** `treesitter_enrichment.json` contains 3 `sql_string_concat` and 1 `hardcoded_secret` security pattern entries
- **THEN** `pattern_insights.json` SHALL list them under `security_findings` with severity rankings

#### Scenario: Missing enrichment input
- **WHEN** `treesitter_enrichment.json` does not exist in the input directory
- **THEN** the module SHALL exit with code 0
- **AND** produce an empty `pattern_insights.json` with a note: `"skipped": "treesitter_enrichment.json not found"`

### Requirement: Comment Linker Insight Module

The system SHALL provide a Layer 2 insight module (`scripts/insights/comment_linker.py`) that maps extracted comments and markers to architecture graph nodes and produces actionable findings.

- The module SHALL follow the standard insight module interface: `--input-dir` and `--output` CLI arguments
- The module SHALL read `treesitter_enrichment.json` and `architecture.graph.json` from the input directory
- The module SHALL produce `comment_insights.json` containing: TODO/FIXME counts per module, documentation coverage (functions with/without docstrings), marker hotspots (files/modules with high marker density)
- The module SHALL be independently executable and testable with fixture inputs

#### Scenario: Identify marker hotspots
- **WHEN** `treesitter_enrichment.json` contains 15 TODO markers in `src/locks.py` and 2 in `src/config.py`
- **THEN** `comment_insights.json` SHALL list `src/locks.py` as a marker hotspot
- **AND** include the count and top marker texts

#### Scenario: Missing enrichment input
- **WHEN** `treesitter_enrichment.json` does not exist in the input directory
- **THEN** the module SHALL exit with code 0
- **AND** produce an empty `comment_insights.json` with a note: `"skipped": "treesitter_enrichment.json not found"`

### Requirement: Three-Layer Analysis Architecture

The codebase analysis pipeline SHALL be organized into three distinct layers with well-defined responsibilities and interfaces:

- **Layer 1 (Code Analysis)**: Per-language analyzer modules that examine specific aspects of the codebase and produce self-contained JSON artifacts. Each module SHALL take a source directory as input and produce a single JSON file as output, with no dependency on other Layer 1 modules.
- **Layer 2 (Insight Synthesis)**: Modules that consume Layer 1 JSON outputs (and/or the canonical graph) and produce higher-level insights. Each module SHALL declare its input dependencies explicitly, be independently testable with fixture JSON inputs, and produce a single JSON or Markdown output.
- **Layer 3 (Report Aggregation)**: A report aggregator that collects all Layer 1 and Layer 2 outputs and composes them into a unified human-readable Markdown report.

The three layers SHALL execute in strict sequence: Layer 1 (parallelizable) → Layer 2 (dependency-ordered) → Layer 3.

Layer 1 SHALL include an optional tree-sitter enrichment sub-phase (Layer 1.5) that runs after per-language analyzers complete and before Layer 2 insight synthesis. This sub-phase SHALL consume Layer 1 outputs and source code to produce supplementary analysis artifacts. The sub-phase SHALL be skippable without affecting the core pipeline.

#### Scenario: Tree-sitter enrichment integrates into pipeline
- **WHEN** tree-sitter is available and the pipeline executes
- **THEN** the enrichment pass SHALL run after all Layer 1 analyzers complete
- **AND** its output SHALL be available as input to Layer 2 modules

#### Scenario: Layer 1 modules run independently
- **WHEN** the pipeline executes Layer 1
- **THEN** each analyzer (Python, TypeScript, Postgres) SHALL run independently with no dependency on other analyzers
- **AND** all three MAY execute in parallel

#### Scenario: Layer 2 modules declare input dependencies
- **WHEN** a new insight module is added to Layer 2
- **THEN** it SHALL declare which Layer 1 outputs and/or Layer 2 outputs it requires
- **AND** the orchestrator SHALL execute it only after all its dependencies have completed

#### Scenario: Layer 3 produces unified report
- **WHEN** all Layer 1 and Layer 2 modules have completed
- **THEN** the report aggregator SHALL produce `architecture.report.md` combining all analysis dimensions into a single human-readable document

#### Scenario: Adding a new analyzer does not modify existing modules
- **WHEN** a new Layer 1 analyzer is added (e.g., for Go or Rust)
- **THEN** it SHALL only need to produce a JSON file following the established schema conventions
- **AND** existing Layer 1, Layer 2, and Layer 3 modules SHALL require no modifications (only the orchestrator adds the new module to the pipeline)

### Requirement: Insight Module Interface

Each Layer 2 insight module SHALL follow a consistent interface:

- Each module SHALL be a standalone Python script under `scripts/insights/`
- Each module SHALL accept `--input-dir` (directory containing Layer 1 and intermediate outputs) and `--output` (path for its output file) CLI arguments
- Each module SHALL read only from its declared input files and write only to its declared output file
- Each module SHALL be independently executable and testable without running the full pipeline
- Each module SHALL exit with code 0 on success and non-zero on failure, writing errors to stderr

#### Scenario: Run a single insight module in isolation
- **WHEN** `scripts/insights/flow_tracer.py --input-dir docs/architecture-analysis --output docs/architecture-analysis/cross_layer_flows.json` is executed
- **THEN** it SHALL read `architecture.graph.json` from the input directory
- **AND** produce `cross_layer_flows.json` as output
- **AND** succeed without requiring any other insight modules to have run

#### Scenario: Test an insight module with fixture data
- **WHEN** an insight module is given a fixture `architecture.graph.json` containing known nodes and edges
- **THEN** its output SHALL be deterministic and verifiable against expected results

### Requirement: Report Aggregator

The system SHALL provide a report aggregator (`scripts/reports/architecture_report.py`) that produces a unified Markdown report from all analysis outputs.

- The aggregator SHALL read `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, `cross_layer_flows.json`, `parallel_zones.json`, and optionally Mermaid diagrams from `views/`
- The aggregator SHALL produce `architecture.report.md` with sections for: Executive Summary, Cross-Layer Flows, Diagnostics and Warnings, Impact Analysis, Parallel Modification Zones, and (optionally) embedded Mermaid diagrams
- The aggregator SHALL gracefully handle missing inputs by omitting the corresponding report section with a note
- The aggregator SHALL include metadata (generation timestamp, git SHA, which modules contributed)

#### Scenario: Generate full report
- **WHEN** all Layer 1 and Layer 2 outputs are available
- **THEN** `architecture.report.md` SHALL contain all sections with data from every module

#### Scenario: Generate partial report
- **WHEN** the TypeScript analyzer was skipped (no frontend source)
- **THEN** `architecture.report.md` SHALL omit frontend-specific sections
- **AND** include a note indicating which analysis modules were unavailable

