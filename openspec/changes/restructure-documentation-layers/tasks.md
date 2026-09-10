# Tasks — Restructure documentation into concept, mechanism, and reference layers

Sizes per plan-feature Task Sizing Reference. No XL tasks; one L-candidate (3.1) kept at M by confining it to README only. Spec scenario references use `<capability>.<requirement>` › scenario name.

Prerequisite (not a task here): `VISION.md` exists at repo root, produced by `/vision`.

## 1. Contracts (wp-contracts)

- [ ] 1.1 Write `contracts/README.md` recording that OpenAPI, database, event, and type-generation sub-types were evaluated and none apply to a documentation-only change. **Size**: XS
  **Files**: `openspec/changes/restructure-documentation-layers/contracts/README.md`
  **Dependencies**: None

## 2. Tests first (wp-tests)

- [ ] 2.1 Write the metadata parser and `test_doc_metadata_complete` in `skills/tests/docs/test_doc_structure.py`: every Layer 1 guide (`docs/guides/*.md`) and hand-written `docs/*.md` parses YAML frontmatter with `layer`, `owns`, `sources`, `verified_against`; `README.md` and `CLAUDE.md` parse the same fields from a leading `<!-- doc-meta ... -->` comment; every `sources` path exists. Generated files and per-run log directories are excluded by an explicit list. **Size**: S
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Document metadata is complete; › Document metadata is missing or malformed
  **Design decisions**: D4, D5
  **Files**: `skills/tests/docs/test_doc_structure.py`
  **Dependencies**: 1.1
- [ ] 2.2 Write `test_relative_links_resolve`: every relative markdown link (including `#anchor`-stripped targets) in `README.md`, `CLAUDE.md`, `docs/guides/*.md`, and hand-written `docs/*.md` resolves to an existing file. **Size**: S
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Newcomer reaches every guide in one click
  **Files**: `skills/tests/docs/test_doc_structure.py`
  **Dependencies**: 2.1
- [ ] 2.3 Write `test_skill_mentions_resolve`: every `` `/name` `` token in the same file set maps to `skills/<name>/SKILL.md`. **Size**: XS
  **Spec scenarios**: harness-engineering.Layered Documentation Map › README carries no inventory claims
  **Files**: `skills/tests/docs/test_doc_structure.py`
  **Dependencies**: 2.1
- [ ] Checkpoint: run `pytest skills/tests/docs -x` (expect RED on the new tests, GREEN on `test_workflow_docs.py`), review diff, verify scope is `skills/tests/docs/**` only
- [ ] 2.4 Write `test_newcomer_path` and `test_map_lists_every_doc`: every `layer: 1` doc is linked from `README.md` or from `docs/guides/documentation.md`, and links back to the map; every hand-authored `docs/**/*.md` outside the exclusion list is listed in the map. **Size**: S
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Newcomer reaches every guide in one click; › Hand-authored doc missing from the map
  **Files**: `skills/tests/docs/test_doc_structure.py`
  **Dependencies**: 2.1
- [ ] 2.5 Write `test_lessons_tagged`: every `- **` bullet in `docs/lessons-learned.md` has `status:` ∈ {active, superseded, retired} and `evidence:`; `superseded` bullets have `by:`; every `evidence:` path or `/skill` mention exists. **Size**: S
  **Spec scenarios**: skill-workflow.Documentation Update Per Iteration › Lesson cites a removed surface; › Lesson superseded by a later decision
  **Files**: `skills/tests/docs/test_doc_structure.py`
  **Dependencies**: 2.1
- [ ] 2.6 Write `test_readme_is_layer_zero` and `test_no_hand_maintained_catalogue`: `README.md` ≤ 80 lines, no `\d+ (skills|specs|specifications)` claim; `docs/skills-catalogue.md` does not exist (message points at the generated inventory). **Size**: XS
  **Spec scenarios**: harness-engineering.Layered Documentation Map › README carries no inventory claims; › Hand-maintained catalogue reintroduced
  **Files**: `skills/tests/docs/test_doc_structure.py`
  **Dependencies**: 2.1
- [ ] Checkpoint: `pytest skills/tests/docs --collect-only` collects all eight tests; commit as `test(docs): pin layered documentation structure (RED)`

## 3. Entry points and map (wp-entry-and-map)

