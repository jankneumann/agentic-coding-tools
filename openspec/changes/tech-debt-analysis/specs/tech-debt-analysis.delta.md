# tech-debt-analysis Delta Spec

**Change ID**: `tech-debt-analysis`
**Target Spec**: `codebase-analysis` (extends)

## Requirements

### Requirement: Complexity Analysis via AST

The system SHALL analyze Python source files using the `ast` standard library to detect structural code smells from Fowler's *Refactoring* catalog.

- The analyzer SHALL detect **Long Methods** — functions exceeding 50 lines (medium severity) or 100 lines (high severity)
- The analyzer SHALL detect **Large Files** — modules exceeding 500 lines (medium) or 1000 lines (high)
- The analyzer SHALL compute **McCabe cyclomatic complexity** for each function by counting decision points (if, for, while, except, with, assert, boolean operators, ternary expressions) with a base of 1
- The analyzer SHALL detect **Complex Functions** — cyclomatic complexity ≥ 10 (medium) or ≥ 20 (high)
- The analyzer SHALL measure **nesting depth** of control-flow statements (if, for, while, with, try, except) and detect depth ≥ 4 (medium) or ≥ 6 (high)
- The analyzer SHALL count function parameters excluding `self` and `cls`, detecting ≥ 5 (medium) or ≥ 8 (high)
- The analyzer SHALL count top-level definitions (classes + functions) per module, detecting ≥ 20 (medium) or ≥ 40 (high)
- The analyzer SHALL skip directories: `.venv`, `node_modules`, `__pycache__`, `.git`, `.tox`, `dist`, `build`, `.agents`, `.claude`, `.codex`, `.gemini`
- The analyzer SHALL gracefully skip files with `SyntaxError` without failing

#### Scenario: Detect a Long Method
- **WHEN** a Python file contains a function spanning 75 lines
- **THEN** the analyzer SHALL produce a finding with category `long-method`, severity `medium`, metric_value `75`, threshold `50`
- **AND** the finding SHALL include the smell name "Long Method" and recommendation "Extract Method"

#### Scenario: Detect high cyclomatic complexity
- **WHEN** a function contains 12 `if` branches
- **THEN** the analyzer SHALL compute complexity ≥ 12 and produce a finding with category `complex-function`

#### Scenario: Skip unparseable files
- **WHEN** a Python file contains a syntax error
- **THEN** the analyzer SHALL skip it and continue with remaining files
- **AND** the overall status SHALL remain `ok`

### Requirement: Structural Duplication Detection

The system SHALL detect duplicated code blocks using structural fingerprinting.

- The analyzer SHALL normalize source lines by stripping comments, replacing string and numeric literals with placeholders, and collapsing whitespace
- The analyzer SHALL extract sliding windows of 6 consecutive normalized lines from each file
- The analyzer SHALL hash each window using MD5 and group by hash to identify exact structural duplicates
- The analyzer SHALL distinguish **cross-file** vs **same-file** duplication in finding titles
- The analyzer SHALL filter out trivial windows (mostly imports, returns, closing brackets)
- The analyzer SHALL assign severity based on copy count: 2 copies → low, 3-4 copies → medium, 5+ copies → high
- The analyzer SHALL skip runtime skill copy directories (`.agents`, `.claude`, `.codex`, `.gemini`)

#### Scenario: Detect cross-file duplication
- **WHEN** the same 6-line code block appears in `a.py` and `b.py`
- **THEN** the analyzer SHALL produce a finding with category `duplicate-code`, title containing "cross-file"

#### Scenario: Ignore trivial windows
- **WHEN** a 6-line window consists entirely of import statements
- **THEN** the analyzer SHALL NOT report it as a duplicate

### Requirement: Coupling Analysis from Architecture Graph

The system SHALL analyze coupling metrics by reading pre-generated architecture artifacts.

