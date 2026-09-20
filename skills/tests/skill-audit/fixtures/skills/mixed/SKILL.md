---
name: mixed
description: Fixture with four prose sections the pre-pass cannot decide
category: Testing
tags: [fixture]
user_invocable: true
---

# Mixed

## Run

```bash
python3 "<skill-base-dir>/scripts/tool.py" mixed
```

## Why

Skills drift out of fit with the models that run them. A recurring audit
notices the drift before a transcript shows the struggle.

## Philosophy

Prefer the simplest thing that works. Every rule should earn its place by
naming the failure it prevents.

## Background

Strong models derive scaffolding on their own; weak models omit steps when
the scaffolding is absent. One text cannot serve both.

## Notes

Reports are proposals. Nothing here rewrites a skill.

## Steps

1. Read the input.
2. Emit the report.
3. Confirm the exit code.
