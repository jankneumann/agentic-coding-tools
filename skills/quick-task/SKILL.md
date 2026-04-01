---
name: quick-task
description: Delegate small ad-hoc tasks to any configured vendor without OpenSpec ceremony
category: Development
tags: [vendor, dispatch, quick, micro-task]
triggers:
  - "quick task"
  - "rescue"
  - "quick fix"
requires:
  coordinator:
    required: []
    safety: []
    enriching: []
---

# Quick Task

Delegate a small ad-hoc task (bug investigation, quick fix, code explanation, small refactor) directly to any configured vendor. Bypasses OpenSpec entirely — no change-id, no proposal, no worktree.

Inspired by the `/codex:rescue` command from [codex-plugin-cc](https://github.com/openai/codex-plugin-cc).

## Arguments

`$ARGUMENTS` - The task prompt to send to the vendor

Optional flags:
- `--vendor <name>` — Dispatch to a specific vendor (e.g., `codex`, `claude`, `gemini`). Default: first available.
- `--timeout <seconds>` — Override default timeout (default: 300s / 5 minutes)

## Prerequisites

- At least one vendor CLI installed and configured in `agents.yaml`
- Vendor must have a `quick` dispatch mode defined

## Steps

### 1. Parse Arguments

Extract the task prompt, optional `--vendor` flag, and optional `--timeout` flag from arguments.

### 2. Complexity Check

If the prompt exceeds 500 words OR references more than 5 file paths, emit a warning:

```
⚠ This task looks complex. Consider using /plan-feature for larger tasks.
Proceeding anyway...
```

The warning does NOT block execution.

### 3. Discover Available Vendors

```python
# Use the same discovery as review dispatch
from review_dispatcher import ReviewOrchestrator

orch = ReviewOrchestrator.from_coordinator() or ReviewOrchestrator.from_agents_yaml()
reviewers = orch.discover_reviewers(dispatch_mode="quick")
available = [r for r in reviewers if r.available]
```

If `--vendor` is specified, filter to matching vendor. If no vendors available, exit with error.

### 4. Dispatch Task

```python
results = orch.dispatch_and_wait(
    review_type="quick",
    dispatch_mode="quick",
    prompt=task_prompt,
    cwd=Path.cwd(),
    timeout_seconds=timeout,
)
```

### 5. Display Result

Print the vendor's raw stdout directly. Do NOT parse as JSON or structured findings.

If the vendor returned non-zero exit code, display error and stderr.

## Output

- Vendor stdout displayed inline (no files created)
- No OpenSpec artifacts created
- No git commits or worktree changes

## Design Notes

- Uses `quick` dispatch mode (read-write, no worktree isolation) — see Design Decision D3
- Returns freeform text, not structured JSON — see Design Decision D4
- This skill is intentionally minimal: prompt in → result out
