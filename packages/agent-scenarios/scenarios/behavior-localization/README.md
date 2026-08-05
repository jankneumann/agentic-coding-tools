# Behavior-localization benchmark

Measures whether the behavior handbook localizes change requests better, and
cheaper, than the raw architecture graph — the claim `add-behavior-handbook-layer`
rests on (design D7).

## Running

```bash
skills/.venv/bin/python packages/agent-scenarios/scenarios/behavior-localization/benchmark.py \
  --repo-root . --k 3 --json results.json
```

Requires a committed `docs/architecture-analysis/architecture.behaviors.json`
(`make architecture-handbook-synthesize`).

## Design

**Scenarios** are mined from `openspec/changes/archive/`:

- *request* — the `## Why` and `## What Changes` sections of `proposal.md`
- *ground truth* — `scope.write_allow` globs from `work-packages.yaml`, expanded
  to files that still exist at HEAD under `agent-coordinator/src/`

Changes whose targets no longer exist are **excluded and counted**, not silently
dropped: an archived change that predates a refactor is not evidence about
today's map. The excluded-reason histogram is printed with every run.

**Arms** (same request, same k):

| Arm | Method |
|---|---|
| `graph` | lexical ranking over canonical graph node names/ids/paths; top `k*12` nodes (a behavior unit is many nodes, so the baseline gets comparable width) |
| `handbook` | `handbook_query --locate`, then the member files of the top-k behavior units |

**Metrics** — file-level precision / recall / F1, plus the serialized token cost
of what each arm would place in a planner's context.

## Interpreting results

`f1_delta_pp > 0` with `token_delta_pct <= 0` is the adoption gate for expanding
the handbook beyond `agent-coordinator/src`.

A large negative `token_delta_pct` alongside a negative `f1_delta_pp` means the
handbook is returning *less*, not *better* — check cluster granularity before
concluding anything about the approach.

See `openspec/changes/add-behavior-handbook-layer/validation-report.md` for the
current baseline and its limitations.
