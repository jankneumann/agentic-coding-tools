# Design — Restructure documentation into concept, mechanism, and reference layers

Cross-cutting by nature (touches Layer 0 entry points, five guides, the lessons corpus, a generated artifact's prose, and one test suite), so the decisions that constrain implementation are recorded here. Each decision lists the alternative considered.

## D1. Keep every spec-pinned or test-pinned path; add new guides beside them

`docs/skills-workflow.md` (pinned by `skill-workflow` › *Workflow Documentation Updates* and by `skills/tests/docs/test_workflow_docs.py`), `docs/guides/workflow.md` (asserted by the same test and linked from CLAUDE.md), and `docs/cloud-deployment.md` (pinned by `agent-coordinator` › *Cloud Deployment Guide*) keep their paths and their pinned content. New Layer 1 guides (`coordinator.md`, `execution-environments.md`, `learning-loop.md`) are created beside them rather than by renaming.

- **Alternative**: rename into a uniform `docs/guides/<concept>.md` set with spec deltas for each pin. Rejected: three extra spec deltas, a test rewrite, and 17 referrer edits for no reader-visible gain; the map makes the layer explicit regardless of filename.
- **Consequence**: the lifecycle concept is owned by `docs/skills-workflow.md` with `docs/guides/workflow.md` as its CLAUDE.md-facing summary. Both declare this in `owns`/`sources` so the Phase B duplicate check treats the pair as intentional.

## D2. Strangler stub for `docs/cloud-vs-local-execution.md`; delete only unreferenced files

`docs/cloud-vs-local-execution.md` is linked from `openspec/project.md` (agent-loaded context), README, `docs/guides/worktree-management.md`, and sits in a work-package `write_allow` allowlist of `add-sandboxed-harness-execution`. Its prose moves into `docs/guides/execution-environments.md`; the old path becomes a five-line stub that says where the content went. The two files this change deletes (`docs/skills-catalogue.md`, `docs/coordinator-railway-to-local-migration.md`) have no spec, test, config, or allowlist referrer.

- **Alternative**: delete and repoint all referrers. Rejected: editing another active change's `work-packages.yaml` allowlist is outside this change's scope, and `openspec/project.md` is loaded every session so a dangling link there costs every agent.
- **Rollback**: `git revert`; the stub and the deletions are the only path changes.

## D3. Coordinator concept vs coordinator reference are two documents with distinct `owns`

`docs/guides/coordinator.md` owns the *concept*: why a coordinator, what it offers, truth-vs-projection, why local-first deployment. `docs/agent-coordinator.md` stays as the *architecture reference* (capabilities, MCP tools, extensions), pruned of the Phase 1–4 status table and the "Future Capabilities" section, and gains a `## Design Principles` section so the `architecture.config.yaml` `best_practices` loader, which already names that section, resolves.

- **Alternative**: merge both into one guide. Rejected: the reference half is long, changes with every coordinator feature, and is the wrong reading level for Layer 1; the config loader would need a repoint.

## D4. Document metadata: YAML frontmatter for Layer 1, HTML comment for Layer 0

Fields: `layer` (0, 1, or 2), `owns` (list of concept slugs), `sources` (repository paths, spec capabilities, or skill names the document describes), `verified_against` (short commit SHA at which the claims were last checked). Layer 1 guides and hand-written `docs/*.md` use YAML frontmatter, which GitHub renders as a small table and which the existing SKILL.md parsers already handle. `README.md` and `CLAUDE.md` carry the same fields in a leading `<!-- doc-meta ... -->` comment: a rendered metadata table above the project's front page is noise, and CLAUDE.md is agent context where a comment costs fewer tokens than a table.

- **Alternative**: frontmatter everywhere. Rejected for the README rendering reason above.
- **Alternative**: defer metadata to Phase B. Rejected at the discovery interview: Phase B needs the data on day one.
- **Parser**: the test suite carries its own ~20-line parser (frontmatter or `doc-meta` comment → dict). Phase B lifts it into the `/simplify-docs` scripts; nothing in `skills/` depends on it yet.

## D5. One test module, no CI wiring changes

`skills/tests/docs/test_doc_structure.py` is collected by the existing `tests/docs` entry in `.github/workflows/ci.yml`. It checks: metadata parses; relative links in Layer 0/1 docs resolve; `/skill-name` mentions resolve; every Layer 1 guide is reachable from README in one click and links to the map; every hand-authored doc under `docs/` is listed in the map; README is ≤ 80 lines with no count claims; every lessons bullet is tagged; no `docs/skills-catalogue.md` exists. It does **not** check design claims (Phase B) and does not touch the producer, `OUTPUT_PATHS`, or `context-drift-gate`.

- **Alternative**: a second `DocBlock` in the documentation producer (Approach 2). Rejected at Gate 1.

## D6. Lessons: tag in place, retire by moving, never delete silently

Each of the 69 bullets in `docs/lessons-learned.md` gets `status:` and `evidence:`. A bullet whose surface is gone (Task() dispatch model, `/parallel-implement`, Beads) is tagged `superseded` with `by:` when a replacing decision or change exists, otherwise `retired`; retired bullets move to `docs/archive/lessons-retired.md` in this change. The "Self-Healing at Milestone Boundaries" section and the "Mission" glossary entry are preserved verbatim under tagging because `factory-missions-architecture-alignment` gates on them with a literal grep.

- **Alternative**: rewrite the lessons file from scratch. Rejected: Chesterton's Fence; the tags make the retirement auditable and the Phase B skill can re-verify each `evidence:` pointer.

## D7. Stale-mention sweep is scoped to files this change already rewrites

Beads and Railway mentions are corrected only in the documents this change creates or restructures (README, the new guides, `docs/agent-coordinator.md`, `docs/local-migration.md`, the lessons file). The 60-odd mentions in `docs/cloud-deployment.md`, `docs/cloudflare-setup.md`, and `docs/cross-repo-setup.md` are runbook content that `reconcile-versions-and-stale-docs-to-one-truth` (ri-02, approved) and the Phase B sweep own.

- **Alternative**: sweep every doc now. Rejected: widens the diff into five files other changes claim, for claims the newcomer path never reaches.

## D8. Package decomposition and scope

Four writing packages after the contracts stub, three of them parallel:

| Package | Owns | Why separate |
|---|---|---|
| `wp-tests` | `skills/tests/docs/**` | Tests first (RED); every other package turns them green |
| `wp-entry-and-map` | `README.md`, `CLAUDE.md`, `docs/guides/documentation.md`, `docs/skills-catalogue.md` (delete), `docs/architecture-analysis/skills-inventory.md` (prose only), `docs/skill-flow/README.md`, `docs/skills-workflow.md` (one link) | Layer 0 and the map; the catalogue retirement lives here because README and the map are its referrers |
| `wp-guides` | `docs/guides/**` except the map, `docs/*.md` except the three files other packages own | Layer 1 content and frontmatter |
| `wp-lessons` | `docs/lessons-learned.md`, `docs/archive/lessons-retired.md` | Independent corpus; conflicts with `factory-missions` are confined here |
| `wp-integration` | `openspec/changes/restructure-documentation-layers/**` | Runs the full suite and the producer check after merge |

`wp-guides` lists its files explicitly rather than using `docs/guides/**` and `docs/*.md` globs: the parallel-zone scope checker compares `write_allow` globs pairwise and does not honour `deny`, so the map and the three `docs/*.md` files other packages own are simply absent from its list. No two parallel packages share a writable path.

## Sequence

```
wp-contracts ─► wp-tests ─┬─► wp-entry-and-map ─┐
                          ├─► wp-guides ────────┼─► wp-integration
                          └─► wp-lessons ───────┘
```

Prerequisite outside the change: `VISION.md` exists at repo root (from `/vision`). `wp-entry-and-map` links to it; the link test fails if it is absent, which is the intended signal.
