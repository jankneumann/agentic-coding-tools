# Tasks — add-visual-code-explainer

Sizes follow the plan-feature sizing table (XS ≤ 30 min · S ≤ 2 h · M ≤ 1 day). No L or XL tasks.
Within each phase, test tasks precede the implementation they verify (TDD RED → GREEN).

## Phase 1 — `codebase-atlas --tree` export (package `wp-atlas-tree`)

- [x] 1.1 Write `skills/tests/codebase-atlas/test_atlas_tree.py` against the `tiny_graph` fixture: callees tree ordering (name then id), callers with `--hops 1` and `(+n more)` suffix, `(cycle)` printed once, basename target roots at the module, unknown target exits `2`, ambiguous name exits `3` with sorted candidates on stderr, byte-identical output across two runs, footer percentages equal `Coverage.percent` with sorted languages and one-decimal shape, every printed node matches a fixture node by `(name, file)` (tree format emits name/file/kind, not ids), a mixed-edge fixture (a copy of `tiny_graph` plus one `import` edge) proving import edges never appear as callers or callees, default hops/direction, hops>4 clamp with stderr note, `--no-coverage` omits footer, unreadable `--graph` exits `1`, exact-id-before-name resolution precedence, unique-name resolve, `--direction both` labelled sections, and a `≤ 2 s` timing test on the committed graph (skipped when absent)
  **Spec scenarios**: codebase-analysis "Callees tree for a symbol", "Callers tree with hop cap", "Non-call edges are excluded", "Cycle is printed once", "File target gives the aggregated module view", "Unknown target exits 2", "Ambiguous target exits 3", "Deterministic output", "Coverage footer matches the page banner", "Default hops and direction", "Hops above four are clamped", "No-coverage suppresses the footer", "Input or IO error exits 1", "Coverage footer shape", "Target resolution precedence", "Unique name resolves", "Direction both labels sections"
  **Design decisions**: D3 (format), D4 (resolution), D7 (fixture-only nodes), D8 (module name)
  **Dependencies**: None
  **Size**: M

- [x] 1.2 Implement `skills/codebase-atlas/scripts/atlas_tree.py` — `resolve_target()`, `walk()` over `call`-typed `symbolEdges`, `format_tree()`, `footer()` — stdlib only, children sorted by name then id, hop clamp at 4 with stderr note
  **Spec scenarios**: as 1.1
  **Design decisions**: D3, D4, D8
  **Dependencies**: 1.1
  **Size**: M

- [x] 1.3 Wire `--tree`, `--hops`, `--direction` into `build_atlas.py` `parse_args()` and dispatch in `main()` after `build_view_model()` and before the render path, honouring `--no-coverage` and returning `0/1/2/3`
  **Spec scenarios**: codebase-analysis "Unknown target exits 2", "Ambiguous target exits 3", "Coverage footer matches the page banner"
  **Design decisions**: D3, D8
  **Dependencies**: 1.2
  **Size**: S

- [x] Checkpoint: run `skills/tests/codebase-atlas`, review diff, verify scope stays inside `skills/codebase-atlas/**` + `skills/tests/codebase-atlas/**`

- [x] 1.4 Add the `--tree` / `--hops` / `--direction` rows to the flag table in `skills/codebase-atlas/SKILL.md` with a two-line usage example (keep the file under 150 lines)
  **Spec scenarios**: codebase-analysis "Callees tree for a symbol"
  **Design decisions**: D3
  **Dependencies**: 1.3
  **Size**: XS

- [x] 1.5 Extend the flag tuple in `skills/tests/codebase-atlas/test_skill_md.py` with `--tree`, `--hops`, `--direction` so the SKILL.md ↔ CLI check covers them
  **Spec scenarios**: (test coverage of 1.4)
  **Design decisions**: —
  **Dependencies**: 1.4
  **Size**: XS

- [x] Checkpoint: run `skills/tests/codebase-atlas`, confirm the SKILL.md flag table and CLI agree, review the cumulative package diff

## Phase 2 — `explain-code` skill (package `wp-skill`, parallel with Phase 1)

- [x] 2.1 Write `skills/tests/explain-code/test_skill_md.py`: frontmatter parses; `name`, `description`, `category: Architecture`, `tags`, `user_invocable: true`, `related` including codebase-atlas and refresh-architecture present and non-empty (asserted explicitly, not via `assert_required_keys_present`); no `triggers` key; `assert_references_resolve`; `assert_related_resolve`; `assert_tail_block_present` (Common Rationalizations / Red Flags / Verification); `SKILL.md ≤ 150` lines; no reference file links to another reference; description mentions `codebase-atlas`
  **Spec scenarios**: skill-workflow "Frontmatter valid in both orderings", "Frontmatter omits triggers and sets Architecture category", "Skill markdown ends with required tail sections", "Description carries the trigger condition", "Progressive disclosure layout"
  **Design decisions**: D6
  **Dependencies**: None
  **Size**: S

- [x] 2.2 Write `skills/tests/explain-code/test_behaviour.py` — three deterministic behavioural checks: grounding reference contains both D5 disclosure forms, the closed ungrounded reason tokens (`graph stale`, `graph absent`, `graph check failed`, `symbol not in graph`, `form not graph-backed`), the footer→disclosure mapping (`;` after sha, copy after `· ` / before trailing ` covered`), non-call-tree source-read requirement, tree-tool-failure → `graph check failed`, and the clarification/redirect disclosure exemptions; `SKILL.md` redirects whole-repository questions to `/codebase-atlas`; `SKILL.md` forbids `--ensure` and the analysis pipeline
  **Spec scenarios**: skill-workflow "Disclosure line present on every sketching answer", "Whole-repository question redirected", "Whole-repository redirect has no disclosure line", "Stale or absent graph falls back to source", "Non-call-tree form is not graph-backed", "Tree tool failure after fresh check", "Ambiguous symbol asks instead of guessing"
  **Design decisions**: D2, D5, D7, D9
  **Dependencies**: None
  **Size**: S

