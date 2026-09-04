# Change: add-visual-code-explainer

## Why

Nothing in the skill set answers a narrow question about the code — "how does a
message get from the bridge to the coordinator?", "what calls `acquire_lock`?" —
with a small picture. `/codebase-atlas` renders the whole repository into one
interactive page and `/refresh-architecture` emits Mermaid views at fixed zoom
levels; both are artifact-first and deterministic, and neither is shaped for a
conversational question. The atlas even lists "show me the architecture" as a
trigger, so a narrow question today either gets a wall of prose or a 650 KB page.

humanlayer's MIT-licensed `show-me` skill
([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md))
demonstrates the missing posture in about forty lines of prompt: a catalogue of
small visual forms (indented call tree, component tree with file paths, file tree
with one-line responsibility comments, Mermaid sequence diagram, structural diff,
one focused HTML file) plus five discipline rules — skip the preamble, keep prose
brief, pick the smallest view that makes the key point, keep only the calls and
boundaries the current question needs, place each visual next to the text it
supports. Its weakness is the opposite of ours: it trusts the model's memory of
the code, so a confidently wrong call tree looks identical to a right one.

This change adopts the catalogue and the brevity rules as a new prompt-only skill,
and improves on the source in the one way this repository is positioned to: the
sketch is **grounded** in `docs/architecture-analysis/architecture.graph.json`
when the graph is fresh, via a new text export from the atlas, and **discloses its
own coverage** on every answer — satisfying the standing codeviz principle that "a
visualisation must disclose its own coverage" (see
`docs/proposals/codebase-visualization-tool.md`). Why now: the atlas shipped as
Phase 0a of that proposal and its remaining phases are usage-gated; a
question-driven entry point is the cheapest way to generate the usage evidence
that gates them, and the analysis that motivated this change is fresh.

## What Changes

- **New skill `skills/explain-code/`** (prompt-only, `user_invocable: true`,
  `category: Architecture`). A thin `SKILL.md` index routing to one
  `references/<form>.md` per visual form: `call-tree.md`, `component-tree.md`,
  `file-tree.md`, `sequence.md`, `structural-diff.md`. Each reference carries the
  worked example adapted from humanlayer (with attribution) and the form's
  "smallest view" rule. **HTML output is explicitly out of scope for v1** — the
  skill emits text and Mermaid only, inline in the reply.
- **Grounding step.** Before sketching, the skill checks graph freshness with
  the existing read-only `run_architecture.py --check` (exit `0` is fresh;
  anything else is treated as stale) and, when fresh,
  obtains callers/callees from the new atlas `--tree` export and builds the call
  tree from that data. When the graph is stale, absent, or does not cover the
  files in question, the skill reads source directly and **labels the sketch
  unverified**. It never refuses and never triggers a refresh on its own.
- **Coverage disclosure line.** Every answer ends with one line stating the
  grounding source (`graph @ <sha>`, or `source read, unverified`) and, for
  grounded sketches, the per-language coverage percentage the atlas already
  computes. The line is not optional and not collapsible.
- **`codebase-atlas` gains `--tree <symbol-or-file> [--hops N] [--direction in|out|both]`.**
  A stdlib-only text export in `build_atlas.py` that BFS-walks the existing
  `symbolEdges` adjacency from `build_view_model()` and prints an indented tree
  with file path and line per node, hop-capped at 4 to match the page's slider.
  Output is byte-stable for a fixed graph. Exit codes follow the existing
  contract (`0` ok, `1` input error, `2` symbol not found).
- **Frontmatter written for the post-`rewrite-skill-frontmatter` world.** The new
  `SKILL.md` carries `name, description, category, tags, user_invocable, related`
  with a description that states capability and trigger condition in third
  person, and **omits `triggers:`**. This change declares a dependency on
  `rewrite-skill-frontmatter`; until that lands, the skill's own test asserts the
  four surviving keys explicitly instead of calling the shared
  `assert_required_keys_present` (which still requires `triggers`).
