# Integrate main context convergence

Roadmap item **ri-11** of `project-context-refresh-lifecycle`. Depends on ri-07
(`add-shared-context-refresh-orchestration`) and ri-10
(`add-deterministic-context-drift-gates`), both merged to `main`.

## Why

`merge-pull-requests` is the only skill that writes `main`. Every other skill in
this repository works inside a managed worktree and lands through a pull request.
That makes it the authoritative main-synchronization point — and today it does
nothing at all about derived context.

Every claim below was measured on the branch point `1cf51386`.

### 1. The merge sync point has no context step

```
$ grep -c "project-context-refresh\|context_refresh\|convergence\|context-drift-gate\|refresh-project-context" \
    skills/merge-pull-requests/SKILL.md skills/merge-pull-requests/scripts/*.py
skills/merge-pull-requests/SKILL.md:0
skills/merge-pull-requests/scripts/analyze_comments.py:0
skills/merge-pull-requests/scripts/auto_rebase.py:0
skills/merge-pull-requests/scripts/auto_rollback.py:0
skills/merge-pull-requests/scripts/check_staleness.py:0
skills/merge-pull-requests/scripts/discover_prs.py:0
skills/merge-pull-requests/scripts/_helpers.py:0
skills/merge-pull-requests/scripts/merge_backend.py:0
skills/merge-pull-requests/scripts/merge_events.py:0
skills/merge-pull-requests/scripts/merge_metrics.py:0
skills/merge-pull-requests/scripts/merge_pr.py:0
skills/merge-pull-requests/scripts/merge_watcher.py:0
skills/merge-pull-requests/scripts/post_merge_cleanup.py:0
skills/merge-pull-requests/scripts/post_merge_pipeline.py:0
skills/merge-pull-requests/scripts/vendor_review.py:0
```

Zero occurrences across the 756-line skill and all 14 helper scripts. The
post-merge pipeline that *does* exist (`SKILL.md:64-72`,
`scripts/post_merge_pipeline.py:21-94`) has exactly three hooks — merge metrics,
cascading rebase, and CI rollback monitoring. None of them touch derived context.

The consequence is measurable in the other direction: ri-10 shipped a **blocking**
`context-drift-gate` CI job (`.github/workflows/ci.yml:114`, `Makefile:471`) that
fails a pull request when committed managed output is stale. Nothing on the merge
path refreshes that output, so drift introduced by a merge is discovered by the
*next* unrelated pull request rather than by the merge that caused it.

### 2. The refresh command cannot run where the merge happens

`skills/project-context-refresh/scripts/cli.py:123` calls the shared checkout
guard without the sync-point escape:

```python
require_mutation_allowed(cwd=repository)
```

`skills/shared/checkout_policy.py:109-121` has an `approved_sync_point` branch,
reached only when the caller passes `sync_point=True`. Nothing passes it. Measured
from the shared checkout:

```
$ python3 skills/shared/checkout_policy.py require-mutation --json
{ "allowed": false, "reason": "shared_checkout_blocked", ... }
```

So `make refresh-project-context` (`Makefile:445`) is *refused* in the checkout
where `merge-pull-requests` operates. The orchestration capability and the sync
point are, today, mechanically unable to meet.

### 3. Cleanup runs the architecture target that does not write provenance

`skills/cleanup-feature/SKILL.md:251` runs `make architecture`. That is the full
generation target (`Makefile:138`). The staged target that writes provenance is
`make architecture-refresh` (`Makefile:147`), and
`skills/refresh-architecture/scripts/run_architecture.py:186` calls
`provenance.write_provenance` only from `run_staged` (lines 140-196).

ri-10's architecture producer decides freshness by comparing *committed*
provenance (`skills/project-context-refresh/scripts/orchestrator.py:212-334`), and
routes missing or malformed provenance to **drift**, not to `not-configured`. So
the current cleanup path can regenerate architecture artifacts and still leave the
gate red.

### 4. Nothing enqueues semantic indexing for the pushed main SHA

`orchestrator.generate` attempts the semantic index inline
(`orchestrator.py:699-708`), unconditionally, at the revision being refreshed.
There is no way to defer it. A refresh that runs *before* the convergence commit
therefore indexes a SHA that is not main's final state, and a refresh that runs
after it costs a second full index — `semantic_adapter.py:86` sets a 1800-second
ceiling on one indexing run.

## What Changes

1. **`merge-pull-requests` gains one convergence step** (new Step 11.6), placed
   after the existing post-merge OpenSpec cleanup approval (`SKILL.md:536-578`)
   and before the summary. It runs **once per invocation pass**, not once per PR.

2. **OpenSpec merge paths run `cleanup-feature --post-merge` first.** Ordering is
   made explicit and mandatory: task migration, `openspec archive`, spec-delta
   merge, and `make decisions` all mutate exactly the inputs the deterministic
   producers read, so a refresh that ran first would be stale on arrival.
   `cleanup-feature` keeps sole ownership of those operations — this change adds
   no archiving logic to `merge-pull-requests`.

3. **The refresh CLI learns the sync-point authorization** (`--sync-point`) and a
   **`--defer-semantic-index`** mode, so the deterministic half can run on `main`
   in the sync-point checkout and record the semantic index as `pending` for a
   later, separately enqueued attempt.

4. **`cleanup-feature`, when merge-driven, stages instead of committing**, and
   switches its architecture step to the staged, provenance-writing target. The
   merge sync point then produces **one** convergence commit containing the
   cleanup artifacts, the regenerated deterministic artifacts, and a tracked
   convergence record.

5. **Semantic indexing is enqueued for the final pushed SHA**, never awaited, and
   never a blocking dependency of the merge.

6. **A durable operation identity keyed on the merged main SHA** makes the whole
   sequence idempotent under retry: re-running the pass after a crash reuses the
   ri-06 operation record and refuses to produce a second convergence commit, a
   second archive, or a second index request.

## Impact

**Affected specs**

- `merge-pull-requests` — MODIFIED `OpenSpec Integration`; ADDED four convergence
  requirements.
- `project-context-refresh-orchestration` — MODIFIED `Sync-point-only main writes`
  to name the authorized sync-point checkout alongside the managed worktree.

**Affected code** (planning only; no implementation in this change)

- `skills/merge-pull-requests/SKILL.md` — new Step 11.6, summary and error-handling
  entries.
- `skills/merge-pull-requests/scripts/main_convergence.py` — new driver.
- `skills/cleanup-feature/SKILL.md` — merge-driven staging mode; staged
  architecture target.
- `skills/project-context-refresh/scripts/cli.py`,
  `skills/project-context-refresh/scripts/orchestrator.py` — sync-point flag,
  deferred semantic index.
- `openspec/contracts/project-context-refresh/schemas/` — new
  `context-convergence-record.schema.json` (promoted at cleanup).
- Tests at `skills/tests/merge-pull-requests/` and
  `skills/tests/project-context-refresh/`.

**Explicitly out of scope**

- Changing how PRs are discovered, reviewed, or merged.
- Moving archive, spec-delta merge, or task migration out of `cleanup-feature`.
- Making the semantic index a required dependency of a merge.
- Tracking `.git-context/` in version control (see design D9).
