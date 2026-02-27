# Tasks: add-treesitter-architecture-enrichment

## 1. Foundation (Sequential)

- [x] 1.1 Create `scripts/pyproject.toml` with tree-sitter dependencies
  **Dependencies**: None
  **Files**: `scripts/pyproject.toml`
  **Traces**: Scripts Dependency Management
  **Verify**: `cd scripts && uv sync && .venv/bin/python -c "import tree_sitter; import tree_sitter_sql; import tree_sitter_python; import tree_sitter_typescript; print('OK')"`

- [x] 1.2 Add Makefile target for scripts venv setup
  **Dependencies**: 1.1
  **Files**: `Makefile`
  **Traces**: Scripts Dependency Management
  **Verify**: `make scripts-setup` creates `scripts/.venv` with tree-sitter installed

## 2. Tree-sitter SQL Analyzer (Parallelizable after 1.1)

- [x] 2.1 Create `scripts/analyze_sql_treesitter.py` — core CST parser
  **Dependencies**: 1.1
  **Files**: `scripts/analyze_sql_treesitter.py`
  **Traces**: Tree-sitter SQL Analyzer
  **Description**: Implement tree-sitter-based SQL migration parser that walks the CST to extract tables, columns, foreign keys, indexes, stored functions, and triggers. Accept `--migrations-dir`, `--output`, and `--schema` CLI arguments. Produce `postgres_analysis.json` conforming to the existing schema.
  **Verify**: Run against `supabase/migrations/` and diff output structure against existing `postgres_analysis.json`

- [x] 2.2 Add PL/pgSQL function body extraction
  **Dependencies**: 2.1
  **Files**: `scripts/analyze_sql_treesitter.py`
  **Traces**: Tree-sitter SQL Analyzer
  **Description**: Extend the SQL analyzer to parse PL/pgSQL function bodies, extracting referenced table names, DML operations, and function parameter/return types that the regex parser silently skips.
  **Verify**: Parse migration files containing `CREATE FUNCTION ... LANGUAGE plpgsql` and verify stored function entries include parameter types, return type, and referenced tables

- [x] 2.3 Write unit tests for tree-sitter SQL analyzer
  **Dependencies**: 2.2
  **Files**: `scripts/tests/test_analyze_sql_treesitter.py`
  **Traces**: Tree-sitter SQL Analyzer
  **Verify**: `scripts/.venv/bin/python -m pytest scripts/tests/test_analyze_sql_treesitter.py -v` — all pass

## 3. Pattern Query Library (Parallelizable with Group 2 after 1.1)

- [x] 3.1 Create `scripts/treesitter_queries/` S-expression query library
  **Dependencies**: 1.1
  **Files**: `scripts/treesitter_queries/python.scm`, `scripts/treesitter_queries/typescript.scm`, `scripts/treesitter_queries/security.scm`
  **Traces**: Configurable Pattern Query Library
  **Description**: Create S-expression query files for Python patterns (bare except, broad except, empty except, context managers, type hints, assertions), TypeScript patterns (empty catch, untyped catch, dynamic imports), and cross-language security patterns (SQL string concatenation, f-string SQL, hardcoded secrets, eval/exec usage). Use `@pattern_name.detail` capture naming convention.
  **Verify**: Each `.scm` file loads without parse errors via `tree_sitter.Query(language, query_text)`

## 4. Enrichment Engine (Parallelizable with Groups 2 & 3 after 1.1)

- [x] 4.1 Create `scripts/enrich_with_treesitter.py` — core enrichment engine
  **Dependencies**: 1.1
  **Files**: `scripts/enrich_with_treesitter.py`
  **Traces**: Comment and Annotation Extraction
  **Description**: Implement tree-sitter enrichment pass with comment extraction for Python and TypeScript files. Parse source files, extract and classify all comments (inline, block, doc, marker), associate each with the nearest enclosing function/class node from `architecture.graph.json`. Produce `treesitter_enrichment.json` with `comments` section.
  **Verify**: Run against `agent-coordinator/src/` and verify output contains classified comments with node associations for both languages

