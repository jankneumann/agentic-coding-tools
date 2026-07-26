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

## Orchestration (ri-07)

`scripts/orchestrator.py` drives **all** configured producers into one durable
ri-06 operation per `(repository, revision)` and emits the manifest:

- `generate(...)` — reuse/create the canonical operation, run every configured
  producer, record each result **before** attempting the degradable semantic
  index (ri-02), finalize `succeeded`/`degraded`/`failed`, then write and record
  the manifest. A repeat run at the same revision reuses a `succeeded` operation
  verbatim (no re-attempt, no repository diff).
- `check(...)` — fully read-only drift assessment (no store or working-tree
  writes).

The semantic index is the one **degradable** producer: unavailable or errored →
a non-succeeded `SemanticIndexReference` with an `exact-search` fallback (never
fatal, deterministic output preserved). Architecture (ri-04) is collected via its
canonical owner; the manifest is written to the gitignored
`.git-context/context-refresh-manifest.json` so reruns never dirty the tree.

The proposal's `capability` producer has no canonical owner and is **not
configured** — tracked as an ri-07 follow-up (coordinator issue
`dced1d51`, candidate change `add-capability-context-producer`). Once such a
producer registers in `registry.py`, the orchestrator picks it up automatically.

## CLI

From the repository root, the Makefile wraps the registry and the orchestrator:

```bash
make context-refresh          # generate every producer's managed output (ri-05)
make context-refresh-check    # read-only per-producer drift check (0 fresh · 2 drift · 1 failed)
make refresh-project-context        # orchestrate all producers + emit the manifest (ri-07)
make refresh-project-context-check  # read-only orchestrated drift check (0/2/1)
```

The underlying entry point is `cli.py` in this skill's resolved `scripts/`
directory, with subcommands `list`, `generate <producer_id>`,
`check <producer_id>`, `generate-all`, `check-all`, `refresh [--producer ID]`,
and `refresh-check [--producer ID]`. Resolve the loaded skill directory first
rather than hardcoding an install path.

### Sync-point flags (ri-11)

`refresh` carries two opt-in flags for the main-convergence sync point. Both
default to **off**, so every existing invocation behaves exactly as before, and
`refresh-check` accepts neither — it writes nothing and never indexes.

| Flag | Default | Effect |
|---|---|---|
| `--sync-point` | off | Authorizes the mutation from the shared checkout, reaching the checkout policy's `approved_sync_point` branch. |
| `--defer-semantic-index` | off | Skips the inline index attempt and records the index as `pending` with an `exact-search` fallback. |

`--sync-point` is a **caller** decision and is never inferred from the
environment: an environment sniff would re-open shared-checkout writes for every
skill that happens to run on `main`, which is the property the guard exists to
protect. It authorizes the checkout classification only — the caller must still
enforce its own clean-tree and active-agent guards, and its own pre-push
compare-and-swap.

`--defer-semantic-index` exists because a sync point refreshes a revision that is
never main's final state: the convergence commit follows it, so an inline index
would be stale on arrival and a correct system would then index a second time.
The caller enqueues exactly one index for the final pushed revision instead.
Deferral only ever weakens the recorded claim — `pending` is not a currency
claim, so a deferred run **degrades** (exit 2) rather than reporting success, and
deterministic producer output is byte-identical to a non-deferred run.

```bash
# What the convergence driver runs, on main, after the merges have landed.
python scripts/cli.py refresh --sync-point --defer-semantic-index
```

`--revision` must name the revision that is **actually checked out**: every
producer reads the live working tree, so accepting another SHA would persist
artifacts under a revision they did not come from. Use a worktree at the target
revision instead.

## Configuration

All optional — with none of it set, `refresh` still runs every deterministic
producer and degrades the semantic index to `not-configured` with an
`exact-search` fallback.

| Variable | Purpose |
|----------|---------|
| `PROJECT_CONTEXT_REPO_ID` | Repository identity shared with `refresh-architecture`'s `provenance.repository_id`. Both must agree or one clone splits across two operation ids. |
| `POSTGRES_DSN` | Semantic-index database. Absent → indexing is unconfigured. |
| `PROJECT_CONTEXT_EMBEDDING_MODEL` | Embedding model id. Required to enable indexing. |
| `PROJECT_CONTEXT_EMBEDDING_DIMENSION` | Embedding dimension. Required to enable indexing. |
| `PROJECT_CONTEXT_EMBEDDING_PROVIDER` | `local` (default) or `openai_compatible`. |
| `PROJECT_CONTEXT_EMBEDDING_CREDENTIAL_REF` | Credential reference (`env:NAME` / `vault:path`) for a remote provider. |
| `PROJECT_CONTEXT_INDEX_TIMEOUT` | Seconds allowed for one indexing run (default `1800`). |

The embedding contract is complete-or-absent: a DSN without a model *and* a
dimension is treated as unconfigured rather than dispatched. Indexing runs the
`index_repo` console script from `packages/code-search` as a **subprocess** — it
pins `asyncpg<0.31` against the coordinator's `>=0.31`, so it cannot be imported
in-process. Every non-`ready` outcome degrades the refresh; it never fails it.

## What it owns / does not own

- Owns: producer registration, fail-closed invocation, generate/check protocol,
  the domain adapters, and (ri-07) cross-producer orchestration — driving every
  configured producer into one ri-06 operation and emitting the aggregate
  manifest.
- Does **not** own: the result/manifest/operation models or durable storage
  (ri-06 `project-context-runtime`); CI/merge drift gates (ri-10/ri-11); the
  architecture analysis (`refresh-architecture`, ri-04) or semantic indexing
  (ri-01…ri-03) themselves — orchestration collects their results but each
  remains owned and regenerated by its canonical owner.

## Tests

`skills/tests/project-context-refresh/` — run with
`skills/.venv/bin/python -m pytest skills/tests/project-context-refresh -q`.
