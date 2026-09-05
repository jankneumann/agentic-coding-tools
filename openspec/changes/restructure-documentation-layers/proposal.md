# Restructure documentation into concept, mechanism, and reference layers

> Parent proposal: [`docs/proposals/documentation-simplification.md`](../../../docs/proposals/documentation-simplification.md) (Phase A)
> Change ID: `restructure-documentation-layers`
> Effort: M
> Tier: coordinated
> Depends on: `VISION.md` existing at repo root (produced by `/vision` in a separate session before implementation starts)

## Why

A newcomer opening this repo today reads a 130-line README that mixes concept, mechanism, and inventory, then follows links into thirty-odd hand-written docs with no layering and no truth check. The generated side of documentation is already policed (the `documentation.inventory` producer and the `context-drift-gate` CI job byte-check every inventory), but nothing checks hand-authored prose, and the only rule that touches it (*Documentation Update Per Iteration* in `skill-workflow`) is append-only. Measured on this checkout:

- `docs/lessons-learned.md` cites `/parallel-implement`, which has no skill directory, and describes a Task() dispatch model the coordinator archetypes replaced.
- README states "≈55 skills" while the generated inventory lists 73. `docs/agent-coordinator.md` carries a Phase 1–4 status table and a "Future Capabilities" section that predate archetypes, the merge queue, and the task router.
- 112 mentions of Beads or Railway survive in `docs/*.md`, README, and CLAUDE.md outside the two migration runbooks.
- `architecture.config.yaml` points its `best_practices` loader at a "Design Principles" section of `docs/agent-coordinator.md` that does not exist; the section lives in `docs/skills-workflow.md`.
- `docs/skills-catalogue.md` is hand-maintained and says so; the generated `docs/architecture-analysis/skills-inventory.md` already carries the same data from filesystem truth.
- Every `docs/` file shares one last-commit date from a squash, so git age cannot signal staleness. Freshness must be content-based, the rule the producers already follow.

The discovery interview fixed the reader: a **human newcomer reading top-down** comes first; CLAUDE.md stays the agent contract and is only touched where the map changes. The `harness-engineering` spec (*Progressive Context Architecture*) already mandates the shape this change completes: CLAUDE.md as a ≤120-line table of contents over self-contained topic docs under `docs/guides/`.

## What Changes

### Layer 0: entry points
- **README.md** rewritten to one screen (60–80 lines): problem statement citing `VISION.md`, the three roles in one paragraph each, one lifecycle line, Getting Started, and a "Go deeper" list that links each Layer 1 guide once. The project tree, specs table, and workflow diagram move out (tree → `docs/guides/documentation.md`; specs table → link to `openspec/specs/`; diagram → `docs/skill-flow/README.md`, where it already lives). Count claims are replaced by links to the generated inventory.
- **CLAUDE.md** Documentation section repointed at the updated map. No other CLAUDE.md edits (it stays ≤120 lines and the `docs/guides/workflow.md` link asserted by `skills/tests/docs/test_workflow_docs.py` is preserved).

### Layer 1: one concept, one home (`docs/guides/`)
- **New `docs/guides/coordinator.md`** — why a coordinator exists, what it offers (locks, work queue, handoffs, memory, archetypes), truth-vs-projection, and the reasoning behind local-first deployment. Written from `docs/agent-coordinator.md`, `docs/guides/work-queue-truth-projection.md`, and `docs/decisions/agent-coordinator.md`. `docs/agent-coordinator.md` stays at its path as the architecture reference, pruned of the stale status and future-capabilities sections, and gains a `## Design Principles` section so the `architecture.config.yaml` loader resolves.
- **New `docs/guides/execution-environments.md`** — local vs cloud, isolation posture, the worktree short-circuit, and deploy topology, absorbing the prose of `docs/cloud-vs-local-execution.md`. That file becomes a short redirect stub at its existing path (it is linked from `openspec/project.md`, README, a worktree guide, and a work-package scope allowlist in `add-sandboxed-harness-execution`; the stub keeps every referrer valid). `docs/cloud-deployment.md`, `docs/local-migration.md`, and `docs/cloud-session-hooks.md` stay as runbooks at their paths (the `agent-coordinator` spec pins `docs/cloud-deployment.md`) and are linked from the guide. `docs/coordinator-railway-to-local-migration.md`, which has one referrer, is folded into `docs/local-migration.md` and removed.
- **New `docs/guides/learning-loop.md`** — session logs → decisions index → episodic memory → `improve-harness` → lessons. Short, links to the owners of each stage.
- **`docs/guides/documentation.md`** promoted to the single map: every hand-authored doc listed once under its layer, with the project tree from README. README and CLAUDE.md link to it; no other doc restates the index.
- **Lifecycle** keeps its current owner. `docs/skills-workflow.md` remains the Layer 1 lifecycle guide at its path (pinned by the `skill-workflow` spec, a content test, and 17 referrers); `docs/guides/workflow.md` remains the CLAUDE.md-facing summary. Merging these is deferred (see Out of scope).