- The analyzer SHALL read `docs/architecture-analysis/architecture.graph.json` to compute fan-in and fan-out for each node
- The analyzer SHALL detect **High Fan-out** (outgoing dependencies ≥ 10) as Shotgun Surgery / Feature Envy risk
- The analyzer SHALL detect **High Fan-in** (incoming dependents ≥ 10) as Change Amplifier risk
- The analyzer SHALL detect **Hub Nodes** (fan-in ≥ 8 AND fan-out ≥ 8) as God Object / Blob
- The analyzer SHALL optionally read `docs/architecture-analysis/high_impact_nodes.json` for transitive dependent counts, flagging nodes with ≥ 15 transitive dependents
- The analyzer SHALL check graph staleness (> 7 days old) and include a warning message recommending `/refresh-architecture`
- The analyzer SHALL return `status: skipped` when the architecture graph file does not exist

#### Scenario: Detect high fan-out node
- **WHEN** a node in the architecture graph has 11 outgoing edges
- **THEN** the analyzer SHALL produce a finding with category `high-coupling`, metric_name `fan_out`, metric_value `11`

#### Scenario: Skip when no graph
- **WHEN** `architecture.graph.json` does not exist
- **THEN** the analyzer SHALL return status `skipped` with a message recommending `/refresh-architecture`

#### Scenario: Warn on stale graph
- **WHEN** `architecture.graph.json` was last modified 10 days ago
- **THEN** the analyzer SHALL include a staleness warning in its messages

### Requirement: Import Graph Complexity Analysis

The system SHALL build a module-level import graph from Python source and detect import complexity issues.

- The analyzer SHALL extract `import` and `from ... import` statements using `ast`
- The analyzer SHALL detect **Circular Imports** — cycles in the internal import graph (between project modules), reported as medium (2-node cycle) or high (3+ node cycle)
- The analyzer SHALL detect **Import Fan-out** — modules importing ≥ 15 unique modules (medium) or ≥ 25 (high)
- The analyzer SHALL detect **Star Imports** — `from X import *` as medium severity (Namespace Pollution)
- The analyzer SHALL only count internal imports (modules that exist within the project) for fan-out and cycle detection
- The analyzer SHALL limit cycle detection depth to avoid combinatorial explosion (max depth 6)
- The analyzer SHALL report up to 10 cycles maximum

#### Scenario: Detect a circular import
- **WHEN** module `a` imports module `b` and module `b` imports module `a`
- **THEN** the analyzer SHALL produce a finding with category `import-complexity`, title containing "Circular import"

#### Scenario: Detect star import
- **WHEN** a module contains `from os.path import *`
- **THEN** the analyzer SHALL produce a finding with title containing "Star import"

### Requirement: Report Generation

The system SHALL produce both markdown and JSON reports from aggregated findings.

- The markdown report SHALL include: executive summary, severity breakdown table, category breakdown table with Fowler refactoring references, hotspot files table (top 10 by finding count), detailed critical/high findings with smell names and recommendations, medium findings in table format, low/info summary counts, analyzer performance table, and numbered recommendations
- The JSON report SHALL include the full finding list with all metadata, summary statistics (by severity, by category, by analyzer, hotspot files, total count), and analyzer results
- Reports SHALL be written to `docs/tech-debt/` by default
- The aggregator SHALL sort findings by severity (descending) then category priority (descending)
- The aggregator SHALL generate up to 7 recommendations based on finding patterns

#### Scenario: Generate complete report
- **WHEN** analyzers produce findings across multiple categories
- **THEN** the report SHALL contain sections for each severity level and a hotspot files table
- **AND** the recommendations SHALL prioritize high-severity findings first

### Requirement: CLI Orchestrator

The system SHALL provide a CLI entry point that coordinates all analyzers.

- The orchestrator SHALL accept `--analyzer` (comma-separated list, default: all), `--severity` (filter threshold), `--project-dir`, `--out-dir`, `--format`, `--no-parallel`, `--max-workers` arguments
- The orchestrator SHALL run analyzers in parallel by default using `ThreadPoolExecutor`
- The orchestrator SHALL auto-detect the project directory by walking up from cwd looking for `pyproject.toml`
- The orchestrator SHALL print per-analyzer status, finding counts, timing, hotspot files, and recommendations to stdout
- The orchestrator SHALL exit with code 0 for clean (no findings) or 1 for findings found

#### Scenario: Run all analyzers in parallel
- **WHEN** the orchestrator is invoked with no `--analyzer` flag
- **THEN** all four analyzers (complexity, coupling, duplication, imports) SHALL run concurrently
- **AND** per-analyzer results SHALL be printed as they complete
