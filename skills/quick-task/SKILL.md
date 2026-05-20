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

Delegate a small ad-hoc task (bug investigation, code explanation, small
read-only review, or explicitly isolated quick fix) directly to any configured
vendor. Bypasses OpenSpec planning, but does not bypass the local CLI mutation
boundary.

Inspired by the `/codex:rescue` command from [codex-plugin-cc](https://github.com/openai/codex-plugin-cc).

## Arguments

`$ARGUMENTS` - The task prompt to send to the vendor

Optional flags:
- `--vendor <name>` — Dispatch to a specific vendor (e.g., `codex`, `claude`, `gemini`). Default: first available.
- `--timeout <seconds>` — Override default timeout (default: 300s / 5 minutes)
- `--write <slug>` — Allow file writes by first creating/entering a managed
  worktree named `quick-<slug>`. Without this flag, quick-task is read-only by
  default.

## Prerequisites

- At least one vendor CLI installed and configured in `agents.yaml`
- Vendor must have a `quick` dispatch mode defined

## Steps

### 1. Parse Arguments

Extract the task prompt, optional `--vendor`, `--timeout`, and `--write <slug>`
flags from arguments.

### 1.5. Enforce Read-Only or Isolated Write Mode

Quick-task is read-only by default in local CLI execution. In default mode, add
this instruction to the vendor prompt:

```
This quick task is read-only. Do not create, modify, delete, format, commit, or
push files. Return findings and suggested patches in text only.
```

If `--write <slug>` is supplied, enter a managed worktree before dispatch:

```bash
CHANGE_ID="quick-<slug>"
eval "$(python3 "<skill-base-dir>/../worktree/scripts/worktree.py" setup "$CHANGE_ID")"
cd "$WORKTREE_PATH"
skills/.venv/bin/python skills/shared/checkout_policy.py require-mutation
```

Write-mode quick tasks must push their branch and use PR review before any work
reaches main.

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

- Vendor stdout displayed inline.
- Default mode: no files created, no commits, no worktree changes.
- `--write` mode: changes occur only inside `quick-<slug>` worktree and branch.
- No OpenSpec artifacts created unless the prompt explicitly asks for planning,
  in which case use `/plan-feature` instead.

## Design Notes

- Default dispatch is read-only by default; write mode requires `worktree.py`
  setup and `checkout_policy.py require-mutation` before vendor execution.
- Returns freeform text, not structured JSON — see Design Decision D4
- This skill is intentionally minimal: prompt in → result out