### Lessons as a maintained corpus
- Every bullet in `docs/lessons-learned.md` gains inline `status: active|superseded|retired` and `evidence: <path or decision anchor>` tags. Bullets citing removed surfaces (Task() dispatch, `/parallel-implement`, Beads) are marked `superseded` with a `by:` pointer or moved to `docs/archive/lessons-retired.md`. The "Self-Healing at Milestone Boundaries" section and the "Mission" glossary entry landed by `factory-missions-architecture-alignment` are preserved verbatim under the new tagging (that change gates on them with a literal grep).

### Retire the hand-maintained catalogue
- **`docs/skills-catalogue.md` deleted.** Its "Reading this catalogue" preface (★/· legend, `related:` note, removed-skills table, Frontends, Shared references library) moves into `docs/architecture-analysis/skills-inventory.md` as hand-written prose **outside** the generated markers, which the producer preserves byte-for-byte. Six inbound links are repointed: `README.md` (2), `docs/guides/documentation.md`, `docs/skill-flow/README.md` (2), `docs/skills-workflow.md`.
- Coordination note, not an edit: `add-product-management-skills` has unchecked tasks that add rows to the catalogue. Once the catalogue is gone those rows appear in the inventory automatically when its skills land; that change's tasks should be re-pointed by its owner.

### Frontmatter contract (data now, checker later)
- Every Layer 1 guide and every hand-written `docs/*.md` gains YAML frontmatter: `layer`, `owns`, `sources`, `verified_against`. `README.md` and `CLAUDE.md` carry the same fields in an HTML comment (`<!-- doc-meta ... -->`) so GitHub does not render a metadata table above the project's front page.
- A parse-and-links test in `skills/tests/docs/` asserts the frontmatter parses, every relative link in Layer 0/1 docs resolves, every `/skill-name` mention resolves to `skills/<name>/SKILL.md`, every lessons bullet carries a status and evidence tag, and every Layer 1 guide is reachable from README in one click and links back to the map. The full claim ledger and the `/simplify-docs` skill are Phase B.

### **BREAKING** path removals and rollback
Two files are removed: `docs/skills-catalogue.md` and `docs/coordinator-railway-to-local-migration.md`. No spec, test, or non-markdown consumer names either. Rollback is `git revert` of the change's commits; no generated artifact changes shape (the producer version is untouched), so `make context-refresh` output is identical before and after.

### Affected architecture layers
Governance only (documentation and the `harness-engineering` / `skill-workflow` capability specs). No Execution, Coordination, or Trust code changes.

## Impact

| Capability | Delta file | Change |
|---|---|---|
| `harness-engineering` | `specs/harness-engineering/spec.md` | ADDED *Layered Documentation Map*: layers, single map, frontmatter fields, generated inventories replace hand catalogues |
| `skill-workflow` | `specs/skill-workflow/spec.md` | MODIFIED *Documentation Update Per Iteration*: lessons carry status and evidence tags; a lesson SHALL NOT cite a surface that no longer exists |

No delta to `agent-coordinator` (`docs/cloud-deployment.md` keeps its path), `project-context-refresh` (producer and block unchanged), or `codebase-analysis`.

Existing tests affected: `skills/tests/docs/test_workflow_docs.py` (unchanged paths, must stay green), `skills/tests/vision/test_localization.py` (`docs/guides` and `docs/decisions` remain).

## Approaches Considered

