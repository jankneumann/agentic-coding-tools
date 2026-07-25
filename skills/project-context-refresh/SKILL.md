---
name: project-context-refresh
description: "Deterministic generate/check producers for documentation, API contracts, decisions, and OpenSpec projections over the ri-06 ProducerResult contract"
category: Infrastructure
tags: [project-context, refresh, producers, deterministic, shared-library]
---

# Project Context Refresh

Shared registry of **deterministic context producers**. Each producer regenerates
one class of derived project context and, in `check` mode, reports precise drift
without touching the checkout — never using file modification times. Every
producer returns the canonical ri-06 `ProducerResult`
(`project-context-runtime`), so the refresh orchestrator (ri-07) records results
with no translation.

This is an infrastructure skill — not user-invocable. Add `scripts/` to
`sys.path` and import the bare module names, or drive it through `scripts/cli.py`.

## Producers

| Producer id | Canonical owner | Managed output |
|---|---|---|
| `documentation.inventory` | this skill (absorbs `add-update-documentation-skill`) | `docs/architecture-analysis/skills-inventory.md` |
| `api.contracts` | `openspec/contracts/` schemas | `docs/architecture-analysis/contracts-inventory.md` |
| `decisions.timeline` | `explore-feature/archive_index.py` (`make decisions`) | `docs/decisions/` |
| `openspec.projection` | `cleanup-feature` / `openspec archive` | `openspec/specs/` (projection only — never written) |

## Modes

- **`generate`** — write a producer's declared managed outputs (byte-stable for a
  fixed revision, inputs, and producer version).
- **`check`** — render in memory / a tempdir and byte-compare; never writes.
  Drift is reported as `degraded` with a failed validation, remediation, and a
  `custom` fallback stating no write occurred. A clean check is `fresh`.

`openspec.projection` is projection-only: canonical spec merges are sync-point
mutations owned by `cleanup-feature`, so both modes are read-only.

## CLI

From the repository root, the Makefile wraps the whole registry:

```bash
make context-refresh          # generate every producer's managed output
make context-refresh-check    # read-only drift check (exit 0 fresh · 2 drift · 1 failed)
```

The underlying entry point is `cli.py` in this skill's resolved `scripts/`
directory, with subcommands `list`, `generate <producer_id>`,
`check <producer_id>`, `generate-all`, and `check-all`. Resolve the loaded skill
directory first rather than hardcoding an install path.

## What it owns / does not own

- Owns: producer registration, fail-closed invocation, generate/check protocol,
  and the domain adapters.
- Does **not** own: the result/manifest/operation models or durable storage
  (ri-06 `project-context-runtime`); cross-producer orchestration and the
  aggregate manifest (ri-07); CI/merge drift gates (ri-10/ri-11); architecture
  (`refresh-architecture`, ri-04) or semantic indexing (ri-01…ri-03).

## Tests

`skills/tests/project-context-refresh/` — run with
`skills/.venv/bin/python -m pytest skills/tests/project-context-refresh -q`.