- [x] 4.2 Add Python pattern extraction to enrichment engine
  **Dependencies**: 3.1, 4.1
  **Files**: `scripts/enrich_with_treesitter.py`
  **Traces**: Python Pattern Enrichment, Configurable Pattern Query Library
  **Description**: Extend enrichment pass to load S-expression queries from `scripts/treesitter_queries/python.scm` and execute them against Python source files. Extract exception handling patterns (bare/broad/empty except), context manager usage, type hints (parameter and return types), and assertion patterns. Store results in `python_patterns` section of `treesitter_enrichment.json`.
  **Verify**: Run against `agent-coordinator/src/` and verify exception handlers, context managers, and type hints are detected

- [x] 4.3 Add TypeScript pattern extraction to enrichment engine
  **Dependencies**: 3.1, 4.1
  **Files**: `scripts/enrich_with_treesitter.py`
  **Traces**: TypeScript Pattern Enrichment, Configurable Pattern Query Library
  **Description**: Extend enrichment pass to load S-expression queries from `scripts/treesitter_queries/typescript.scm` and execute them against TypeScript source files. Extract error handling patterns (empty catch, untyped catch) and dynamic import expressions. Store results in `typescript_patterns` section.
  **Verify**: Run against TypeScript test fixtures and verify empty catches and dynamic imports are detected

- [x] 4.4 Add security pattern extraction to enrichment engine
  **Dependencies**: 3.1, 4.1
  **Files**: `scripts/enrich_with_treesitter.py`
  **Traces**: Configurable Pattern Query Library
  **Description**: Extend enrichment pass to load cross-language security queries from `scripts/treesitter_queries/security.scm`. Detect SQL string concatenation, f-string SQL, hardcoded secrets, and eval/exec usage across Python and TypeScript. Store results in `security_patterns` section.
  **Verify**: Run against test fixtures containing known security anti-patterns and verify all are detected

- [x] 4.5 Write unit tests for enrichment engine
  **Dependencies**: 4.2, 4.3, 4.4
  **Files**: `scripts/tests/test_enrich_with_treesitter.py`
  **Traces**: Comment and Annotation Extraction, Python Pattern Enrichment, TypeScript Pattern Enrichment, Configurable Pattern Query Library
  **Verify**: `scripts/.venv/bin/python -m pytest scripts/tests/test_enrich_with_treesitter.py -v` — all pass

## 5. Insight Modules (After Group 4)

- [x] 5.1 Create `scripts/insights/comment_linker.py` — Layer 2 insight module
  **Dependencies**: 4.5
  **Files**: `scripts/insights/comment_linker.py`
  **Traces**: Comment Linker Insight Module
  **Description**: Layer 2 module following standard interface (`--input-dir`, `--output`). Read `treesitter_enrichment.json` and `architecture.graph.json`. Produce `comment_insights.json` with TODO/FIXME counts per module, documentation coverage metrics, and marker hotspot identification. Handle missing input gracefully.
  **Verify**: Run with fixture data and verify output schema; run with missing input and verify graceful skip

- [x] 5.2 Create `scripts/insights/pattern_reporter.py` — Layer 2 insight module
  **Dependencies**: 4.5
  **Files**: `scripts/insights/pattern_reporter.py`
  **Traces**: Pattern Reporter Insight Module
  **Description**: Layer 2 module following standard interface. Read `treesitter_enrichment.json`. Produce `pattern_insights.json` with per-module pattern counts by category, type hint coverage percentage, security findings ranked by severity, and exception handling summary. Handle missing input gracefully.
  **Verify**: Run with fixture data and verify output schema; run with missing input and verify graceful skip