### Approach 1: Hand-authored restructure with a parse-and-links test — **Recommended**
Rewrite README and the guides by hand, add frontmatter by hand, tag lessons by hand, and pin the structure with one small test suite. No producer changes.

- **Pros**: no coupling to the producer version bump, CI `OUTPUT_PATHS` list, or a `project-context-refresh` spec delta; matches the interview decision "frontmatter now, checker later"; every conflicting change rebases onto plain prose edits; rollback is a revert.
- **Cons**: prose freshness still relies on the Phase B skill; the test checks links and tags, not design claims.
- **Effort**: M

### Approach 2: Generated-first restructure
Add a second `DocBlock` to the documentation producer for README's tree and specs table, make the map a generated block, and validate lesson tags inside the producer's `check` mode.

- **Pros**: drift in those blocks becomes CI-blocking on day one through the existing gate; no separate test.
- **Cons**: requires a producer version bump (restales every managed block), a CI `OUTPUT_PATHS` edit guarded by `test_remediation_policy.py`, hand-inserted markers in README, and a MODIFIED delta on `project-context-refresh`; pulls Phase B machinery into Phase A and blocks on `gate-drift-with-mirrors-hooks-and-blocking-ci`; a generated README tree is exactly the mechanism content Layer 0 should not carry.
- **Effort**: L

### Approach 3: Minimal drift fix
Fix the stale counts and dead references, repoint links, delete the catalogue, and stop. No new guides, no frontmatter, no lesson tags.

- **Pros**: S-sized; overlaps `reconcile-versions-and-stale-docs-to-one-truth` almost entirely and could be folded into it.
- **Cons**: does not produce the newcomer path the author asked for; leaves the coordinator and execution-environment rationale scattered across five docs; leaves lessons untriaged, so the Phase B skill has nothing to verify against.
- **Effort**: S

**Rationale for Approach 1**: it delivers the newcomer path (the stated outcome) at M effort, keeps this change decoupled from the producer and CI machinery that Phase B and ri-01 own, and its only breaking edits are two file deletions with no non-markdown consumers. Approach 2 buys blocking freshness for the wrong content (inventory tables the README should not carry) at the cost of coupling to three other changes. Approach 3 is a subset of ri-02 and does not meet the acceptance outcomes below.

### Selected Approach

**Approach 1, selected at Gate 1 (2026-09-05) without modification.** The latent-intent check confirmed the author's underlying goal (docs that stay in sync and feed implementation) is served by this change as the first step: it produces the structure and the tagged lesson corpus that the Phase B `/simplify-docs` skill verifies against. Approaches 2 and 3 are retained above only as the record of what was rejected and why.

## Success Criteria

Chosen in the discovery interview:

1. **Newcomer path**: from README, every Layer 1 guide is reachable in one click; every Layer 1 guide links to the map; no hand-authored doc under `docs/` or `docs/guides/` is unreachable from the map.
2. **Zero stale claims in scope**: every relative link, `/skill-name` mention, and `make` target named in README, CLAUDE.md, and the Layer 1 guides resolves; no count claims remain in README.
3. **Lessons fully tagged**: every bullet in `docs/lessons-learned.md` carries `status:` and `evidence:`; `superseded` bullets name `by:`; no bullet cites a nonexistent skill.
4. README is 60–80 lines and contains no mechanism prose (each term links to its guide within two sentences).
5. Existing gates stay green unchanged: `skills/tests/docs/test_workflow_docs.py`, `skills/tests/vision/test_localization.py`, `make context-refresh-check`, `make decisions`.

## Out of scope

- Merging `docs/skills-workflow.md`, `docs/guides/workflow.md`, and `docs/skill-flow/README.md` into one lifecycle guide (pinned by spec, test, and 17 referrers; separate change).
- Deleting or renaming `docs/cloud-deployment.md`, `docs/local-migration.md`, `docs/cloud-session-hooks.md`, or `docs/cloud-vs-local-execution.md` (stub only).
- The `/simplify-docs` skill, claim ledger, lessons-candidates producer, autopilot DOCS phase, weekly sweep, and `context-engineering` lesson injection (Phase B and C of the parent proposal).
- Any CLAUDE.md content beyond the Documentation section (`cut-competence-rules-relocate-policy` and `ambient-review-ledger` hold that file).
- Running `/vision`: it is an interactive prerequisite, not a task in this change.
