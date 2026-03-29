---
name: bug-scrub
description: Comprehensive project health diagnostic — collects signals from CI tools, existing reports, deferred issues, and code markers into a prioritized finding report
category: Git Workflow
tags: [quality, diagnostics, health-check, deferred-issues, code-markers]
triggers:
  - "bug scrub"
  - "run bug scrub"
  - "project health check"
  - "code health"
---

# Bug Scrub

Perform a comprehensive project health check by collecting signals from multiple sources, aggregating findings into a unified schema, and producing a prioritized report.

This is a **read-only diagnostic skill** — it does not modify any code. Use `/fix-scrub` to remediate findings.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--source <list>` (comma-separated sources; default: all available)
- `--severity <level>` (minimum severity: critical, high, medium, low, info; default: low)
- `--project-dir <path>` (directory with pyproject.toml; default: auto-detect)
- `--out-dir <path>` (default: `docs/bug-scrub`)
- `--format <md|json|both>` (default: both)

Valid sources: `pytest`, `ruff`, `mypy`, `openspec`, `architecture`, `security`, `deferred`, `markers`

## Script Location

Scripts live in `<agent-skills-dir>/bug-scrub/scripts/`. Each agent runtime substitutes `<agent-skills-dir>` with its config directory:
- **Claude**: `.claude/skills`
- **Codex**: `.codex/skills`
- **Gemini**: `.gemini/skills`

If scripts are missing, run `skills/install.sh` to sync them from the canonical `skills/` source.

## Prerequisites

- Python 3.11+
- Project tools installed (pytest, ruff, mypy — collectors skip unavailable tools)
- OpenSpec CLI for `openspec` source

## Steps

### 1. Run Orchestrator

```bash
python3 <agent-skills-dir>/bug-scrub/scripts/main.py \
  --source <sources-or-omit-for-all> \
  --severity <level> \
  --project-dir <path> \
  --out-dir docs/bug-scrub \
  --format both
```

### 2. Review Report

The orchestrator produces:
- `docs/bug-scrub/bug-scrub-report.md` — human-readable prioritized report
- `docs/bug-scrub/bug-scrub-report.json` — machine-readable for `/fix-scrub`

### 3. Interpret Results

**Signal Sources**:
- **pytest**: Test failures (severity: high)
- **ruff**: Lint violations (severity: high for errors, medium for warnings)
- **mypy**: Type errors (severity: medium)
- **openspec**: Spec validation issues (severity: medium)
- **architecture**: Diagnostics from architecture analysis (severity: mapped from report)
- **security**: Findings from security review report (severity: preserved from scanner)
- **deferred**: Uncompleted tasks and deferred findings from OpenSpec changes (severity: medium for active, low for archived)
- **markers**: TODO/FIXME/HACK/XXX in Python files (severity: medium for FIXME/HACK, low for TODO/XXX)

**Severity Levels** (descending): critical > high > medium > low > info

**Staleness Warnings**: Reports older than 7 days trigger a refresh recommendation.

### 4. Next Steps

- **Quick fixes**: Run `/fix-scrub --tier auto` for tool-native auto-fixes (ruff)
- **Guided fixes**: Run `/fix-scrub` for auto + agent-assisted fixes
- **Preview**: Run `/fix-scrub --dry-run` to see what would be fixed
- **Selective**: Run `/fix-scrub --severity high` for high-priority items only
- **Feature work**: Create a `/plan-feature` proposal for findings that need design decisions

## Quality Checks

```bash
python3 -m pytest <agent-skills-dir>/bug-scrub/tests -q
```
