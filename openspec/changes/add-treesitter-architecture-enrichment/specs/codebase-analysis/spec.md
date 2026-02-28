## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: CI Integration and Baseline Diffing (MODIFIED)

The `make architecture` target SHALL include the tree-sitter enrichment pass when tree-sitter is available, executing it as a Layer 1.5 step between code analysis and insight synthesis. When tree-sitter is not available, the pipeline SHALL skip the enrichment pass without error.

#### Scenario: Full generation with tree-sitter
- **WHEN** `make architecture` is run with tree-sitter available
- **THEN** the pipeline SHALL execute: Layer 1 (analyzers including tree-sitter SQL) → Layer 1.5 (tree-sitter enrichment for Python + TypeScript) → Layer 2 (insights including comment linker and pattern reporter) → Layer 3 (report)
- **AND** `treesitter_enrichment.json`, `comment_insights.json`, and `pattern_insights.json` SHALL be generated

#### Scenario: Full generation without tree-sitter
- **WHEN** `make architecture` is run without tree-sitter installed
- **THEN** the pipeline SHALL execute the standard Layer 1 → Layer 2 → Layer 3 pipeline
- **AND** `treesitter_enrichment.json`, `comment_insights.json`, and `pattern_insights.json` SHALL not be generated
- **AND** no errors SHALL be raised

### Requirement: Three-Layer Analysis Architecture (MODIFIED)

Layer 1 SHALL include an optional tree-sitter enrichment sub-phase (Layer 1.5) that runs after per-language analyzers complete and before Layer 2 insight synthesis. This sub-phase SHALL consume Layer 1 outputs and source code to produce supplementary analysis artifacts. The sub-phase SHALL be skippable without affecting the core pipeline.

#### Scenario: Tree-sitter enrichment integrates into pipeline
- **WHEN** tree-sitter is available and the pipeline executes
- **THEN** the enrichment pass SHALL run after all Layer 1 analyzers complete
- **AND** its output SHALL be available as input to Layer 2 modules
