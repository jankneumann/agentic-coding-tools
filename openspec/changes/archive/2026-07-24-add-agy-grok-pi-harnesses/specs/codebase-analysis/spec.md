# codebase-analysis — delta for add-agy-grok-pi-harnesses

Drops `.gemini` from the analyzer skip-directory lists, since the repo-root `.gemini/` harness
config directory is removed by this change and no per-vendor runtime directories replace it
(proposal decision D2).

## MODIFIED Requirements

### Requirement: Complexity Analysis via AST

The system SHALL analyze Python source files using the `ast` standard library to detect structural code smells from Fowler's *Refactoring* catalog.

- The analyzer SHALL detect **Long Methods** — functions exceeding 50 lines (medium severity) or 100 lines (high severity)
- The analyzer SHALL detect **Large Files** — modules exceeding 500 lines (medium) or 1000 lines (high)
- The analyzer SHALL compute **McCabe cyclomatic complexity** for each function by counting decision points (if, for, while, except, with, assert, boolean operators, ternary expressions) with a base of 1
- The analyzer SHALL detect **Complex Functions** — cyclomatic complexity ≥ 10 (medium) or ≥ 20 (high)
- The analyzer SHALL measure **nesting depth** of control-flow statements (if, for, while, with, try, except) and detect depth ≥ 4 (medium) or ≥ 6 (high)
- The analyzer SHALL count function parameters excluding `self` and `cls`, detecting ≥ 5 (medium) or ≥ 8 (high)
- The analyzer SHALL count top-level definitions (classes + functions) per module, detecting ≥ 20 (medium) or ≥ 40 (high)
- The analyzer SHALL skip directories: `.venv`, `node_modules`, `__pycache__`, `.git`, `.tox`, `dist`, `build`, `.agents`, `.claude`, `.codex`
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
- The analyzer SHALL skip runtime skill copy directories (`.agents`, `.claude`, `.codex`)

#### Scenario: Detect cross-file duplication
- **WHEN** the same 6-line code block appears in `a.py` and `b.py`
- **THEN** the analyzer SHALL produce a finding with category `duplicate-code`, title containing "cross-file"

#### Scenario: Ignore trivial windows
- **WHEN** a 6-line window consists entirely of import statements
- **THEN** the analyzer SHALL NOT report it as a duplicate
