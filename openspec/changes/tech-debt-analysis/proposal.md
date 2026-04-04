# Proposal: Tech Debt Analysis Skill

**Change ID**: `tech-debt-analysis`
**Status**: Implemented
**Author**: Claude Code
**Date**: 2026-04-04

## Why

Martin Fowler's Design Stamina Hypothesis observes that good design pays off by keeping development speed high over time. Without periodic assessment, design quality degrades silently — functions grow longer, modules accumulate responsibilities, duplication spreads, and coupling increases. By the time these problems become visible (through bugs, slow features, or integration failures), the remediation cost has multiplied.

The existing skill ecosystem has strong runtime diagnostics (`/bug-scrub`: test failures, lint errors, type errors) and structural analysis (`/refresh-architecture`: call graphs, cross-layer flows, parallel zones), but lacks a **design-quality diagnostic** that surfaces code smells, structural duplication, coupling metrics, and import complexity.

## What Changes

Add a structural tech-debt analysis skill that scans the codebase for design quality degradation using principles from Martin Fowler's *Refactoring* catalog, the *Design Stamina Hypothesis*, and the AWS Builders' Library. The skill produces actionable reports identifying code smells, complexity hotspots, coupling problems, and duplicated code.

This skill complements the existing `/bug-scrub` (runtime signals) and `/refresh-architecture` (structural graph) skills by providing a **design quality** layer that surfaces where development velocity is at risk due to accumulated tech debt.

### Integration with Existing Skills

- **Reads from** `/refresh-architecture` artifacts (architecture.graph.json, high_impact_nodes.json) for coupling analysis
- **Complements** `/bug-scrub` findings — together they provide a complete codebase health picture
- **Feeds into** `/plan-feature` for prioritizing refactoring work

### Goals

1. **Detect code smells** from Fowler's *Refactoring* catalog using AST-based analysis (Long Method, Large Class, Complex Function, Deep Nesting, Long Parameter List, Duplicated Code)
2. **Measure coupling** from architecture graph artifacts (fan-in, fan-out, hub nodes, blast radius)
3. **Identify import complexity** (circular dependencies, star imports, import fan-out)
4. **Detect code duplication** via structural fingerprinting
5. **Produce actionable reports** with hotspot files, severity breakdown, and refactoring recommendations grounded in Fowler's catalog

### Non-Goals

- Modifying any code (read-only diagnostic)
- Replacing existing linting tools (ruff, mypy) — these catch syntax/style issues, not design issues
- Full token-level clone detection (heavyweight; structural fingerprinting covers the most impactful cases)

## Design

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    main.py (orchestrator)                    │
│  Runs analyzers in parallel, aggregates, renders report     │
├─────────────┬──────────────┬──────────────┬─────────────────┤
│ complexity  │ duplication  │  coupling    │   imports       │
│ analyzer    │ analyzer     │  analyzer    │   analyzer      │
│ (AST-based) │ (fingerprint)│ (graph read) │  (AST-based)   │
└─────────────┴──────────────┴──────────────┴─────────────────┘
              │                      │
              ▼                      ▼
        Python source         architecture.graph.json
                              high_impact_nodes.json
```

### Analyzers

| Analyzer | Method | Code Smells Detected |
|----------|--------|---------------------|
| **complexity** | Python `ast` module | Long Method, Large File, Complex Function, Deep Nesting, Long Parameter List, Too Many Definitions |
| **duplication** | Structural fingerprinting (sliding window + MD5) | Duplicated Code (cross-file and same-file) |
| **coupling** | Read architecture graph JSON | High Fan-out (Shotgun Surgery), High Fan-in (Change Amplifier), Hub Nodes (God Object), High Impact (Blast Radius) |
| **imports** | Python `ast` module | Circular Imports, Import Fan-out, Star Imports |

### Thresholds

All thresholds follow a two-tier model:
- **Threshold** → medium severity (accumulating debt)
- **Critical** (2× threshold) → high severity (active pain point)

| Metric | Threshold | Critical |
|--------|-----------|----------|
| Function lines | 50 | 100 |
| File lines | 500 | 1000 |
| Cyclomatic complexity | 10 | 20 |
| Nesting depth | 4 | 6 |
| Parameter count | 5 | 8 |
| Top-level definitions | 20 | 40 |
| Fan-out edges | 10 | 20 |
| Fan-in edges | 10 | 20 |
| Hub (fan-in AND fan-out) | 8 each | - |
| Transitive dependents | 15 | 30 |
| Import fan-out | 15 | 25 |

### Report Output

- `docs/tech-debt/tech-debt-report.md` — human-readable with hotspots, severity tables, category breakdown with Fowler references
- `docs/tech-debt/tech-debt-report.json` — machine-readable for downstream tooling

## Implementation

### File Structure

```
skills/tech-debt-analysis/
├── SKILL.md                          # Skill definition (triggers, args, steps)
├── scripts/
│   ├── models.py                     # TechDebtFinding, AnalyzerResult, TechDebtReport
│   ├── analyze_complexity.py         # AST-based function/file complexity analyzer
│   ├── analyze_duplication.py        # Structural fingerprint duplication detector
│   ├── analyze_coupling.py           # Architecture graph coupling analyzer
│   ├── analyze_imports.py            # Import graph complexity analyzer
│   ├── aggregate.py                  # Finding aggregation and recommendation engine
│   ├── render_report.py              # Markdown and JSON report renderer
│   └── main.py                       # CLI orchestrator
└── tests/
    ├── test_models.py
    ├── test_analyze_complexity.py     # 22 tests
    ├── test_analyze_duplication.py    # 9 tests
    ├── test_analyze_coupling.py       # 9 tests
    ├── test_analyze_imports.py        # 13 tests
    ├── test_aggregate.py              # 5 tests
    └── test_render_report.py          # 12 tests
```

### Dependencies

- Python 3.11+ (stdlib only: `ast`, `hashlib`, `json`, `pathlib`, `concurrent.futures`)
- No external packages required
- Architecture artifacts (optional, for coupling analyzer)

## Testing

- **88 unit tests** covering all analyzers, models, aggregation, and rendering
- Smoke-tested against the full codebase (1,494 findings at medium+ severity)
- Consistent with existing skill test patterns (pytest, tmp_path fixtures, mocked externals)