- [x] 2.3 Write `skills/explain-code/SKILL.md` — frontmatter per D6 (no `triggers`), one-paragraph purpose crediting humanlayer's MIT `show-me`, the five rules, a catalogue table linking each `references/<form>.md`, the grounding step summary linking `references/grounding.md`, the deferred-scope note (no HTML, no files, no browser), and the tail block copied from `skills/references/skill-tail-template.md`
  **Spec scenarios**: skill-workflow "Narrow question answered with the smallest visual", "No file or browser side effects", "Progressive disclosure layout"
  **Design decisions**: D1, D6, D9
  **Dependencies**: 2.1, 2.2
  **Size**: M

- [x] Checkpoint: run `skills/tests/explain-code`, review diff, verify scope stays inside `skills/explain-code/**` + `skills/tests/explain-code/**`

- [x] 2.4 Write the five form references — `references/call-tree.md`, `component-tree.md`, `file-tree.md`, `sequence.md`, `structural-diff.md` — each with: when to use, the smallest-view rule for that form, one worked example adapted from humanlayer with attribution, and how to attach file locations
  **Spec scenarios**: skill-workflow "Narrow question answered with the smallest visual"
  **Design decisions**: D1
  **Dependencies**: 2.3
  **Size**: M

- [x] 2.5 Write `references/grounding.md` — the `--check` freshness command (D2: exit `0` only = fresh; non-zero ungrounded), the `--tree` invocation via `<skill-base-dir>/../codebase-atlas/`, how to map the footer coverage list into the `Grounding:` line (D5 substring rule), the closed ungrounded reason set with first-match order (`graph absent` → `graph check failed` → `graph stale` → `symbol not in graph` → `form not graph-backed`, including `--tree` spawn/unexpected-exit → `graph check failed`), non-call-tree source-read before sketching, the ask-don't-guess rule for an ambiguous name (exit `3`, no `Grounding:` line), the whole-repository redirect (no `Grounding:` line), and the refusal list (D9)
  **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Symbol outside graph coverage", "Non-call-tree form is not graph-backed", "Tree tool failure after fresh check", "Ambiguous symbol asks instead of guessing", "Whole-repository redirect has no disclosure line", "Disclosure line present on every sketching answer"
  **Design decisions**: D2, D5, D9
  **Dependencies**: 2.3
  **Size**: S

- [x] Checkpoint: run `skills/tests/explain-code`, confirm every `references/<form>.md` cited in SKILL.md exists, review diff

- [x] 2.6 Add `"explain-code": {"distribution": "portable"}` to `skills/install-manifest.json` `skills`, plus `cross_skill_dependencies` `"explain-code": ["codebase-atlas", "refresh-architecture"]`
  **Spec scenarios**: skill-workflow "Manifest validation passes", "Manifest declares portable distribution and atlas dependencies", "Sibling skill paths use skill-base-dir form"
  **Design decisions**: D1
  **Dependencies**: 2.5
  **Size**: XS

- [x] 2.7 Add `"tests/explain-code"` to `testpaths` in `skills/pyproject.toml`
  **Spec scenarios**: skill-workflow "Tests collected by the default sweep"
  **Design decisions**: —
  **Dependencies**: 2.1
  **Size**: XS

- [x] 2.8 (conditional) Author three scenario fixtures under `skills/tests/explain-code/scenarios/` in the trajectory-scenario harness format if that harness is present in the checkout; otherwise record "harness absent" in the session log
  **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Whole-repository question redirected"
  **Design decisions**: D7
  **Dependencies**: 2.5
  **Size**: S

- [x] Checkpoint: run `bash skills/install.sh --check` and `skills/.venv/bin/python -m pytest skills/tests/explain-code`, verify scope stayed inside the package's write_allow

## Phase 3 — Integration (package `wp-integration`)

- [ ] 3.1 Merge the `wp-atlas-tree` and `wp-skill` package branches into the feature branch, resolving any overlap in `skills/install-manifest.json`
  **Spec scenarios**: —
  **Design decisions**: —
  **Dependencies**: 1.5, 2.7, 2.8
  **Size**: XS

- [ ] 3.2 Regenerate the runtime mirrors with `bash skills/install.sh --mode rsync --deps none --python-tools none`
  **Spec scenarios**: skill-workflow "Manifest validation passes"
  **Design decisions**: —
  **Dependencies**: 3.1
  **Size**: XS

- [ ] 3.3 Record "Phase 0b shipped: `/explain-code` question-driven explainer" in `docs/proposals/codebase-visualization-tool.md` delivery status
  **Spec scenarios**: —
  **Design decisions**: —
  **Dependencies**: 3.2
  **Size**: XS

- [ ] 3.4 Run the full verification block from `design.md`: `pytest skills/tests/codebase-atlas skills/tests/explain-code skills/tests/install_sh`, `openspec validate add-visual-code-explainer --strict`, `bash skills/install.sh --check`, and the two-run `cmp` determinism check
  **Spec scenarios**: all
  **Design decisions**: all
  **Dependencies**: 3.3
  **Size**: S

- [ ] Checkpoint: review cumulative diff against `tasks.md`; every change maps to a task

- [ ] 3.5 Append the Implement phase record to `session-log.md` via `PhaseRecord.write_both()`
  **Spec scenarios**: —
  **Design decisions**: —
  **Dependencies**: 3.4
  **Size**: XS