- **Distribution wiring.** `skills/install-manifest.json` gains
  `"explain-code": {"distribution": "portable"}` and a `cross_skill_dependencies`
  entry `"explain-code": ["codebase-atlas", "refresh-architecture"]` (the validator rejects undeclared
  `<skill-base-dir>/../` references). `skills/pyproject.toml` `testpaths` gains
  `"tests/explain-code"`. Runtime mirrors regenerate via `skills/install.sh`.
- **Tests.** `skills/tests/explain-code/test_skill_md.py` (frontmatter parses,
  explicit key presence, references resolve, related resolve, tail block
  present) plus **three behavioural scenarios** in the replay-harness shape that
  `invert-skill-test-suite-to-behavioural` prescribes: (1) a grounded question
  yields a call tree whose nodes all exist in the fixture graph and a
  `graph @` disclosure; (2) a stale graph yields a source-read sketch with an
  `unverified` disclosure; (3) a whole-repo question is redirected to
  `/codebase-atlas` rather than answered with a giant tree.
  `skills/tests/codebase-atlas/` gains `test_atlas_tree.py` and the flag tuple
  in `test_skill_md.py` gains `--tree`.

### Explicitly deferred to a follow-up change

Chosen at discovery to keep this change to one capability:

- Indented call-tree text output from `refresh-architecture --feature`.
- Rendering `architecture.diff.json` as a structural tree diff.
- Folding HTML playbook rules (real labels, product colours, mobile and desktop,
  one file per point) into `add-visual-plan-review` — which would also require
  widening that change's stated "OpenSpec proposals only" boundary.
- Rewriting the `codebase-atlas` description so "show me X" no longer routes to a
  whole-repo rebuild. Its `triggers:` list is dead metadata (nothing reads it)
  and is deleted wholesale by `rewrite-skill-frontmatter`.
- Any HTML output from `explain-code`, and the interactive-capability check
  (`CI`, display, TTY) this repository does not yet have.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Coverage honesty | Answers carrying a disclosure line | 100% of behavioural-scenario replies, grounded and ungrounded | Behavioural scenarios in CI (skill test suite) |
| Determinism | `--tree` output for a fixed graph and args | Byte-identical across two runs; sorted children | `tests/codebase-atlas/test_atlas_tree.py` |
| Operability | `--tree` wall time on the committed graph (1,903 nodes / 1,199 edges) | ≤ 2 s, stdlib only, zero network | `test_atlas_tree.py` timing assertion on the committed graph |
| Context cost | `SKILL.md` line count; reference depth | `SKILL.md` ≤ 150 lines (hard cap 500 per `apply-progressive-disclosure-oversized-skills`); references one level deep; TOC if > 100 lines | `test_skill_md.py` |
| Compatibility | Skill test result with and without a `triggers:` key | Passes in both states | `test_skill_md.py` (explicit key assertions) |
| Portability | `validate_install_manifest.py --check-only` | 0 errors with the new manifest entries | `install.sh --check-only` in CI |

## Approaches Considered

### Approach 1: Prompt-only skill grounded through a new atlas `--tree` export

Description: `skills/explain-code/` ships no scripts. Its `SKILL.md` teaches the
catalogue and rules, and the grounding step shells out to
`<skill-base-dir>/../codebase-atlas/scripts/build_atlas.py --tree`, which is
the only new code. The model composes the answer from that output.

- Pros: smallest new surface (one CLI flag plus prose); grounding reuses
  `build_view_model()` and its coverage measurement rather than duplicating them;
  fits the "render before you index" and "adopt before build" principles; the
  catalogue stays a prompt, which is what makes show-me good.
- Cons: the sketch for anything other than a call tree (file tree, sequence
  diagram) is still model-authored, so only the call tree is machine-verified;
  depends on the atlas's basename-only coverage matching, which is an optimistic
  upper bound.
- Effort: **M**

### Approach 2: Scripted explainer that emits every form deterministically

Description: a new `skills/explain-code/scripts/sketch.py` that produces call trees,
file trees, and Mermaid sequence diagrams from the graph; the model only chooses
the form and adds one sentence of prose.

- Pros: every form is reproducible and unit-testable; no model-authored
  structure at all.
