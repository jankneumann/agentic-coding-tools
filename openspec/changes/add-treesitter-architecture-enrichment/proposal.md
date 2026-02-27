# Change: add-treesitter-architecture-enrichment

## Why

The architecture analysis pipeline's SQL analyzer relies on regex-based parsing (`analyze_postgres.py`), which silently skips unrecognized SQL statements (PL/pgSQL bodies, complex ALTER chains, vendor extensions) and produces incomplete schema representations. Meanwhile, the Python and TypeScript analyzers (using `ast` and `ts-morph` respectively) lack access to comments, annotations, and cross-language pattern matching. Tree-sitter provides production-grade incremental parsers with a unified S-expression query language across 200+ grammars — it can replace the fragile regex SQL parser with a proper CST-based one, and enrich existing analyzers with capabilities that `ast` and `ts-morph` cannot provide (comment extraction, cross-language pattern queries, new language support without per-language AST walkers).

The scripts directory currently has zero external Python dependencies (all stdlib). This change introduces `tree-sitter` and grammar packages as the first managed dependency, requiring a `scripts/pyproject.toml` managed by `uv` — consistent with the project's existing Python environment conventions.

## What Changes

### Phase 1: Tree-sitter SQL Analyzer (replaces regex parser)
- Add `scripts/pyproject.toml` with `tree-sitter`, `tree-sitter-sql` dependencies, managed by `uv`
- Create `scripts/analyze_sql_treesitter.py` — CST-based SQL analyzer replacing regex parsing in `analyze_postgres.py`
- Parse `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, `CREATE FUNCTION` (including PL/pgSQL bodies), `CREATE TRIGGER` using tree-sitter SQL grammar
- Produce the same `postgres_analysis.json` schema for backward compatibility with Layer 2 consumers
- Graceful fallback: if tree-sitter is unavailable, fall back to existing regex analyzer with a warning
- Update `refresh_architecture.sh` and Makefile to use new analyzer when available

### Phase 2: Cross-Language Enrichment Layer
- Add `tree-sitter-python` and `tree-sitter-typescript` grammar packages
- Create `scripts/enrich_with_treesitter.py` — enrichment pass that runs after existing analyzers
- Create `scripts/treesitter_queries/` — configurable S-expression query library with per-language pattern files
- **Comment extraction** (Python + TypeScript): Extract inline comments, TODO/FIXME/HACK markers, and documentation blocks that Python's `ast` strips and the TypeScript analyzer doesn't capture
- **Python enrichment**: Exception handling patterns (bare `except:`, broad `except Exception`), context manager usage (`with` blocks for DB transactions/locks/files), type hint extraction (parameter types, return types that `analyze_python.py` currently ignores), assertion patterns in production code
- **TypeScript enrichment**: Error handling patterns (try/catch with empty catch blocks, untyped catch), dynamic `import()` expressions not captured by the static import graph, comment/TODO extraction
- **Security pattern queries**: SQL built via string concatenation/f-strings, hardcoded secrets patterns, `eval()`/`exec()` usage
- Output `treesitter_enrichment.json` consumed by new Layer 2 insight modules
- New insight module `scripts/insights/comment_linker.py` that maps comments/TODOs to architecture graph nodes
- New insight module `scripts/insights/pattern_reporter.py` that aggregates pattern query findings into `pattern_insights.json`

### Phase 3: Extended Grammar Support (future, not in initial scope)
- Add grammars for Bash, YAML, TOML, Dockerfile to analyze config files and scripts
- Incremental parsing integration for faster `make architecture-diff`
- Additional pattern queries for complexity estimation and concurrency hazard detection

## Impact

### Affected Specs

| Spec | Capability | Delta |
|------|-----------|-------|
| `codebase-analysis` | Database Schema Analysis | Replace regex SQL parsing with tree-sitter CST parsing |
| `codebase-analysis` | Three-Layer Analysis Architecture | Add tree-sitter as Layer 1 component + new Layer 2 enrichment module |
| `codebase-analysis` | Insight Module Interface | New `comment_linker.py` module following existing interface |
| `codebase-analysis` | CI Integration and Baseline Diffing | Update `make architecture` to include tree-sitter enrichment pass |
| `codebase-analysis` | Canonical Architecture Graph Schema | Extend node tags to include comment/annotation metadata |

### Affected Code

| File | Change |
|------|--------|
| `scripts/pyproject.toml` | **NEW** — dependency management for scripts (tree-sitter, tree-sitter-sql, tree-sitter-python, tree-sitter-typescript) |
| `scripts/analyze_sql_treesitter.py` | **NEW** — tree-sitter-based SQL analyzer |
| `scripts/enrich_with_treesitter.py` | **NEW** — cross-language enrichment pass (Python + TypeScript) |
| `scripts/treesitter_queries/` | **NEW** — configurable S-expression query library (python.scm, typescript.scm, security.scm) |
| `scripts/insights/comment_linker.py` | **NEW** — Layer 2 module mapping comments to graph nodes |
| `scripts/insights/pattern_reporter.py` | **NEW** — Layer 2 module aggregating pattern query findings |
| `scripts/refresh_architecture.sh` | Updated — integrate new analyzer and enrichment pass |
| `Makefile` | Updated — add tree-sitter setup target, update architecture pipeline |
| `scripts/analyze_postgres.py` | Retained as fallback — no modifications |
| `.github/workflows/ci.yml` | Updated — install tree-sitter deps for architecture validation |

### Architecture Layers
- **Execution layer**: New analyzer scripts and enrichment pass
- No changes to Coordination, Trust, or Governance layers

### Rollback Plan
- Tree-sitter is additive; existing `analyze_postgres.py` regex parser is retained as fallback
- Setting `TREESITTER_ENABLED=false` environment variable skips tree-sitter components
- Removing `scripts/pyproject.toml` and new scripts restores previous behavior
- Layer 2 consumers read the same `postgres_analysis.json` schema — no breaking interface changes

## Non-Goals

- **Not replacing** `ast`-based Python analyzer — `ast` is excellent for Python-specific analysis and has zero dependencies
- **Not replacing** `ts-morph`-based TypeScript analyzer — `ts-morph` provides type information tree-sitter cannot
- **Not adding** runtime tree-sitter to `agent-coordinator` — this is analysis tooling only
- **Not implementing** Phase 3 extended grammar support in initial scope
