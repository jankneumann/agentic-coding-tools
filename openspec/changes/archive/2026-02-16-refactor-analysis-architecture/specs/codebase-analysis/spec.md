## ADDED Requirements

### Requirement: Three-Layer Analysis Architecture

The codebase analysis pipeline SHALL be organized into three distinct layers with well-defined responsibilities and interfaces:

- **Layer 1 (Code Analysis)**: Per-language analyzer modules that examine specific aspects of the codebase and produce self-contained JSON artifacts. Each module SHALL take a source directory as input and produce a single JSON file as output, with no dependency on other Layer 1 modules.
- **Layer 2 (Insight Synthesis)**: Modules that consume Layer 1 JSON outputs (and/or the canonical graph) and produce higher-level insights. Each module SHALL declare its input dependencies explicitly, be independently testable with fixture JSON inputs, and produce a single JSON or Markdown output.
- **Layer 3 (Report Aggregation)**: A report aggregator that collects all Layer 1 and Layer 2 outputs and composes them into a unified human-readable Markdown report.

The three layers SHALL execute in strict sequence: Layer 1 (parallelizable) → Layer 2 (dependency-ordered) → Layer 3.

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
- **WHEN** `scripts/insights/flow_tracer.py --input-dir .architecture --output .architecture/cross_layer_flows.json` is executed
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

## MODIFIED Requirements

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

#### Scenario: Full generation
- **WHEN** `make architecture` is run with no arguments
- **THEN** all analyzers, insight modules, and report aggregator SHALL execute in layer order
- **AND** `.architecture/` SHALL contain `architecture.graph.json`, `architecture.summary.json`, `architecture.diagnostics.json`, `architecture.report.md`, and `views/` directory

#### Scenario: Baseline diff detects new cycle
- **WHEN** `make architecture-diff BASE_SHA=abc123` is run and the current graph contains a dependency cycle that did not exist at the baseline
- **THEN** the diff report SHALL list the new cycle with the involved modules

#### Scenario: Partial analyzer failure
- **WHEN** the TypeScript analyzer fails (e.g., missing tsconfig.json) but Python and Postgres analyzers succeed
- **THEN** the refresh orchestrator SHALL log the TypeScript failure
- **AND** produce `architecture.graph.json` with available nodes/edges and a note in the snapshot about the missing TypeScript analysis
- **AND** the Layer 3 report SHALL note which analyzers were unavailable