- [ ] 3.1 Rewrite `README.md` to 60–80 lines: opening paragraph citing `VISION.md`, three roles in one paragraph each linking their guides, one lifecycle line linking `docs/skills-workflow.md`, Getting Started, "Go deeper" list linking every Layer 1 guide once and the map. Remove the project tree, specs table, and workflow diagram; replace count claims with a link to `docs/architecture-analysis/skills-inventory.md`. **Size**: M
  **Spec scenarios**: harness-engineering.Layered Documentation Map › README carries no inventory claims; › Newcomer reaches every guide in one click
  **Design decisions**: D1, D7
  **Files**: `README.md`
  **Dependencies**: 2.6
- [ ] 3.2 Add the `<!-- doc-meta -->` block to `README.md` and `CLAUDE.md`; repoint the CLAUDE.md Documentation section summary at the layered map wording. No other CLAUDE.md edits. **Size**: XS
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Document metadata is complete
  **Design decisions**: D4
  **Files**: `README.md`, `CLAUDE.md`
  **Dependencies**: 3.1
- [ ] 3.3 Rewrite `docs/guides/documentation.md` as the layered map: Layer 0 / Layer 1 / Layer 2 sections listing every hand-authored doc once, the project tree moved from README, and a "Document metadata" section defining the four fields. Add its own frontmatter. **Size**: S
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Hand-authored doc missing from the map
  **Files**: `docs/guides/documentation.md`
  **Dependencies**: 2.4
- [ ] Checkpoint: run `pytest skills/tests/docs -k "readme or metadata"`; review diff; verify scope
- [ ] 3.4 Delete `docs/skills-catalogue.md`; move its "Reading this catalogue" legend, removed-skills table, Frontends table, and shared-references note into `docs/architecture-analysis/skills-inventory.md` as prose **outside** the generated markers. Run `make context-refresh-check` and confirm `documentation.inventory` reports fresh. **Size**: S
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Hand-maintained catalogue reintroduced; › Inventory preface survives regeneration
  **Files**: `docs/skills-catalogue.md`, `docs/architecture-analysis/skills-inventory.md`
  **Dependencies**: 2.6
- [ ] 3.5 Repoint the remaining catalogue links in `docs/skill-flow/README.md` (2) and `docs/skills-workflow.md` (1) at the inventory. No other edits to `docs/skills-workflow.md`. **Size**: XS
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Newcomer reaches every guide in one click
  **Files**: `docs/skill-flow/README.md`, `docs/skills-workflow.md`
  **Dependencies**: 3.4
- [ ] Checkpoint: `pytest skills/tests/docs` and `make context-refresh-check`; commit

## 4. Layer 1 guides (wp-guides)

- [ ] 4.1 Write `docs/guides/coordinator.md`: why a coordinator, what it offers (locks, work queue, handoffs, memory, discovery, archetypes), truth-vs-projection, and the reasoning for local-first deployment behind a tunnel. Sources: `docs/agent-coordinator.md`, `docs/guides/work-queue-truth-projection.md`, `docs/decisions/agent-coordinator.md`. Frontmatter included; links to the map. **Size**: M
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Newcomer reaches every guide in one click
  **Design decisions**: D3
  **Files**: `docs/guides/coordinator.md`
  **Dependencies**: 2.4
- [ ] 4.2 Prune `docs/agent-coordinator.md`: remove the Phase 1–4 "Implementation Status" table and "Future Capabilities"; add a `## Design Principles` section (moved from the coordinator portion of `docs/skills-workflow.md` § Design Principles or written fresh) so `architecture.config.yaml` resolves; add frontmatter with `layer: 2`. **Size**: S
  **Design decisions**: D3
  **Files**: `docs/agent-coordinator.md`
  **Dependencies**: 4.1
- [ ] Checkpoint: `pytest skills/tests/docs -k "links or metadata"`; review diff; verify scope
- [ ] 4.3 Write `docs/guides/execution-environments.md` absorbing `docs/cloud-vs-local-execution.md` (detection signal, mutation policy, precedence, what changes under isolation, troubleshooting) plus a deploy-topology section linking the runbooks (`cloud-deployment.md`, `local-migration.md`, `cloud-session-hooks.md`, `cloudflare-setup.md`). Reduce `docs/cloud-vs-local-execution.md` to a stub pointing at the guide. **Size**: M
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Newcomer reaches every guide in one click
  **Design decisions**: D2
  **Files**: `docs/guides/execution-environments.md`, `docs/cloud-vs-local-execution.md`
  **Dependencies**: 2.4
