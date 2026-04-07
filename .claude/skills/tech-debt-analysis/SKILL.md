---
name: tech-debt-analysis
description: Analyze codebase for structural tech debt using software design principles from Fowler's Refactoring, the Design Stamina Hypothesis, and the AWS Builders' Library
category: Architecture
tags: [tech-debt, refactoring, code-quality, complexity, coupling, duplication, design-stamina]
triggers:
  - "tech debt analysis"
  - "tech debt"
  - "analyze tech debt"
  - "code quality analysis"
  - "refactoring analysis"
  - "design stamina"
---

# Tech Debt Analysis

Perform a structural analysis of the codebase to identify tech debt — areas where design quality has degraded and future development velocity is at risk.

Grounded in principles from:
- **Martin Fowler's *Refactoring*** — code smell detection (Long Method, Large Class, Duplicated Code, Long Parameter List, etc.)
- **Design Stamina Hypothesis** — good design pays off by keeping development speed high over time
- **AWS Builders' Library** — minimize blast radius through loose coupling and clear module boundaries

This is a **read-only diagnostic skill** — it does not modify code. Use its output to prioritize refactoring work via `/plan-feature`.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--analyzer <list>` (comma-separated analyzers; default: all)
- `--severity <level>` (minimum severity: critical, high, medium, low, info; default: low)
- `--project-dir <path>` (directory to analyze; default: auto-detect)
- `--out-dir <path>` (default: `docs/tech-debt`)
- `--format <md|json|both>` (default: both)
- `--no-parallel` (run analyzers sequentially)

Valid analyzers: `complexity`, `coupling`, `duplication`, `imports`

## Script Location

Scripts live in `<agent-skills-dir>/tech-debt-analysis/scripts/`. Each agent runtime substitutes `<agent-skills-dir>` with its config directory:
- **Claude**: `.claude/skills`
- **Codex**: `.codex/skills`
- **Gemini**: `.gemini/skills`

If scripts are missing, run `skills/install.sh` to sync them from the canonical `skills/` source.

## Prerequisites

- Python 3.11+
- For the `coupling` analyzer: architecture artifacts must exist (`docs/architecture-analysis/architecture.graph.json`). Run `/refresh-architecture` first if missing.
- No external dependencies — uses only Python stdlib (`ast`, `hashlib`, `json`, `pathlib`)

## Analyzers

### 1. Complexity Analyzer (`complexity`)

Uses Python's `ast` module to detect:

| Code Smell | Metric | Threshold | Critical | Reference |
|------------|--------|-----------|----------|-----------|
| Long Method | Function line count | 50 | 100 | Fowler: Extract Method |
| Large File / God File | File line count | 500 | 1000 | Fowler: Extract Class |
| Complex Function | McCabe cyclomatic complexity | 10 | 20 | Fowler: Decompose Conditional |
| Deep Nesting | Control-flow nesting depth | 4 | 6 | Fowler: Guard Clauses |
| Long Parameter List | Parameter count (excl. self/cls) | 5 | 8 | Fowler: Introduce Parameter Object |
| Too Many Definitions | Top-level classes + functions | 20 | 40 | SRP: Single Responsibility Principle |

### 2. Coupling Analyzer (`coupling`)

Reads from existing architecture artifacts to detect:

| Code Smell | Metric | Threshold | Reference |
|------------|--------|-----------|-----------|
| High Fan-out | Outgoing dependencies | 10 | Shotgun Surgery / Feature Envy |
| High Fan-in | Incoming dependents | 10 | Change Amplifier |
| Hub Node | High fan-in AND fan-out | 8 each | God Object / Blob |
| High Impact | Transitive dependents | 15 | AWS: Blast Radius |

**Requires**: `docs/architecture-analysis/architecture.graph.json` (from `/refresh-architecture`)

### 3. Duplication Analyzer (`duplication`)

Uses structural fingerprinting to detect copy-pasted code:

- Normalizes source (strip comments, collapse whitespace, abstract literals)
- Extracts sliding windows of 6 consecutive normalized lines
- Groups by fingerprint hash to find exact structural duplicates
- Reports cross-file vs same-file duplication

### 4. Import Analyzer (`imports`)

Builds a module-level import graph to detect:

| Code Smell | Description | Reference |
|------------|-------------|-----------|
| Circular Import | Cycles in the import graph | Fragile initialization order |
| Import Fan-out | Module importing 15+ other modules | Divergent Change |
| Star Import | `from X import *` | Namespace Pollution |

## Steps

### 0. Ensure Fresh Architecture Artifacts

Before running the full analysis, ensure architecture artifacts are up to date for accurate coupling analysis:

```bash
# Check if architecture graph exists and is fresh (< 7 days old)
# If missing or stale, refresh it first:
make architecture
# Or invoke the skill:
# /refresh-architecture
```

The coupling analyzer automatically detects stale artifacts (> 7 days old) and warns in its output, but refreshing beforehand gives the most accurate results.

### 1. Run Orchestrator

```bash
python3 <agent-skills-dir>/tech-debt-analysis/scripts/main.py \
  --analyzer <analyzers-or-omit-for-all> \
  --severity <level> \
  --project-dir <path> \
  --out-dir docs/tech-debt \
  --format both
```

### 2. Review Report

The orchestrator produces:
- `docs/tech-debt/tech-debt-report.md` — human-readable report with hotspots, severity breakdown, and refactoring recommendations
- `docs/tech-debt/tech-debt-report.json` — machine-readable for downstream tools

### 3. Interpret Results

**Severity Levels** (descending): critical > high > medium > low > info

**Severity mapping**:
- Metric ≥ 2× threshold → **high** (active pain point)
- Metric ≥ threshold → **medium** (accumulating debt)
- Below threshold → not reported (unless severity filter is `info`)

**Hotspot files**: Files with the most findings across all analyzers. These are the best candidates for refactoring investment.

### 4. Next Steps

- **Quick wins**: Address high-severity Long Method and Complex Function findings — these directly impact bug rates
- **Structural**: Use hotspot files to plan Extract Class / Move Method refactorings
- **Coupling**: Hub nodes and high-impact nodes need stable interfaces before further feature work
- **Plan refactoring**: Create a `/plan-feature` proposal for significant refactoring efforts
- **Track over time**: Re-run periodically and compare JSON reports to measure design stamina

## Integration with Bug Scrub

This skill complements `/bug-scrub`:
- **Bug scrub** collects runtime signals (test failures, lint errors, type errors)
- **Tech debt analysis** collects structural signals (complexity, coupling, duplication)

Together, they provide a complete picture of codebase health. Run both before major planning sessions.

## Integration with Architecture Analysis

The `coupling` analyzer reads directly from `/refresh-architecture` artifacts. For best results:

1. Run `/refresh-architecture` to update the graph
2. Run `/tech-debt-analysis` to analyze structural quality
3. Review both reports together for a complete architectural assessment

## Quality Checks

```bash
python3 -m pytest <agent-skills-dir>/tech-debt-analysis/tests -q
```
