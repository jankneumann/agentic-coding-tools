---
name: all-shaped
description: Fixture whose every section is decidable by the pre-pass
category: Testing
tags: [fixture]
user_invocable: true
---

# All Shaped

Run `python3 "<skill-base-dir>/scripts/tool.py" <name>` to start.

## Arguments

| Flag | Meaning |
|---|---|
| `--all` | Audit every skill |
| `--output-dir <path>` | Where reports go |

## Run

```bash
python3 "<skill-base-dir>/scripts/tool.py" quick-task --output-dir /tmp/out
```

## Never Edit the Target

Never write under the audited skill directory because the audit is a
proposal, not an edit; the rightsizing changes own the rewrite.

## Steps

1. Parse the arguments.
2. Read the target SKILL.md.
3. Write the ledger.
4. Verify the exit code is 0.

## Exit codes

| Exit code | Meaning |
|---|---|
| 0 | ok |
| 1 | stale or input error |
