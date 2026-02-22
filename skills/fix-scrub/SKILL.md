---
name: fix-scrub
description: Remediate findings from bug-scrub report — auto-fixes, agent-assisted fixes, and quality verification
category: Git Workflow
tags: [quality, remediation, auto-fix, code-markers, deferred-issues]
triggers:
  - "fix scrub"
  - "run fix scrub"
  - "fix findings"
  - "remediate"
---

# Fix Scrub

Consume the bug-scrub report and apply fixes with clean separation from the diagnostic phase. Classifies findings into three tiers (auto/agent/manual), applies fixes, verifies quality, and commits.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--report <path>` (default: `docs/bug-scrub/bug-scrub-report.json`)
- `--tier <list>` (comma-separated; default: `auto,agent`; values: `auto`, `agent`, `manual`)
- `--severity <level>` (minimum severity; default: `medium`)
- `--dry-run` (plan fixes without applying)
- `--max-agent-fixes <N>` (default: 10)

## Prerequisites

- Bug-scrub report must exist (run `/bug-scrub` first)
- Python 3.11+
- ruff for auto-fixes

## Steps

### 1. Load Report and Classify

```bash
python3 skills/fix-scrub/scripts/main.py \
  --report <report-path> \
  --tier <tiers> \
  --severity <level> \
  --dry-run
```

Review the dry-run output before applying.

### 2. Apply Fixes

```bash
python3 skills/fix-scrub/scripts/main.py \
  --report <report-path> \
  --tier <tiers> \
  --severity <level> \
  --max-agent-fixes <N>
```

This will:
1. Apply auto-fixes (ruff --fix)
2. Generate agent-fix prompts to `docs/bug-scrub/agent-fix-prompts.json`
3. Track OpenSpec task completions

### 3. Dispatch Agent Fixes (if applicable)

If agent-fix prompts were generated, dispatch them as parallel Task() agents:

```python
import json
with open("docs/bug-scrub/agent-fix-prompts.json") as f:
    prompts = json.load(f)

# Launch parallel agents — one per file group
for entry in prompts:
    Task(
        subagent_type="general-purpose",
        description=f"Fix issues in {entry['file']}",
        prompt=entry["prompt"],
        run_in_background=True,
    )
```

Wait for all agents to complete, then verify.

### 4. Quality Verification

After all fixes (auto + agent) are applied, the orchestrator runs pytest, mypy, ruff, and openspec validate. If regressions are detected, review before committing.

### 5. Commit

```bash
git add .
git commit -m "$(cat <<'EOF'
fix(scrub): apply <N> fixes from bug-scrub report

Auto-fixes: <count> (ruff)
Agent-fixes: <count> (mypy, markers, deferred)
Manual-only: <count> (reported, not fixed)

Source report: <report-path>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

### 6. Review Summary

Check `docs/bug-scrub/fix-scrub-report.md` for the full summary including:
- Fixes applied by tier
- Files changed
- OpenSpec tasks marked as completed
- Quality check results
- Manual action items requiring human attention

## Fixability Tiers

| Tier | Criteria | Action |
|------|----------|--------|
| **auto** | ruff with fixable rules | `ruff check --fix` |
| **agent** | mypy type errors, markers with 10+ chars context, deferred items with proposed fix | Task() agent with file scope |
| **manual** | architecture, security, deferred without fix, markers with insufficient context | Reported only |

## Quality Checks

```bash
python3 -m pytest skills/fix-scrub/tests -q
```