- Cons: duplicates the atlas view-model and the `generate_views.py` Mermaid
  emitters inside a third skill; sequence diagrams need runtime ordering the
  static graph does not carry, so the "deterministic" output would be wrong in a
  different way; loses the fast conversational feel that is the whole point;
  largest change and the one most likely to stall like Phase 0 did.
- Effort: **L**

### Approach 3: Fold a "question mode" into `codebase-atlas` instead of a new skill

Description: add `--tree` and a "Answering a narrow question" section to the
existing atlas `SKILL.md`; no new skill directory.

- Pros: one skill, one manifest entry, no new tests directory.
- Cons: conflates a deterministic whole-repo renderer with a conversational
  explainer that must sometimes answer from source and say so; the atlas
  `SKILL.md` gains the catalogue and the tail-block obligations and drifts
  toward the 500-line cap; the trigger overlap this change exists to fix gets
  worse; the codeviz proposal frames the atlas as "a rendering skill" that
  "never parses source itself", which a source-reading fallback would violate.
- Effort: **S**

### Recommended

**Approach 1.** It is the only option that keeps the catalogue as prose (the
property that makes show-me work) while adding exactly one piece of
deterministic code where determinism buys something — the call tree — and it
reuses the atlas's existing view-model and coverage measurement instead of
duplicating them (Approach 2's main cost). Approach 3 is cheaper but breaks the
atlas's stated contract of never reading source and worsens the routing problem.
The accepted trade-off is that non-call-tree forms remain model-authored; the
disclosure line makes that visible rather than hiding it.

### Selected Approach

**Approach 1 selected at Gate 1** (2026-09-04) with no modifications to the
approach itself. One refinement was made while designing it: the graph
freshness check reuses the existing `refresh-architecture` read-only contract
(`run_architecture.py --check`, exit `0` fresh / `2` drift / `1` error) instead
of re-implementing a provenance comparison in prose. This adds
`refresh-architecture` to the skill's declared cross-skill dependencies; see
`design.md` D2.

**Renamed at Gate 2**: the skill directory is `explain-code`, not `show-me`.
The name `show-me` is reserved for the upstream humanlayer skill this change
credits as the source of the format catalogue, so reusing it locally would
have made the attribution ambiguous. Only the directory, the slash command,
the manifest key, and the test path changed; no decision in `design.md` is
affected.

## Impact

**Affected specs (delta files in this change):**

- `specs/skill-workflow/spec.md` — ADDED: "Visual Code Explainer Skill",
  "Explainer Grounding and Coverage Disclosure", "Explainer Frontmatter Without
  Triggers" (records the dependency on `rewrite-skill-frontmatter`).
- `specs/codebase-analysis/spec.md` — ADDED: "Atlas Symbol Tree Export"
  (`--tree`, hop cap, exit codes, determinism).

**Code and docs:**

- New: `skills/explain-code/SKILL.md`, `skills/explain-code/references/*.md`,
  `skills/tests/explain-code/`.
- Modified: `skills/codebase-atlas/scripts/build_atlas.py` (new flag and a
  `tree.py` helper module — no bare-named `models`/`utils` modules, per
  `collect-uncollected-skill-tests`), `skills/codebase-atlas/SKILL.md` (flag
  table row only), `skills/tests/codebase-atlas/test_skill_md.py`,
  `skills/install-manifest.json`, `skills/pyproject.toml`,
  `docs/proposals/codebase-visualization-tool.md` (record Phase 0b shipped).
- Regenerated: `.claude/skills/`, `.agents/skills/` mirrors.

**Architecture layers:** Execution only (skill runtime). No coordinator,
trust, or governance surface changes. No API, database, or event contracts.

**Dependencies:** `rewrite-skill-frontmatter` (ordering only; this change is
valid before or after it, see Compatibility NFR). No conflict with
`add-visual-plan-review` (HTML deferred) or `add-cross-harness-flow-display`
(agent flows, not code structure).

**Architecture-analysis caveat:** the architecture refresh failed with three
validator errors during planning and `parallel_zones.json` is absent, so the
node/edge counts above come from the committed `architecture.summary.json` and
are unverified against the current tree.
