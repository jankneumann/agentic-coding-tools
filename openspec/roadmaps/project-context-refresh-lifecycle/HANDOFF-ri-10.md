# Handoff — resuming at ri-10

Written 2026-07-26, immediately after ri-09 merged (PR #282).

## Do not trust `checkpoint.json`'s phase

It reads `current_item_id: ri-10`, `phase: implementing`. **ri-10 has not been planned.**
`openspec/changes/add-deterministic-context-drift-gates/` does not exist on `main` or on
any branch. `CheckpointManager.advance_to_next()` hardcodes `IMPLEMENTING` on advance, so a
freshly advanced item always claims planning is done.

Start ri-10 with `/plan-feature`, not `/implement-feature`. Same trap applied to ri-09.

(Note: `openspec/changes/gate-drift-with-mirrors-hooks-and-blocking-ci/` exists and sounds
similar — it is a **different**, unrelated change about install-asset mirror drift. Do not
mistake it for ri-10.)

## Roadmap state now matches merge state — as of 2026-07-26

| Item | roadmap.yaml | Actually on `main`? |
|---|---|---|
| ri-01 … ri-08 | completed | yes, merged |
| **ri-09** | completed | **yes — PR #282, merged 2026-07-26** |
| **ri-03** | completed | **yes — PR #290, merged 2026-07-26** |

**ri-03 was reconciled after this file was first written.** It had been marked `completed`
while sitting unmerged (32 commits, no PR). It is now genuinely on `main`, so **ri-12 is
unblocked**. Both ri-03 and ri-08 are archived (PR #291), and ri-03's
`contracts/openapi/v2.yaml` was promoted to `openspec/contracts/code-search/`.

Two things that merge surfaced, worth knowing before touching code-search:

- The ri-03 branch's headline diff (52k insertions) was a three-dot artefact spanning
  ri-01/ri-02 work already on `main`. Its real delta was ~4 files / 3.3k lines.
- It fixed a genuine unsatisfiable pin: `agent-coordinator` needs `asyncpg>=0.31.0` while
  `packages/code-search` had capped at `<0.31`. Now `<1`.

Ready items are therefore **ri-10** and **ri-12**, by priority ri-10 first.

## What ri-10 inherits from ri-09

Read `openspec/changes/add-branch-local-context-checkpoints/design.md` first — three items
are addressed to ri-10 directly:

1. **D3 was corrected mid-implementation.** Check-mode read-only-ness is *not* guaranteed
   by `registry.run_producer`; it holds because the four landed adapters respect it. ri-10
   must **assert** read-only-ness, not inherit the claim.
2. **ri-09 is deliberately report-only** (D8). Drift exits 0 and is recorded as data. ri-10
   owns turning it into a CI/merge failure, and consumes
   `openspec/changes/<id>/context-checkpoints/<package-id>.json`
   (contract: `openspec/contracts/project-context-refresh/schemas/context-checkpoint.schema.json`).
3. **Open question ri-09 left for ri-10/ri-11:** no GC or retention exists for per-package
   semantic index namespaces.

## Two gates that bit ri-09 and will bit ri-10

Neither is reachable by running pytest on the suites a change touches:

- `bash install.sh --check` — fails on an **undeclared cross-skill dependency**. Adding a
  reference to another skill in a `SKILL.md` requires an entry in
  `skills/install-manifest.json` under `cross_skill_dependencies`.
- `validate-decision-index` — `docs/decisions/` is derived. Capability-tagging a
  `Decision(...)` in a session log obliges you to run `make decisions` and commit. This
  fires on **active** changes, not only at archive time.

Also new since ri-09: `skills/` is now **ruff-gated** in CI (PR #283), with an explicit
rule set in `skills/pyproject.toml`. Run `uv run ruff check .` from `skills/` before pushing.

## Worktree note

This roadmap worktree is ~66 commits behind `main` and carries stale untracked paths. It is
meta-only — nothing on `main` touches `openspec/roadmaps/` — so bookkeeping commits are
safe without syncing. Rebasing needs those untracked paths cleared first.