- [ ] 4.4 Fold `docs/coordinator-railway-to-local-migration.md` into `docs/local-migration.md` and delete it; repoint the blockquote in `docs/cloud-deployment.md`. **Size**: S
  **Design decisions**: D2, D7
  **Files**: `docs/local-migration.md`, `docs/coordinator-railway-to-local-migration.md`, `docs/cloud-deployment.md`
  **Dependencies**: 4.3
- [ ] 4.5 Write `docs/guides/learning-loop.md`: session-log phase entries → `make decisions` timelines → episodic memory tags → `improve-harness` reports → `docs/lessons-learned.md`, with one link per stage owner. **Size**: S
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Newcomer reaches every guide in one click
  **Files**: `docs/guides/learning-loop.md`
  **Dependencies**: 2.4
- [ ] Checkpoint: `pytest skills/tests/docs -k "links or newcomer"`; review diff; verify scope
- [ ] 4.6 Add frontmatter to every existing `docs/guides/*.md` (except `documentation.md`) and to every hand-written `docs/*.md` not owned by another package, with `layer`, `owns`, `sources`, `verified_against`. **Size**: M
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Document metadata is complete
  **Design decisions**: D4
  **Files**: `docs/guides/*.md` (excluding `documentation.md`), `docs/*.md` (excluding `skills-catalogue.md`, `skills-workflow.md`, `lessons-learned.md`)
  **Dependencies**: 2.1
- [ ] 4.7 Correct false Beads and Railway claims in the files touched by 4.1–4.5 only (D7); leave runbook mentions to ri-02. **Size**: S
  **Design decisions**: D7
  **Files**: `docs/guides/coordinator.md`, `docs/guides/execution-environments.md`, `docs/agent-coordinator.md`, `docs/local-migration.md`
  **Dependencies**: 4.4
- [ ] Checkpoint: `pytest skills/tests/docs`; commit

## 5. Lessons corpus (wp-lessons)

- [ ] 5.1 Tag every bullet in `docs/lessons-learned.md` with `status:` and `evidence:`; `superseded` bullets get `by:`. Preserve the "Self-Healing at Milestone Boundaries" section and the "Mission" glossary entry verbatim apart from tags. **Size**: M
  **Spec scenarios**: skill-workflow.Documentation Update Per Iteration › Lesson superseded by a later decision; › Lesson cites a removed surface
  **Design decisions**: D6
  **Files**: `docs/lessons-learned.md`
  **Dependencies**: 2.5
- [ ] 5.2 Move `retired` bullets to `docs/archive/lessons-retired.md` with their `by:` pointers and the section they came from; add frontmatter (`layer: 1`) to `docs/lessons-learned.md`. **Size**: S
  **Design decisions**: D6
  **Files**: `docs/lessons-learned.md`, `docs/archive/lessons-retired.md`
  **Dependencies**: 5.1
- [ ] Checkpoint: `pytest skills/tests/docs -k lessons` and `grep -c "Self-Healing" docs/lessons-learned.md` ≥ 1; commit

## 6. Integration (wp-integration)

- [ ] 6.1 Merge the four package branches; run `pytest skills/tests/docs skills/tests/vision` and fix any path constants the restructure invalidated (none expected per D1). **Size**: S
  **Spec scenarios**: all scenarios in both deltas
  **Files**: `openspec/changes/restructure-documentation-layers/tasks.md`
  **Dependencies**: 3.5, 4.7, 5.2
- [ ] 6.2 Run `make context-refresh-check`, `make decisions` (expect no `git diff docs/decisions/`), and `openspec validate restructure-documentation-layers --strict`. **Size**: XS
  **Spec scenarios**: harness-engineering.Layered Documentation Map › Inventory preface survives regeneration
  **Files**: `openspec/changes/restructure-documentation-layers/tasks.md`
  **Dependencies**: 6.1
- [ ] 6.3 Tick every task checkbox and append the Implementation phase entry to `session-log.md`. **Size**: XS
  **Files**: `openspec/changes/restructure-documentation-layers/tasks.md`, `openspec/changes/restructure-documentation-layers/session-log.md`
  **Dependencies**: 6.2