- [x] 5.3 Write unit tests for insight modules
  **Dependencies**: 5.1, 5.2
  **Files**: `scripts/tests/test_comment_linker.py`, `scripts/tests/test_pattern_reporter.py`
  **Traces**: Comment Linker Insight Module, Pattern Reporter Insight Module
  **Verify**: `scripts/.venv/bin/python -m pytest scripts/tests/test_comment_linker.py scripts/tests/test_pattern_reporter.py -v` — all pass

## 6. Pipeline Integration (Sequential, after Groups 2 & 5)

- [x] 6.1 Add graceful fallback detection to `refresh_architecture.sh`
  **Dependencies**: 2.3, 5.3
  **Files**: `scripts/refresh_architecture.sh`
  **Traces**: Graceful Tree-sitter Fallback, CI Integration and Baseline Diffing (MODIFIED)
  **Description**: Update the refresh script to detect tree-sitter availability (import check + `TREESITTER_ENABLED` env var). When available, use `analyze_sql_treesitter.py` instead of `analyze_postgres.py`, run enrichment pass after Layer 1, and include comment_linker + pattern_reporter in Layer 2. Record tree-sitter version in snapshot metadata.
  **Verify**: Run `make architecture` with and without tree-sitter; verify both paths produce valid output

- [x] 6.2 Update Makefile pipeline targets
  **Dependencies**: 1.2, 6.1
  **Files**: `Makefile`
  **Traces**: CI Integration and Baseline Diffing (MODIFIED), Three-Layer Analysis Architecture (MODIFIED)
  **Description**: Update `make architecture` to include Layer 1.5 enrichment step. Add `make architecture-enrichment` for standalone enrichment. Ensure `make architecture-validate` checks enrichment output when present.
  **Verify**: `make architecture` produces `treesitter_enrichment.json`, `comment_insights.json`, and `pattern_insights.json` when tree-sitter is available

- [x] 6.3 Update CI workflow for scripts dependencies
  **Dependencies**: 6.2
  **Files**: `.github/workflows/ci.yml`
  **Traces**: Scripts Dependency Management, CI Integration and Baseline Diffing (MODIFIED)
  **Description**: Add `uv sync` step for scripts directory in CI. Ensure architecture validation includes tree-sitter analyzer and enrichment pass.
  **Verify**: CI pipeline runs successfully with tree-sitter components

## 7. Documentation (After all implementation)

- [x] 7.1 Update CLAUDE.md and docs with scripts venv instructions
  **Dependencies**: 6.3
  **Files**: `CLAUDE.md`, `docs/architecture-artifacts.md`
  **Traces**: Scripts Dependency Management
  **Description**: Add scripts venv setup instructions to CLAUDE.md Python Environment section. Update architecture artifacts doc to mention tree-sitter enrichment outputs and pattern query library.
  **Verify**: Instructions are accurate and complete

## Parallel Execution Map

```
Group 1 (Foundation):     [1.1] → [1.2]
                            ↓
              ┌─────────────┼─────────────┐
Group 2       │  Group 3    │  Group 4    │
(SQL):        │  (Queries): │  (Enrich):  │
[2.1]→[2.2]   [3.1]─────┐  [4.1]────────┐
  → [2.3]     │          ├→ [4.2]        │
              │          ├→ [4.3]        │
              │          └→ [4.4]        │
              │             → [4.5]      │
              └─────────────┼────────────┘
                            ↓
Group 5 (Insights):     [5.1] ║ [5.2] → [5.3]
                            ↓
Group 6 (Integration):  [6.1] → [6.2] → [6.3]
                            ↓
Group 7 (Docs):         [7.1]
```

**Maximum parallel width**: 3 (Groups 2, 3, and 4 execute concurrently after foundation)
**Total tasks**: 18
**Critical path**: 1.1 → 4.1 → 4.2 → 4.5 → 5.1 → 5.3 → 6.1 → 6.2 → 6.3 → 7.1 (10 tasks)
