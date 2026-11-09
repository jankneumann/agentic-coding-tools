## Review Round 1

This packet exceeds the size budget and was truncated. You MAY use Read/Grep to recover truncated context.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/openspec/changes/add-visual-code-explainer/design.md b/openspec/changes/add-visual-code-explainer/design.md
index c93dd0ff..2033df91 100644
--- a/openspec/changes/add-visual-code-explainer/design.md
+++ b/openspec/changes/add-visual-code-explainer/design.md
@@ -29,13 +29,16 @@ atlas already holds the symbol adjacency (`build_view_model()["symbolEdges"]`).
 ### D2 — Freshness is decided by the existing `--check` contract
 
 The skill runs `python3 "<skill-base-dir>/../refresh-architecture/scripts/
-run_architecture.py" --check` and treats **exit 0 only** as fresh. Exit 2
-(drift), exit 1 (error), a missing script, or a missing graph all mean
-*ungrounded*. Rationale: `--check` is the read-only half of the
-`architecture-refresh` contract that the atlas already mirrors; re-deriving
-freshness from `git_sha` in prose would be a second, weaker definition. The
-skill **never** runs `--ensure` or the full pipeline (proposal: "never
-triggers a refresh on its own").
+run_architecture.py" --check` and treats **exit 0 only** as fresh. Any
+non-zero exit — the script returns `1` when provenance is not fresh, and
+other failures are also non-zero — a missing script, or a missing graph all
+mean *ungrounded*. Do **not** confuse this with `build_atlas.py --check`,
+which uses exit `2` for a stale HTML page; that flag is unrelated to
+explain-code freshness. Rationale: `run_architecture.py --check` is the
+read-only half of the `architecture-refresh` contract; re-deriving freshness
+from `git_sha` in prose would be a second, weaker definition. The skill
+**never** runs `--ensure` or the full pipeline (proposal: "never triggers a
+refresh on its own").
 
 ### D3 — `--tree` output format
 
@@ -48,8 +51,9 @@ build_atlas.py --tree <target> [--hops N] [--direction out|in|both] [--graph PAT
   `out` lists callees (`call` edges where the node is `s`), `in` lists callers, `both`
   prints two labelled sections `callees:` / `callers:`.
 - A node already printed on the current path is emitted once with the suffix
-  `(cycle)` and not expanded. A node beyond `--hops` is not printed; the parent
-  line gets the suffix `(+<n> more)` so truncation is visible.
+  `(cycle)` and not expanded. Neighbours beyond the hop depth are not printed;
+  the parent line gets the suffix `(+<n> more)` where `<n>` counts those
+  omitted further neighbours, so truncation is visible.
 - `--hops` default `2`, maximum `4` (matches the page's hop slider,
   `atlas_render.py`). Values above 4 are clamped with a stderr note.
 - Only edges with `ty == "call"` are walked (singular, the spelling the graph
@@ -57,8 +61,12 @@ build_atlas.py --tree <target> [--hops N] [--direction out|in|both] [--graph PAT
   `call` and `import` edges — and an import is a dependency, not a call: walking
   it would report importers as callers and corrupt the grounded output. A
   dependency-tree mode over `import` edges is out of scope for this change.
-- Trailing footer: `graph @ <sha7> · <language> <percent>% covered` per language
-  present, taken from `build_view_model(measure=True)` — the same `Coverage`
+- Trailing footer, one line: `graph @ <sha7> · python 14.4% / sql 37.0% covered`:
+  one `<language> <percent>%` entry per language, sorted by language name, joined
+  with ` / `, percent to one decimal place (the `Coverage.percent` value
+  itself, never re-rounded, so it stays equal to the page banner), a single
+  trailing `covered`. Percentages are
+  taken from `build_view_model(measure=True)` — the same `Coverage`
   values the page banner uses. `--no-coverage` suppresses it.
 
 Determinism: children sorted, no timestamps, no random ids. Byte-identical for a
@@ -70,20 +78,55 @@ fixed graph and arguments (NFR "Determinism").
 unique symbol `name`; a file path or basename matching a module, in which case
 the root is the module and hop 1 is the module's own symbols (aggregated view,
 mirroring the page's "selecting a file gives the aggregated module view").
-Ambiguous names print the candidate ids to stderr and exit `2`; no match exits
-`2` with `not found`. Exit `1` remains input/IO errors, `0` success — consistent
-with the existing `build_atlas.py` codes.
+No match exits `2` with `not found`. Ambiguous names print the candidate ids to
+stderr (one per line, sorted) and exit `3`. The two stay distinct because the
+skill must react differently: a missing symbol falls back to source reading, but
+an ambiguous one exists in the graph, so a source fallback would silently answer
+about a guessed symbol; the skill asks which candidate was meant instead. Exit
+`1` remains input/IO errors, `0` success. Exit `3` is new for `--tree`.
+`build_atlas.py --check` already uses exit `2` for a stale HTML page;
+`--check` and `--tree` never combine on one invocation.
 
 ### D5 — Disclosure line
 
-Every reply ends with exactly one line, never omitted, never collapsed:
+Every **sketching** reply (a catalogue visual was emitted, grounded or not)
+ends with exactly one line, never omitted, never collapsed. Two reply shapes
+are explicit exceptions and MUST NOT carry a `Grounding:` line:
 
-- grounded: `Grounding: graph @ <sha7>; python 14% / sql 37% covered`
-- ungrounded: `Grounding: source read, unverified (graph <stale|absent|check failed>)`
+- **Ambiguous-symbol clarification** — `--tree` exited `3`; the skill lists
+  candidate ids and asks which was meant (no visual, no source fallback).
+- **Whole-repository redirect** — the skill names `/codebase-atlas` and stops
+  (no visual).
 
-The grounded form copies the footer `--tree` prints (D3) so the two cannot
-drift. The percentages are the atlas's optimistic upper bound and the reference
-file says so.
+Sketching replies use one of:
+
+- grounded call tree:
+  `Grounding: graph @ <sha7>; python 14.4% / sql 37.0% covered`
+  Take the `--tree` footer from D3, copy the substring after `· ` and before
+  the trailing ` covered`, then re-append ` covered`. That substring is the
+  coverage list — same language order, ` / ` separators, and one-decimal
+  percents — so the disclosure and footer cannot drift. The line uses `; `
+  after the sha (not the footer's `·`) and always starts with `Grounding:`.
+- ungrounded / non-graph-backed:
+  `Grounding: source read, unverified (<reason>)`
+  where `<reason>` is exactly one of (decision order; first match wins):
+  - `graph absent` — before invoking `--check`, the skill finds the
+    `--check` script or the graph file missing
+  - `graph check failed` — the skill could not spawn/run `--check`
+    (OSError / exception before an exit code); or, after a fresh `--check`,
+    could not spawn/run `--tree`, `--tree` exits `1` (input/IO), or `--tree`
+    returns any exit other than `0`/`2`/`3`
+  - `graph stale` — `--check` ran and exited non-zero (including exit `1`
+    for stale provenance and any other non-zero the script returns)
+  - `symbol not in graph` — `--tree` exited `2`
+  - `form not graph-backed` — reply used a catalogue form other than a
+    call tree (component/file/sequence/structural-diff). Those forms are
+    model-authored from source the skill **must read** before sketching;
+    the disclosure still uses this reason (they are not graph-backed)
+
+Only a call tree built from `--tree` after a fresh `--check` may use the
+grounded form. The percentages are the atlas's optimistic upper bound and
+the grounding reference says so.
 
 ### D6 — Frontmatter without `triggers:`; explicit key test
 
@@ -106,8 +149,13 @@ the checkout; otherwise as pytest tests marked `e2e`. Independently of the
 harness, three **deterministic** tests always run in CI and encode the same
 three behaviours at the level the prompt can be checked without an LLM:
 
-1. `SKILL.md` instructs the disclosure line for both grounded and ungrounded
-   paths (D5 strings present in the grounding reference).
+1. `SKILL.md` / grounding reference instruct the disclosure line for grounded
+   and ungrounded sketching paths (both D5 templates present; the closed
+   ungrounded reason set `graph stale|absent|check failed`, `symbol not in
+   graph`, `form not graph-backed` present as exact tokens; the
+   footer→disclosure mapping documented — copy after `· ` / before trailing
+   ` covered`, re-append ` covered`, use `; ` after the sha; clarification
+   and redirect replies exempt from `Grounding:`).
 2. `SKILL.md` instructs redirecting whole-repository questions to
    `/codebase-atlas` (string present, and the atlas is in `related:`).
 3. `SKILL.md` instructs never running `--ensure` or the analysis pipeline
@@ -115,9 +163,10 @@ three behaviours at the level the prompt can be checked without an LLM:
 
 The fourth behaviour — "a grounded call tree cannot invent symbols" — is
 asserted where the code lives: `tests/codebase-atlas/test_atlas_tree.py`
-checks that `--tree` on the `tiny_graph` fixture prints only fixture node ids.
-Keeping it there lets `wp-skill` and `wp-atlas-tree` run in parallel without
-`wp-skill` importing code it does not own.
+checks that every node printed for the `tiny_graph` fixture matches a
+fixture node by `(name, file)` (the tree format emits name/file/kind, not
+node ids). Keeping it there lets `wp-skill` and `wp-atlas-tree` run in
+parallel without `wp-skill` importing code it does not own.
 
 Rationale: the inversion change is 0/10 tasks; this change must be green on
 today's CI and must not block on it.
diff --git a/openspec/changes/add-visual-code-explainer/proposal.md b/openspec/changes/add-visual-code-explainer/proposal.md
index 6e209922..b124b181 100644
--- a/openspec/changes/add-visual-code-explainer/proposal.md
+++ b/openspec/changes/add-visual-code-explainer/proposal.md
@@ -41,23 +41,27 @@ that gates them, and the analysis that motivated this change is fresh.
   worked example adapted from humanlayer (with attribution) and the form's
   "smallest view" rule. **HTML output is explicitly out of scope for v1** — the
   skill emits text and Mermaid only, inline in the reply.
-- **Grounding step.** Before sketching, the skill checks graph freshness with
-  the existing read-only `run_architecture.py --check` (exit `0` is fresh;
-  anything else is treated as stale) and, when fresh,
-  obtains callers/callees from the new atlas `--tree` export and builds the call
-  tree from that data. When the graph is stale, absent, or does not cover the
-  files in question, the skill reads source directly and **labels the sketch
-  unverified**. It never refuses and never triggers a refresh on its own.
-- **Coverage disclosure line.** Every answer ends with one line stating the
-  grounding source (`graph @ <sha>`, or `source read, unverified`) and, for
-  grounded sketches, the per-language coverage percentage the atlas already
-  computes. The line is not optional and not collapsible.
+- **Grounding step.** Before sketching a call tree, the skill checks graph
+  freshness with the existing read-only `run_architecture.py --check` (exit `0`
+  alone is fresh; missing script/graph → `graph absent`; spawn failure →
+  `graph check failed`; any non-zero `--check` exit → `graph stale`) and, when
+  fresh, obtains callers/callees from the new atlas `--tree` export. When the
+  graph is unusable or the symbol is outside coverage, the skill reads source
+  directly and **labels the sketch unverified**. Ambiguous `--tree` exit `3`
+  asks instead of guessing. It never refuses and never triggers a refresh on
+  its own.
+- **Coverage disclosure line.** Every **sketching** reply ends with one
+  `Grounding:` line (`graph @ <sha>; … covered`, or
+  `source read, unverified (<reason>)`). Ambiguous-symbol clarifications and
+  whole-repository redirects are explicit exceptions and carry no disclosure
+  line. The line is otherwise not optional and not collapsible.
 - **`codebase-atlas` gains `--tree <symbol-or-file> [--hops N] [--direction in|out|both]`.**
   A stdlib-only text export in `build_atlas.py` that BFS-walks the `call` edges of
   the existing `symbolEdges` adjacency from `build_view_model()` and prints an indented tree
   with file path and line per node, hop-capped at 4 to match the page's slider.
   Output is byte-stable for a fixed graph. Exit codes follow the existing
-  contract (`0` ok, `1` input error, `2` symbol not found).
+  contract (`0` ok, `1` input error, `2` symbol not found) plus `3` for an
+  ambiguous name, which the skill resolves by asking rather than guessing.
 - **Frontmatter written for the post-`rewrite-skill-frontmatter` world.** The new
   `SKILL.md` carries `name, description, category, tags, user_invocable, related`
   with a description that states capability and trigger condition in third
@@ -72,14 +76,20 @@ that gates them, and the analysis that motivated this change is fresh.
   `"tests/explain-code"`. Runtime mirrors regenerate via `skills/install.sh`.
 - **Tests.** `skills/tests/explain-code/test_skill_md.py` (frontmatter parses,
   explicit key presence, references resolve, related resolve, tail block
-  present) plus **three behavioural scenarios** in the replay-harness shape that
-  `invert-skill-test-suite-to-behavioural` prescribes: (1) a grounded question
-  yields a call tree whose nodes all exist in the fixture graph and a
-  `graph @` disclosure; (2) a stale graph yields a source-read sketch with an
-  `unverified` disclosure; (3) a whole-repo question is redirected to
-  `/codebase-atlas` rather than answered with a giant tree.
-  `skills/tests/codebase-atlas/` gains `test_atlas_tree.py` and the flag tuple
-  in `test_skill_md.py` gains `--tree`.
+  present) plus **three deterministic behavioural checks** in
+  `test_behaviour.py` that encode the behaviours
+  `invert-skill-test-suite-to-behavioural` wants without blocking on that
+  change (0/10 tasks today): (1) grounding reference contains both D5
+  disclosure forms, the closed ungrounded reason tokens, the
+  footer→disclosure mapping, and the clarification/redirect disclosure
+  exemptions; (2) `SKILL.md` redirects whole-repo questions to
+  `/codebase-atlas`; (3) `SKILL.md` forbids `--ensure` / the analysis
+  pipeline. The "grounded call tree invents no symbols" assertion lives in
+  `tests/codebase-atlas/test_atlas_tree.py` (every printed node matches a
+  fixture node by `(name, file)`). Optional trajectory-harness fixtures are
+  task 2.8 when the harness is present. `skills/tests/codebase-atlas/` gains
+  `test_atlas_tree.py` and the flag tuple in `test_skill_md.py` gains
+  `--tree`.
 
 ### Explicitly deferred to a follow-up change
 
@@ -100,7 +110,7 @@ Chosen at discovery to keep this change to one capability:
 
 | Attribute | Metric | Target | Verified by (phase) |
 |-----------|--------|--------|---------------------|
-| Coverage honesty | Answers carrying a disclosure line | 100% of behavioural-scenario replies, grounded and ungrounded | Behavioural scenarios in CI (skill test suite) |
+| Coverage honesty | Sketching replies carrying a disclosure line | 100% of sketching behavioural-scenario replies (clarification/redirect scenarios exempt) | Behavioural scenarios in CI (skill test suite) |
 | Determinism | `--tree` output for a fixed graph and args | Byte-identical across two runs; sorted children | `tests/codebase-atlas/test_atlas_tree.py` |
 | Operability | `--tree` wall time on the committed graph (1,903 nodes / 1,199 edges) | ≤ 2 s, stdlib only, zero network | `test_atlas_tree.py` timing assertion on the committed graph |
 | Context cost | `SKILL.md` line count; reference depth | `SKILL.md` ≤ 150 lines (hard cap 500 per `apply-progressive-disclosure-oversized-skills`); references one level deep; TOC if > 100 lines | `test_skill_md.py` |
@@ -171,8 +181,9 @@ disclosure line makes that visible rather than hiding it.
 **Approach 1 selected at Gate 1** (2026-09-04) with no modifications to the
 approach itself. One refinement was made while designing it: the graph
 freshness check reuses the existing `refresh-architecture` read-only contract
-(`run_architecture.py --check`, exit `0` fresh / `2` drift / `1` error) instead
-of re-implementing a provenance comparison in prose. This adds
+(`run_architecture.py --check`, exit `0` fresh / any non-zero ungrounded;
+the script returns `1` when provenance is not fresh) instead of
+re-implementing a provenance comparison in prose. This adds
 `refresh-architecture` to the skill's declared cross-skill dependencies; see
 `design.md` D2.
 
@@ -198,7 +209,7 @@ affected.
 - New: `skills/explain-code/SKILL.md`, `skills/explain-code/references/*.md`,
   `skills/tests/explain-code/`.
 - Modified: `skills/codebase-atlas/scripts/build_atlas.py` (new flag and a
-  `tree.py` helper module — no bare-named `models`/`utils` modules, per
+  `atlas_tree.py` helper module — no bare-named `models`/`utils` modules, per
   `collect-uncollected-skill-tests`), `skills/codebase-atlas/SKILL.md` (flag
   table row only), `skills/tests/codebase-atlas/test_skill_md.py`,
   `skills/install-manifest.json`, `skills/pyproject.toml`,
diff --git a/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md b/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
index e0c04fac..069b98f6 100644
--- a/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
+++ b/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
@@ -2,12 +2,12 @@
 
 ### Requirement: Atlas Symbol Tree Export
 
-`skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional `--hops N` (default `2`, maximum `4`, larger values clamped with a stderr note) and `--direction out|in|both` (default `out`), and SHALL print an indented text tree to stdout instead of rendering the page. The traversal SHALL walk the symbol-level adjacency produced by `build_view_model()` (`symbolEdges`) restricted to edges whose `ty` is `call` — `import` and every other edge type are dependencies, not calls, and SHALL NOT appear as callers or callees — using only the Python standard library and making no network requests. Each line SHALL show `<name>  (<file>:<line>)  [<kind>]`, children SHALL be sorted by name then id, a node already on the current path SHALL be printed once with the suffix `(cycle)` and not expanded, and a parent whose children exceed `--hops` SHALL carry the suffix `(+<n> more)`. The output SHALL end with a footer `graph @ <sha7> · <language> <percent>% covered` per language present unless `--no-coverage` is given. `<target>` SHALL resolve as exact node id, then unique symbol name, then module file path or basename (rooting the tree at the module with its own symbols as hop 1). Exit codes SHALL be `0` success, `1` input or IO error, `2` target not found or ambiguous (candidates listed on stderr). Output SHALL be byte-identical across runs for a fixed graph and arguments.
+`skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional `--hops N` (default `2`, maximum `4`, larger values clamped with a stderr note) and `--direction out|in|both` (default `out`), and SHALL print an indented text tree to stdout instead of rendering the page. The traversal SHALL walk the symbol-level adjacency produced by `build_view_model()` (`symbolEdges`) restricted to edges whose `ty` is `call` — `import` and every other edge type are dependencies, not calls, and SHALL NOT appear as callers or callees — using only the Python standard library and making no network requests. Each line SHALL show `<name>  (<file>:<line>)  [<kind>]`, children SHALL be sorted by name then id, a node already on the current path SHALL be printed once with the suffix `(cycle)` and not expanded, and a parent with further neighbours beyond the hop depth SHALL carry the suffix `(+<n> more)` where `<n>` is the count of those omitted further neighbours. The output SHALL end with a single footer line `graph @ <sha7> · <language> <percent>% / <language> <percent>% covered`, one `<language> <percent>%` entry per language present, sorted by language name and joined with ` / `, with `<percent>` printed to exactly one decimal place as `Coverage.percent` returns it (for example `14.4%`, `37.0%`), unless `--no-coverage` is given. `<target>` SHALL resolve as exact node id, then unique symbol name, then module file path or basename (rooting the tree at the module with its own symbols as hop 1). Exit codes SHALL be `0` success, `1` input or IO error, `2` target not found, `3` target ambiguous (candidate ids listed on stderr, one per line, sorted). Output SHALL be byte-identical across runs for a fixed graph and arguments.
 
 #### Scenario: Callees tree for a symbol
 
 - **WHEN** `build_atlas.py --tree <symbol-id>` runs against a graph containing that symbol
-- **THEN** stdout SHALL start with the symbol's line and list its callees indented two spaces per hop, sorted by name
+- **THEN** stdout SHALL start with a root line matching `<name>  (<file>:<line>)  [<kind>]` and list its callees indented two spaces per hop, sorted by name then id
 - **AND** the exit code SHALL be `0`
 
 #### Scenario: Callers tree with hop cap
@@ -34,11 +34,17 @@
 - **THEN** the root line SHALL be the module and hop 1 SHALL be the module's own symbols
 - **AND** subsequent hops SHALL follow those symbols' `call` edges
 
-#### Scenario: Unknown or ambiguous target exits 2
+#### Scenario: Unknown target exits 2
 
-- **WHEN** `--tree` names a symbol not in the graph, or a bare name matching several ids
+- **WHEN** `--tree` names a symbol that is not in the graph
 - **THEN** the exit code SHALL be `2`
-- **AND** for the ambiguous case stderr SHALL list the candidate ids
+- **AND** stderr SHALL contain `not found`
+
+#### Scenario: Ambiguous target exits 3
+
+- **WHEN** `--tree` names a bare symbol name matching several node ids
+- **THEN** the exit code SHALL be `3`, distinct from not-found
+- **AND** stderr SHALL list the candidate ids, one per line, sorted
 
 #### Scenario: Deterministic output
 
@@ -49,3 +55,47 @@
 
 - **WHEN** `--tree` runs without `--no-coverage`
 - **THEN** the footer percentages SHALL equal the `Coverage.percent` values `build_view_model()` computes for the same repository root
+
+#### Scenario: Default hops and direction
+
+- **WHEN** `--tree <target>` is invoked with neither `--hops` nor `--direction`
+- **THEN** the traversal SHALL use `--hops 2` and `--direction out`
+- **AND** the exit code SHALL be `0` for a resolvable target
+
+#### Scenario: Hops above four are clamped
+
+- **WHEN** `--tree <target> --hops 9` is given
+- **THEN** the effective hop cap SHALL be `4`
+- **AND** stderr SHALL contain a note that the value was clamped
+
+#### Scenario: No-coverage suppresses the footer
+
+- **WHEN** `--tree <target> --no-coverage` runs
+- **THEN** stdout SHALL omit the `graph @` coverage footer line
+
+#### Scenario: Input or IO error exits 1
+
+- **WHEN** `--tree` cannot read the graph file (missing path via `--graph`, or unreadable IO)
+- **THEN** the exit code SHALL be `1`
+
+#### Scenario: Coverage footer shape
+
+- **WHEN** `--tree` runs without `--no-coverage` on a graph with multiple languages
+- **THEN** stdout SHALL end with one line matching `graph @ <sha7> · <language> <percent>% / <language> <percent>% covered`
+- **AND** language entries SHALL be sorted by language name and joined with ` / `
+- **AND** each `<percent>` SHALL use exactly one decimal place as returned by `Coverage.percent`
+
+#### Scenario: Target resolution precedence
+
+- **WHEN** the same string could match an exact node id and also appear as a symbol name
+- **THEN** `--tree` SHALL resolve the exact node id and SHALL NOT treat the name match as ambiguous
+
+#### Scenario: Unique name resolves
+
+- **WHEN** `--tree` is given a bare symbol name that matches exactly one node
+- **THEN** that node SHALL be the root and the exit code SHALL be `0`
+
+#### Scenario: Direction both labels sections
+
+- **WHEN** `--tree <target> --direction both` runs
+- **THEN** stdout SHALL include labelled `callees:` and `callers:` sections
diff --git a/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md b/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md
index bcb27546..c2afba94 100644
--- a/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md
+++ b/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md
@@ -6,7 +6,7 @@ The repository SHALL provide a user-invocable, prompt-only skill `explain-code`
 
 #### Scenario: Narrow question answered with the smallest visual
 
-- **WHEN** a user asks how a specific function, module, or message path works or connects
+- **WHEN** a user asks how a specific function, module, or message path works or connects, and the named target is resolvable without an ambiguous-symbol clarification
 - **THEN** the skill SHALL reply with exactly one visual form from the catalogue and at most three sentences of prose
 - **AND** every node in the visual SHALL carry its file location
 
@@ -27,34 +27,61 @@ The repository SHALL provide a user-invocable, prompt-only skill `explain-code`
 
 - **WHEN** the skill answers any question
 - **THEN** it SHALL emit text and Mermaid inline in the reply only
-- **AND** it SHALL NOT create, modify, or open any file
+- **AND** it SHALL NOT create or modify any file, and SHALL NOT open a browser or otherwise present a user-facing file side effect
+- **AND** it MAY read the architecture graph and source files read-only as part of grounding
 
 ### Requirement: Explainer Grounding and Coverage Disclosure
 
-Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh. When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that export returns. When stale, absent, or failing, the skill SHALL read source directly and label the sketch unverified. Every reply SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% covered …` when grounded, or `Grounding: source read, unverified (graph <stale|absent|check failed>)` when not. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.
+Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh (any non-zero exit means ungrounded; the script returns `1` when provenance is not fresh). When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that `build_atlas.py --tree` returns. When `--tree` exits `3` (ambiguous target), the skill SHALL list the candidate ids from stderr and ask which one was meant, and SHALL NOT fall back to source reading or sketch a tree. When stale, absent, or failing (including `--tree` exit `2`, `--tree` spawn failure, or any `--tree` exit other than `0`/`2`/`3`), the skill SHALL read source directly and label the sketch unverified. Every sketching reply (a catalogue visual was emitted) SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% / <language> <percent>% covered` when grounded (coverage list taken from the `--tree` footer by copying the substring after `· ` and before the trailing ` covered`, then re-appending ` covered`, preserving language order and ` / ` separators), or `Grounding: source read, unverified (<reason>)` when not, where `<reason>` is chosen by first-match order: `graph absent` (script or graph missing before `--check`), `graph check failed` (`--check` could not be spawned; or after a fresh `--check`, `--tree` could not be spawned, exits `1`, or returns any exit other than `0`/`2`/`3`), `graph stale` (`--check` ran and exited non-zero), `symbol not in graph` (`--tree` exited `2`), or `form not graph-backed` (non-call-tree catalogue form). For non-call-tree catalogue forms the skill SHALL read the relevant source files before sketching and SHALL still use reason `form not graph-backed` (they are not graph-backed). Ambiguous-symbol clarification replies and whole-repository redirect replies SHALL NOT carry a `Grounding:` line. Only a call tree built from `--tree` after a fresh `--check` MAY use the grounded form; other catalogue forms SHALL use `form not graph-backed`. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.
 
 #### Scenario: Fresh graph grounds the call tree
 
 - **WHEN** `run_architecture.py --check` exits `0` and the question names a symbol present in the graph
 - **THEN** the call tree SHALL contain only nodes returned by `build_atlas.py --tree`
-- **AND** the disclosure line SHALL read `Grounding: graph @ <sha7>; …` with per-language coverage percentages copied from the `--tree` footer
+- **AND** the disclosure line SHALL read `Grounding: graph @ <sha7>; …` with per-language coverage percentages copied from the `--tree` footer per the substring rule above
 
 #### Scenario: Stale or absent graph falls back to source
 
 - **WHEN** `run_architecture.py --check` exits non-zero, or the script or graph file is missing
 - **THEN** the skill SHALL still answer, drawing the sketch from the source files it reads
-- **AND** the disclosure line SHALL read `Grounding: source read, unverified (graph <reason>)`
+- **AND** the disclosure line SHALL read `Grounding: source read, unverified (<reason>)` with reason `graph stale`, `graph absent`, or `graph check failed` per the first-match order above
 - **AND** the skill SHALL NOT invoke `--ensure` or the analysis pipeline
 
 #### Scenario: Symbol outside graph coverage
 
 - **WHEN** the graph is fresh but `build_atlas.py --tree` exits `2` (target not found) for the requested symbol
 - **THEN** the skill SHALL fall back to source reading for that symbol
-- **AND** the disclosure line SHALL use the unverified form with reason `symbol not in graph`
+- **AND** the disclosure line SHALL read `Grounding: source read, unverified (symbol not in graph)`
 
-#### Scenario: Disclosure line present on every answer
+#### Scenario: Non-call-tree form is not graph-backed
 
-- **WHEN** the skill produces any reply, grounded or not
+- **WHEN** the skill answers with a catalogue form other than a call tree
+- **THEN** the skill SHALL read the relevant source files before sketching
+- **AND** the disclosure line SHALL read `Grounding: source read, unverified (form not graph-backed)`
+- **AND** the skill SHALL NOT claim the grounded `graph @` form for that reply
+
+#### Scenario: Tree tool failure after fresh check
+
+- **WHEN** `run_architecture.py --check` exits `0` but `build_atlas.py --tree` cannot be spawned or returns an exit other than `0`, `2`, or `3`
+- **THEN** the skill SHALL fall back to source reading
+- **AND** the disclosure line SHALL read `Grounding: source read, unverified (graph check failed)`
+
+#### Scenario: Ambiguous symbol asks instead of guessing
+
+- **WHEN** the graph is fresh and `build_atlas.py --tree` exits `3` (ambiguous name) for the requested symbol
+- **THEN** the skill SHALL list the candidate ids from stderr and ask which one was meant
+- **AND** the skill SHALL NOT fall back to source reading or sketch a tree for any candidate
+- **AND** the reply SHALL NOT include a `Grounding:` line
+
+#### Scenario: Whole-repository redirect has no disclosure line
+
+- **WHEN** a user asks for the whole architecture, the full dependency graph, or a repository-wide map
+- **THEN** the skill SHALL name `/codebase-atlas` and stop
+- **AND** the reply SHALL NOT include a `Grounding:` line
+
+#### Scenario: Disclosure line present on every sketching answer
+
+- **WHEN** the skill produces a sketching reply (a catalogue visual was emitted), grounded or not
 - **THEN** the final line of the reply SHALL begin with `Grounding:`
 - **AND** the reply SHALL contain exactly one such line
 
@@ -68,6 +95,19 @@ The `explain-code` `SKILL.md` frontmatter SHALL declare `name`, `description`, `
 - **THEN** it SHALL pass in both states
 - **AND** it SHALL fail if any of `name`, `description`, `category`, `tags`, `user_invocable`, or `related` is missing or empty
 
+#### Scenario: Frontmatter omits triggers and sets Architecture category
+
+- **WHEN** the `explain-code` `SKILL.md` frontmatter is read
+- **THEN** it SHALL NOT declare a `triggers:` key
+- **AND** `category` SHALL be `Architecture`
+- **AND** `user_invocable` SHALL be `true`
+- **AND** `related` SHALL include `codebase-atlas` and `refresh-architecture`
+
+#### Scenario: Skill markdown ends with required tail sections
+
+- **WHEN** the `explain-code` `SKILL.md` body is read
+- **THEN** it SHALL end with the `## Common Rationalizations`, `## Red Flags`, and `## Verification` sections
+
 #### Scenario: Description carries the trigger condition
 
 - **WHEN** the frontmatter `description` is read
@@ -84,6 +124,17 @@ The `explain-code` `SKILL.md` frontmatter SHALL declare `name`, `description`, `
 - **THEN** the manifest validator SHALL report zero errors
 - **AND** every sibling reference in `skills/explain-code/**` SHALL be covered by the declared cross-skill dependencies
 
+#### Scenario: Manifest declares portable distribution and atlas dependencies
+
+- **WHEN** `skills/install-manifest.json` is read after the skill is added
+- **THEN** `explain-code` SHALL declare `"distribution": "portable"`
+- **AND** `cross_skill_dependencies` SHALL list `codebase-atlas` and `refresh-architecture` for `explain-code`
+
+#### Scenario: Sibling skill paths use skill-base-dir form
+
+- **WHEN** `skills/explain-code/**` references a co-installed sibling skill
+- **THEN** the reference SHALL use the `<skill-base-dir>/../<skill>/` form
+
 #### Scenario: Tests collected by the default sweep
 
 - **WHEN** `skills/.venv/bin/python -m pytest` runs from `skills/` with no path arguments
diff --git a/openspec/changes/add-visual-code-explainer/tasks.md b/openspec/changes/add-visual-code-explainer/tasks.md
index e7243d68..21edd807 100644
--- a/openspec/changes/add-visual-code-explainer/tasks.md
+++ b/openspec/changes/add-visual-code-explainer/tasks.md
@@ -5,125 +5,125 @@ Within each phase, test tasks precede the implementation they verify (TDD RED 
 
 ## Phase 1 — `codebase-atlas --tree` export (package `wp-atlas-tree`)
 
-- [ ] 1.1 Write `skills/tests/codebase-atlas/test_atlas_tree.py` against the `tiny_graph` fixture: callees tree ordering, callers with `--hops 1` and `(+n more)` suffix, `(cycle)` printed once, basename target roots at the module, unknown target exits `2`, ambiguous name exits `2` with candidates on stderr, byte-identical output across two runs, footer percentages equal `Coverage.percent`, output contains only fixture node ids, a mixed-edge fixture (a copy of `tiny_graph` plus one `import` edge) proving import edges never appear as callers or callees, and a `≤ 2 s` timing test on the committed graph (skipped when absent)
-  **Spec scenarios**: codebase-analysis "Callees tree for a symbol", "Callers tree with hop cap", "Non-call edges are excluded", "Cycle is printed once", "File target gives the aggregated module view", "Unknown or ambiguous target exits 2", "Deterministic output", "Coverage footer matches the page banner"
+- [x] 1.1 Write `skills/tests/codebase-atlas/test_atlas_tree.py` against the `tiny_graph` fixture: callees tree ordering (name then id), callers with `--hops 1` and `(+n more)` suffix, `(cycle)` printed once, basename target roots at the module, unknown target exits `2`, ambiguous name exits `3` with sorted candidates on stderr, byte-identical output across two runs, footer percentages equal `Coverage.percent` with sorted languages and one-decimal shape, every printed node matches a fixture node by `(name, file)` (tree format emits name/file/kind, not ids), a mixed-edge fixture (a copy of `tiny_graph` plus one `import` edge) proving import edges never appear as callers or callees, default hops/direction, hops>4 clamp with stderr note, `--no-coverage` omits footer, unreadable `--graph` exits `1`, exact-id-before-name resolution precedence, unique-name resolve, `--direction both` labelled sections, and a `≤ 2 s` timing test on the committed graph (skipped when absent)
+  **Spec scenarios**: codebase-analysis "Callees tree for a symbol", "Callers tree with hop cap", "Non-call edges are excluded", "Cycle is printed once", "File target gives the aggregated module view", "Unknown target exits 2", "Ambiguous target exits 3", "Deterministic output", "Coverage footer matches the page banner", "Default hops and direction", "Hops above four are clamped", "No-coverage suppresses the footer", "Input or IO error exits 1", "Coverage footer shape", "Target resolution precedence", "Unique name resolves", "Direction both labels sections"
   **Design decisions**: D3 (format), D4 (resolution), D7 (fixture-only nodes), D8 (module name)
   **Dependencies**: None
   **Size**: M
 
-- [ ] 1.2 Implement `skills/codebase-atlas/scripts/atlas_tree.py` — `resolve_target()`, `walk()` over `call`-typed `symbolEdges`, `format_tree()`, `footer()` — stdlib only, children sorted by name then id, hop clamp at 4 with stderr note
+- [x] 1.2 Implement `skills/codebase-atlas/scripts/atlas_tree.py` — `resolve_target()`, `walk()` over `call`-typed `symbolEdges`, `format_tree()`, `footer()` — stdlib only, children sorted by name then id, hop clamp at 4 with stderr note
   **Spec scenarios**: as 1.1
   **Design decisions**: D3, D4, D8
   **Dependencies**: 1.1
   **Size**: M
 
-- [ ] 1.3 Wire `--tree`, `--hops`, `--direction` into `build_atlas.py` `parse_args()` and dispatch in `main()` after `build_view_model()` and before the render path, honouring `--no-coverage` and returning `0/1/2`
-  **Spec scenarios**: codebase-analysis "Unknown or ambiguous target exits 2", "Coverage footer matches the page banner"
+- [x] 1.3 Wire `--tree`, `--hops`, `--direction` into `build_atlas.py` `parse_args()` and dispatch in `main()` after `build_view_model()` and before the render path, honouring `--no-coverage` and returning `0/1/2/3`
+  **Spec scenarios**: codebase-analysis "Unknown target exits 2", "Ambiguous target exits 3", "Coverage footer matches the page banner"
   **Design decisions**: D3, D8
   **Dependencies**: 1.2
   **Size**: S
 
-- [ ] Checkpoint: run `skills/tests/codebase-atlas`, review diff, verify scope stays inside `skills/codebase-atlas/**` + `skills/tests/codebase-atlas/**`
+- [x] Checkpoint: run `skills/tests/codebase-atlas`, review diff, verify scope stays inside `skills/codebase-atlas/**` + `skills/tests/codebase-atlas/**`
 
-- [ ] 1.4 Add the `--tree` / `--hops` / `--direction` rows to the flag table in `skills/codebase-atlas/SKILL.md` with a two-line usage example (keep the file under 150 lines)
+- [x] 1.4 Add the `--tree` / `--hops` / `--direction` rows to the flag table in `skills/codebase-atlas/SKILL.md` with a two-line usage example (keep the file under 150 lines)
   **Spec scenarios**: codebase-analysis "Callees tree for a symbol"
   **Design decisions**: D3
   **Dependencies**: 1.3
   **Size**: XS
 
-- [ ] 1.5 Extend the flag tuple in `skills/tests/codebase-atlas/test_skill_md.py` with `--tree`, `--hops`, `--direction` so the SKILL.md ↔ CLI check covers them
+- [x] 1.5 Extend the flag tuple in `skills/tests/codebase-atlas/test_skill_md.py` with `--tree`, `--hops`, `--direction` so the SKILL.md ↔ CLI check covers them
   **Spec scenarios**: (test coverage of 1.4)
   **Design decisions**: —
   **Dependencies**: 1.4
   **Size**: XS
 
-- [ ] Checkpoint: run `skills/tests/codebase-atlas`, confirm the SKILL.md flag table and CLI agree, review the cumulative package diff
+- [x] Checkpoint: run `skills/tests/codebase-atlas`, confirm the SKILL.md flag table and CLI agree, review the cumulative package diff
 
 ## Phase 2 — `explain-code` skill (package `wp-skill`, parallel with Phase 1)
 
-- [ ] 2.1 Write `skills/tests/explain-code/test_skill_md.py`: frontmatter parses; `name`, `description`, `category`, `tags`, `user_invocable`, `related` present and non-empty (asserted explicitly, not via `assert_required_keys_present`); no `triggers` key; `assert_references_resolve`; `assert_related_resolve`; `assert_tail_block_present`; `SKILL.md ≤ 150` lines; no reference file links to another reference; description mentions `codebase-atlas`
-  **Spec scenarios**: skill-workflow "Frontmatter valid in both orderings", "Description carries the trigger condition", "Progressive disclosure layout"
+- [x] 2.1 Write `skills/tests/explain-code/test_skill_md.py`: frontmatter parses; `name`, `description`, `category: Architecture`, `tags`, `user_invocable: true`, `related` including codebase-atlas and refresh-architecture present and non-empty (asserted explicitly, not via `assert_required_keys_present`); no `triggers` key; `assert_references_resolve`; `assert_related_resolve`; `assert_tail_block_present` (Common Rationalizations / Red Flags / Verification); `SKILL.md ≤ 150` lines; no reference file links to another reference; description mentions `codebase-atlas`
+  **Spec scenarios**: skill-workflow "Frontmatter valid in both orderings", "Frontmatter omits triggers and sets Architecture category", "Skill markdown ends with required tail sections", "Description carries the trigger condition", "Progressive disclosure layout"
   **Design decisions**: D6
   **Dependencies**: None
   **Size**: S
 
-- [ ] 2.2 Write `skills/tests/explain-code/test_behaviour.py` — three deterministic behavioural checks: grounding reference contains both D5 disclosure forms; `SKILL.md` redirects whole-repository questions to `/codebase-atlas`; `SKILL.md` forbids `--ensure` and the analysis pipeline
-  **Spec scenarios**: skill-workflow "Disclosure line present on every answer", "Whole-repository question redirected", "Stale or absent graph falls back to source"
+- [x] 2.2 Write `skills/tests/explain-code/test_behaviour.py` — three deterministic behavioural checks: grounding reference contains both D5 disclosure forms, the closed ungrounded reason tokens (`graph stale`, `graph absent`, `graph check failed`, `symbol not in graph`, `form not graph-backed`), the footer→disclosure mapping (`;` after sha, copy after `· ` / before trailing ` covered`), non-call-tree source-read requirement, tree-tool-failure → `graph check failed`, and the clarification/redirect disclosure exemptions; `SKILL.md` redirects whole-repository questions to `/codebase-atlas`; `SKILL.md` forbids `--ensure` and the analysis pipeline
+  **Spec scenarios**: skill-workflow "Disclosure line present on every sketching answer", "Whole-repository question redirected", "Whole-repository redirect has no disclosure line", "Stale or absent graph falls back to source", "Non-call-tree form is not graph-backed", "Tree tool failure after fresh check", "Ambiguous symbol asks instead of guessing"
   **Design decisions**: D2, D5, D7, D9
   **Dependencies**: None
   **Size**: S
 
-- [ ] 2.3 Write `skills/explain-code/SKILL.md` — frontmatter per D6 (no `triggers`), one-paragraph purpose crediting humanlayer's MIT `show-me`, the five rules, a catalogue table linking each `references/<form>.md`, the grounding step summary linking `references/grounding.md`, the deferred-scope note (no HTML, no files, no browser), and the tail block copied from `skills/references/skill-tail-template.md`
+- [x] 2.3 Write `skills/explain-code/SKILL.md` — frontmatter per D6 (no `triggers`), one-paragraph purpose crediting humanlayer's MIT `show-me`, the five rules, a catalogue table linking each `references/<form>.md`, the grounding step summary linking `references/grounding.md`, the deferred-scope note (no HTML, no files, no browser), and the tail block copied from `skills/references/skill-tail-template.md`
   **Spec scenarios**: skill-workflow "Narrow question answered with the smallest visual", "No file or browser side effects", "Progressive disclosure layout"
   **Design decisions**: D1, D6, D9
   **Dependencies**: 2.1, 2.2
   **Size**: M
 
-- [ ] Checkpoint: run `skills/tests/explain-code`, review diff, verify scope stays inside `skills/explain-code/**` + `skills/tests/explain-code/**`
+- [x] Checkpoint: run `skills/tests/explain-code`, review diff, verify scope stays inside `skills/explain-code/**` + `skills/tests/explain-code/**`
 
-- [ ] 2.4 Write the five form references — `references/call-tree.md`, `component-tree.md`, `file-tree.md`, `sequence.md`, `structural-diff.md` — each with: when to use, the smallest-view rule for that form, one worked example adapted from humanlayer with attribution, and how to attach file locations
+- [x] 2.4 Write the five form references — `references/call-tree.md`, `component-tree.md`, `file-tree.md`, `sequence.md`, `structural-diff.md` — each with: when to use, the smallest-view rule for that form, one worked example adapted from humanlayer with attribution, and how to attach file locations
   **Spec scenarios**: skill-workflow "Narrow question answered with the smallest visual"
   **Design decisions**: D1
   **Dependencies**: 2.3
   **Size**: M
 
-- [ ] 2.5 Write `references/grounding.md` — the `--check` freshness command (D2), the `--tree` invocation via `<skill-base-dir>/../codebase-atlas/`, how to copy the footer into the disclosure line (D5), the symbol-not-in-graph fallback, the whole-repository redirect, and the refusal list (D9)
-  **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Symbol outside graph coverage", "Disclosure line present on every answer"
+- [x] 2.5 Write `references/grounding.md` — the `--check` freshness command (D2: exit `0` only = fresh; non-zero ungrounded), the `--tree` invocation via `<skill-base-dir>/../codebase-atlas/`, how to map the footer coverage list into the `Grounding:` line (D5 substring rule), the closed ungrounded reason set with first-match order (`graph absent` → `graph check failed` → `graph stale` → `symbol not in graph` → `form not graph-backed`, including `--tree` spawn/unexpected-exit → `graph check failed`), non-call-tree source-read before sketching, the ask-don't-guess rule for an ambiguous name (exit `3`, no `Grounding:` line), the whole-repository redirect (no `Grounding:` line), and the refusal list (D9)
+  **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Symbol outside graph coverage", "Non-call-tree form is not graph-backed", "Tree tool failure after fresh check", "Ambiguous symbol asks instead of guessing", "Whole-repository redirect has no disclosure line", "Disclosure line present on every sketching answer"
   **Design decisions**: D2, D5, D9
   **Dependencies**: 2.3
   **Size**: S
 
-- [ ] Checkpoint: run `skills/tests/explain-code`, confirm every `references/<form>.md` cited in SKILL.md exists, review diff
+- [x] Checkpoint: run `skills/tests/explain-code`, confirm every `references/<form>.md` cited in SKILL.md exists, review diff
 
-- [ ] 2.6 Add `"explain-code": {"distribution": "portable"}` to `skills/install-manifest.json` `skills`, plus `cross_skill_dependencies` `"explain-code": ["codebase-atlas", "refresh-architecture"]`
-  **Spec scenarios**: skill-workflow "Manifest validation passes"
+- [x] 2.6 Add `"explain-code": {"distribution": "portable"}` to `skills/install-manifest.json` `skills`, plus `cross_skill_dependencies` `"explain-code": ["codebase-atlas", "refresh-architecture"]`
+  **Spec scenarios**: skill-workflow "Manifest validation passes", "Manifest declares portable distribution and atlas dependencies", "Sibling skill paths use skill-base-dir form"
   **Design decisions**: D1
   **Dependencies**: 2.5
   **Size**: XS
 
-- [ ] 2.7 Add `"tests/explain-code"` to `testpaths` in `skills/pyproject.toml`
+- [x] 2.7 Add `"tests/explain-code"` to `testpaths` in `skills/pyproject.toml`
   **Spec scenarios**: skill-workflow "Tests collected by the default sweep"
   **Design decisions**: —
   **Dependencies**: 2.1
   **Size**: XS
 
-- [ ] 2.8 (conditional) Author three scenario fixtures under `skills/tests/explain-code/scenarios/` in the trajectory-scenario harness format if that harness is present in the checkout; otherwise record "harness absent" in the session log
+- [x] 2.8 (conditional) Author three scenario fixtures under `skills/tests/explain-code/scenarios/` in the trajectory-scenario harness format if that harness is present in the checkout; otherwise record "harness absent" in the session log
   **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Whole-repository question redirected"
   **Design decisions**: D7
   **Dependencies**: 2.5
   **Size**: S
 
-- [ ] Checkpoint: run `bash skills/install.sh --check` and `skills/.venv/bin/python -m pytest skills/tests/explain-code`, verify scope stayed inside the package's write_allow
+- [x] Checkpoint: run `bash skills/install.sh --check` and `skills/.venv/bin/python -m pytest skills/tests/explain-code`, verify scope stayed inside the package's write_allow
 
 ## Phase 3 — Integration (package `wp-integration`)
 
-- [ ] 3.1 Merge the `wp-atlas-tree` and `wp-skill` package branches into the feature branch, resolving any overlap in `skills/install-manifest.json`
+- [x] 3.1 Merge the `wp-atlas-tree` and `wp-skill` package branches into the feature branch, resolving any overlap in `skills/install-manifest.json`
   **Spec scenarios**: —
   **Design decisions**: —
   **Dependencies**: 1.5, 2.7, 2.8
   **Size**: XS
 
-- [ ] 3.2 Regenerate the runtime mirrors with `bash skills/install.sh --mode rsync --deps none --python-tools none`
+- [x] 3.2 Regenerate the runtime mirrors with `bash skills/install.sh --mode rsync --deps none --python-tools none`
   **Spec scenarios**: skill-workflow "Manifest validation passes"
   **Design decisions**: —
   **Dependencies**: 3.1
   **Size**: XS
 
-- [ ] 3.3 Record "Phase 0b shipped: `/explain-code` question-driven explainer" in `docs/proposals/codebase-visualization-tool.md` delivery status
+- [x] 3.3 Record "Phase 0b shipped: `/explain-code` question-driven explainer" in `docs/proposals/codebase-visualization-tool.md` delivery status
   **Spec scenarios**: —
   **Design decisions**: —
   **Dependencies**: 3.2
   **Size**: XS
 
-- [ ] 3.4 Run the full verification block from `design.md`: `pytest skills/tests/codebase-atlas skills/tests/explain-code skills/tests/install_sh`, `openspec validate add-visual-code-explainer --strict`, `bash skills/install.sh --check`, and the two-run `cmp` determinism check
+- [x] 3.4 Run the full verification block from `design.md`: `pytest skills/tests/codebase-atlas skills/tests/explain-code skills/tests/install_sh`, `openspec validate add-visual-code-explainer --strict`, `bash skills/install.sh --check`, and the two-run `cmp` determinism check
   **Spec scenarios**: all
   **Design decisions**: all
   **Dependencies**: 3.3
   **Size**: S
 
-- [ ] Checkpoint: review cumulative diff against `tasks.md`; every change maps to a task
+- [x] Checkpoint: review cumulative diff against `tasks.md`; every change maps to a task
 
-- [ ] 3.5 Append the Implement phase record to `session-log.md` via `PhaseRecord.write_both()`
+- [x] 3.5 Append the Implement phase record to `session-log.md` via `PhaseRecord.write_both()`
   **Spec scenarios**: —
   **Design decisions**: —
   **Dependencies**: 3.4
diff --git a/openspec/changes/add-visual-code-explainer/work-packages.yaml b/openspec/changes/add-visual-code-explainer/work-packages.yaml
index cc739615..f876fdfc 100644
--- a/openspec/changes/add-visual-code-explainer/work-packages.yaml
+++ b/openspec/changes/add-visual-code-explainer/work-packages.yaml
@@ -3,7 +3,7 @@ schema_version: 1
 feature:
   id: add-visual-code-explainer
   title: "Visual code explainer — explain-code skill grounded through codebase-atlas --tree"
-  plan_revision: 1
+  plan_revision: 6
   created_by: claude-code
 
 contracts:
@@ -23,12 +23,12 @@ defaults:
   min_trust_level: 2
 
 packages:
-  # ── wp-atlas-tree — the only new code: --tree export in codebase-atlas (tasks 1.1–1.4)
+  # ── wp-atlas-tree — the only new code: --tree export in codebase-atlas (tasks 1.1–1.5)
   - package_id: wp-atlas-tree
     title: "codebase-atlas --tree symbol export"
     task_type: backend
     description: |
-      Tasks 1.1–1.4: tests first, then atlas_tree.py (BFS over call-typed symbolEdges, target
+      Tasks 1.1–1.5: tests first, then atlas_tree.py (BFS over call-typed symbolEdges, target
       resolution, formatter, coverage footer) and the --tree/--hops/--direction flags in
       build_atlas.py; SKILL.md flag-table row; flag tuple in test_skill_md.py.
       Design D3, D4, D8. Spec: codebase-analysis "Atlas Symbol Tree Export".
@@ -91,17 +91,18 @@ packages:
         - "atlas_tests_green"
         - "tree_deterministic"
 
-  # ── wp-skill — the prompt-only skill, its references, tests, and distribution wiring (tasks 2.1–2.6)
+  # ── wp-skill — the prompt-only skill, its references, tests, and distribution wiring (tasks 2.1–2.8)
   - package_id: wp-skill
     title: "explain-code skill, references, tests, manifest and testpaths wiring"
     task_type: docs
     description: |
-      Tasks 2.1–2.6: test_skill_md.py first (explicit frontmatter keys, references resolve,
+      Tasks 2.1–2.8: test_skill_md.py first (explicit frontmatter keys, references resolve,
       tail block, ≤150-line guard), then SKILL.md index, five references/<form>.md files
       with humanlayer-attributed examples and the grounding reference (D2, D5, D9), the
-      three deterministic behavioural tests (D7), and install-manifest.json / pyproject.toml
-      entries. Runs in parallel with wp-atlas-tree; the grounding reference documents the
-      --tree contract from design D3 rather than importing the implementation.
+      three deterministic behavioural tests (D7), install-manifest.json / pyproject.toml
+      entries (2.6–2.7), and conditional trajectory-harness fixtures (2.8). Runs in
+      parallel with wp-atlas-tree; the grounding reference documents the --tree contract
+      from design D3 rather than importing the implementation.
     role: docs-implementer
     archetype: implementer
     priority: 1
@@ -163,15 +164,15 @@ packages:
         - "skill_tests_green"
         - "manifest_valid"
 
-  # ── wp-integration — mirrors, docs, full suite, spec validation (tasks 3.1–3.4)
+  # ── wp-integration — mirrors, docs, full suite, spec validation (tasks 3.1–3.5)
   - package_id: wp-integration
     title: "Integration — regenerate mirrors, update codeviz proposal, full verification"
     task_type: integration
     description: |
-      Tasks 3.1–3.4: merge both package branches; run skills/install.sh --mode rsync to
+      Tasks 3.1–3.5: merge both package branches; run skills/install.sh --mode rsync to
       regenerate .claude/skills and .agents/skills; record Phase 0b in
       docs/proposals/codebase-visualization-tool.md; run the full skills test sweep and
-      openspec validate --strict; append the session log.
+      openspec validate --strict; append the Implement phase record to the session log.
     role: integrator
     archetype: integrator
     priority: 2
diff --git a/skills/codebase-atlas/SKILL.md b/skills/codebase-atlas/SKILL.md
index 0f9fcbbe..86846dd8 100644
--- a/skills/codebase-atlas/SKILL.md
+++ b/skills/codebase-atlas/SKILL.md
@@ -39,6 +39,9 @@ graph is wrong or narrow, the atlas says so rather than hiding it.
 | `--json-only` | Print the view-model as JSON; render nothing |
 | `--no-coverage` | Skip the on-disk coverage scan (faster, drops the banner) |
 | `--graph PATH` | Read a different graph artifact |
+| `--tree TARGET` | Print an indented call/callee tree for a symbol or file |
+| `--hops N` | Hop depth for `--tree` (default 2, max 4) |
+| `--direction in\|out\|both` | Callers, callees, or both for `--tree` (default out) |
 
 ## Usage
 
@@ -47,6 +50,7 @@ runtime copy in any consumer repository:
 
 ```bash
 python3 "<skill-base-dir>/scripts/build_atlas.py" $ARGUMENTS
+python3 "<skill-base-dir>/scripts/build_atlas.py" --tree acquire_lock --hops 2
 ```
 
 Requires only the Python standard library. In *this* repository the Makefile wraps
diff --git a/skills/codebase-atlas/scripts/atlas_tree.py b/skills/codebase-atlas/scripts/atlas_tree.py
new file mode 100644
index 00000000..4a2e7ed1
--- /dev/null
+++ b/skills/codebase-atlas/scripts/atlas_tree.py
@@ -0,0 +1,365 @@
+"""Symbol call-tree text export for ``build_atlas.py --tree``.
+
+Walks ``call``-typed ``symbolEdges`` from ``build_view_model()`` and prints an
+indented tree. Stdlib only. See design D3/D4/D8 of add-visual-code-explainer.
+"""
+
+from __future__ import annotations
+
+import sys
+from dataclasses import dataclass, field
+from typing import Any, Literal
+
+RootKind = Literal["symbol", "module"]
+Direction = Literal["in", "out", "both"]
+
+MAX_HOPS = 4
+DEFAULT_HOPS = 2
+
+
+@dataclass(frozen=True, slots=True)
+class ResolveOk:
+    kind: RootKind
+    id: str
+
+
+@dataclass(frozen=True, slots=True)
+class ResolveNotFound:
+    pass
+
+
+@dataclass(frozen=True, slots=True)
+class ResolveAmbiguous:
+    candidates: tuple[str, ...]
+
+
+ResolveResult = ResolveOk | ResolveNotFound | ResolveAmbiguous
+
+
+@dataclass(slots=True)
+class TreeNode:
+    id: str
+    name: str
+    file: str
+    line: int
+    kind: str
+    cycle: bool = False
+    more: int = 0
+    children: list[TreeNode] = field(default_factory=list)
+
+
+def resolve_target(view: dict[str, Any], target: str) -> ResolveResult:
+    """Resolve ``target`` as exact id, unique name, then module file/basename."""
+    symbols = view.get("symbols") or []
+    by_id = {s["id"]: s for s in symbols if s.get("id")}
+
+    if target in by_id:
+        return ResolveOk(kind="symbol", id=target)
+
+    name_hits = sorted(
+        (s["id"] for s in symbols if s.get("name") == target),
+        key=lambda i: i,
+    )
+    if len(name_hits) == 1:
+        return ResolveOk(kind="symbol", id=name_hits[0])
+    if len(name_hits) > 1:
+        return ResolveAmbiguous(candidates=tuple(name_hits))
+
+    modules = view.get("modules") or []
+    basename = target.rsplit("/", 1)[-1]
+    module_hits = [
+        m for m in modules
+        if m.get("file") == target or m.get("file") == basename or m.get("key") == target
+    ]
+    # Prefer exact file path match over basename when both could apply.
+    exact = [m for m in module_hits if m.get("file") == target or m.get("key") == target]
+    chosen = exact[0] if len(exact) == 1 else (module_hits[0] if len(module_hits) == 1 else None)
+    if chosen is None and len(module_hits) > 1:
+        # Multiple modules share the basename across languages — treat as ambiguous
+        # via their keys so the caller can ask.
+        return ResolveAmbiguous(
+            candidates=tuple(sorted(m["key"] for m in module_hits))
+        )
+    if chosen is not None:
+        return ResolveOk(kind="module", id=chosen["key"])
+
+    return ResolveNotFound()
+
+
+def _symbol_index(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
+    return {s["id"]: s for s in (view.get("symbols") or []) if s.get("id")}
+
+
+def _module_index(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
+    return {m["key"]: m for m in (view.get("modules") or []) if m.get("key")}
+
+
+def _call_adjacency(
+    view: dict[str, Any],
+) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
+    """Return (out_adj, in_adj) over call edges only, neighbours sorted."""
+    out_adj: dict[str, list[str]] = {}
+    in_adj: dict[str, list[str]] = {}
+    symbols = _symbol_index(view)
+    for edge in view.get("symbolEdges") or []:
+        if edge.get("ty") != "call":
+            continue
+        src, dst = edge.get("s"), edge.get("t")
+        if src not in symbols or dst not in symbols:
+            continue
+        out_adj.setdefault(src, []).append(dst)
+        in_adj.setdefault(dst, []).append(src)
+
+    def _sort_unique(adj: dict[str, list[str]]) -> dict[str, list[str]]:
+        sorted_adj: dict[str, list[str]] = {}
+        for node, neigh in adj.items():
+            uniq = sorted(set(neigh), key=lambda i: (symbols[i]["name"], i))
+            sorted_adj[node] = uniq
+        return sorted_adj
+
+    return _sort_unique(out_adj), _sort_unique(in_adj)
+
+
+def _enrich_symbols(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
+    """Attach ``file`` onto each symbol from its module for formatting."""
+    modules = _module_index(view)
+    out: dict[str, dict[str, Any]] = {}
+    for sym in view.get("symbols") or []:
+        sid = sym.get("id")
+        if not sid:
+            continue
+        mod = modules.get(sym.get("module") or "")
+        enriched = dict(sym)
+        enriched["file"] = (mod or {}).get("file") or ""
+        out[sid] = enriched
+    return out
+
+
+def _node_from_symbol(sym: dict[str, Any], *, cycle: bool = False, more: int = 0) -> TreeNode:
+    return TreeNode(
+        id=sym["id"],
+        name=str(sym.get("name") or sym["id"]),
+        file=str(sym.get("file") or ""),
+        line=int(sym.get("line") or 0),
+        kind=str(sym.get("kind") or "symbol"),
+        cycle=cycle,
+        more=more,
+    )
+
+
+def _node_from_module(mod: dict[str, Any]) -> TreeNode:
+    file = str(mod.get("file") or "")
+    name = file.rsplit("/", 1)[-1] if file else str(mod.get("key") or "module")
+    return TreeNode(
+        id=mod["key"],
+        name=name,
+        file=file,
+        line=1,
+        kind="module",
+    )
+
+
+def _walk_symbol(
+    root_id: str,
+    *,
+    hops: int,
+    direction: Literal["in", "out"],
+    out_adj: dict[str, list[str]],
+    in_adj: dict[str, list[str]],
+    symbols: dict[str, dict[str, Any]],
+) -> TreeNode:
+    adj = out_adj if direction == "out" else in_adj
+
+    def expand(node_id: str, depth: int, path: frozenset[str]) -> TreeNode:
+        sym = symbols[node_id]
+        if node_id in path:
+            return _node_from_symbol(sym, cycle=True)
+        neighbours = adj.get(node_id) or []
+        if depth >= hops:
+            return _node_from_symbol(sym, more=len(neighbours))
+        children = [
+            expand(nid, depth + 1, path | {node_id})
+            for nid in neighbours
+            if nid in symbols
+        ]
+        node = _node_from_symbol(sym)
+        node.children = children
+        return node
+
+    return expand(root_id, 0, frozenset())
+
+
+def _walk_module(
+    module_key: str,
+    *,
+    hops: int,
+    direction: Literal["in", "out"],
+    out_adj: dict[str, list[str]],
+    in_adj: dict[str, list[str]],
+    symbols: dict[str, dict[str, Any]],
+    modules: dict[str, dict[str, Any]],
+) -> TreeNode:
+    mod = modules[module_key]
+    root = _node_from_module(mod)
+    member_ids = sorted(
+        (sid for sid, sym in symbols.items() if sym.get("module") == module_key),
+        key=lambda i: (symbols[i]["name"], i),
+    )
+    if hops < 1:
+        root.more = len(member_ids)
+        return root
+
+    adj = out_adj if direction == "out" else in_adj
+
+    def expand_symbol(node_id: str, depth: int, path: frozenset[str]) -> TreeNode:
+        sym = symbols[node_id]
+        if node_id in path:
+            return _node_from_symbol(sym, cycle=True)
+        neighbours = adj.get(node_id) or []
+        if depth >= hops:
+            return _node_from_symbol(sym, more=len(neighbours))
+        children = [
+            expand_symbol(nid, depth + 1, path | {node_id})
+            for nid in neighbours
+            if nid in symbols
+        ]
+        node = _node_from_symbol(sym)
+        node.children = children
+        return node
+
+    # Hop 1 = module's own symbols; subsequent hops follow call edges.
+    root.children = [expand_symbol(sid, 1, frozenset()) for sid in member_ids]
+    return root
+
+
+def walk(
+    view: dict[str, Any],
+    root: ResolveOk,
+    *,
+    hops: int = DEFAULT_HOPS,
+    direction: Direction = "out",
+) -> TreeNode | tuple[TreeNode, TreeNode]:
+    """BFS-shaped recursive walk. ``both`` returns ``(callees_tree, callers_tree)``."""
+    symbols = _enrich_symbols(view)
+    modules = _module_index(view)
+    out_adj, in_adj = _call_adjacency(view)
+    hops = max(0, hops)
+
+    def one(dir_: Literal["in", "out"]) -> TreeNode:
+        if root.kind == "module":
+            return _walk_module(
+                root.id,
+                hops=hops,
+                direction=dir_,
+                out_adj=out_adj,
+                in_adj=in_adj,
+                symbols=symbols,
+                modules=modules,
+            )
+        return _walk_symbol(
+            root.id,
+            hops=hops,
+            direction=dir_,
+            out_adj=out_adj,
+            in_adj=in_adj,
+            symbols=symbols,
+        )
+
+    if direction == "both":
+        return one("out"), one("in")
+    return one(direction)  # type: ignore[arg-type]
+
+
+def format_tree_node(node: TreeNode, *, indent: int = 0) -> list[str]:
+    pad = "  " * indent
+    suffix = ""
+    if node.cycle:
+        suffix = "  (cycle)"
+    elif node.more:
+        suffix = f"  (+{node.more} more)"
+    line = f"{pad}{node.name}  ({node.file}:{node.line})  [{node.kind}]{suffix}"
+    lines = [line]
+    if not node.cycle:
+        for child in node.children:
+            lines.extend(format_tree_node(child, indent=indent + 1))
+    return lines
+
+
+def format_tree(
+    tree: TreeNode | tuple[TreeNode, TreeNode],
+    *,
+    direction: Direction = "out",
+) -> str:
+    if direction == "both":
+        callees, callers = tree  # type: ignore[misc]
+        lines = ["callees:"]
+        lines.extend(format_tree_node(callees, indent=0))
+        lines.append("callers:")
+        lines.extend(format_tree_node(callers, indent=0))
+        return "\n".join(lines) + "\n"
+    assert isinstance(tree, TreeNode)
+    return "\n".join(format_tree_node(tree)) + "\n"
+
+
+def footer(view: dict[str, Any]) -> str:
+    """Coverage footer matching the page banner percentages.
+
+    Always ``graph @ <sha7> · <list> covered`` so the D5 disclosure mapping
+    (copy after ``· `` / before trailing `` covered``) stays well-defined even
+    when the coverage list is empty.
+    """
+    sha = str((view.get("meta") or {}).get("gitSha") or "")
+    sha7 = sha[:7]
+    cov = view.get("coverage") or []
+    parts = [
+        f"{c['language']} {c['percent']}%"
+        for c in sorted(cov, key=lambda x: x["language"])
+    ]
+    return f"graph @ {sha7} · {' / '.join(parts)} covered"
+
+
+def clamp_hops(hops: int) -> tuple[int, bool]:
+    """Return (effective_hops, was_clamped).
+
+    Values above ``MAX_HOPS`` clamp to the max (design D3). Negative values
+    floor at 0 so a bad CLI int cannot invert the depth check.
+    """
+    if hops > MAX_HOPS:
+        return MAX_HOPS, True
+    if hops < 0:
+        return 0, True
+    return hops, False
+
+
+def render_tree(
+    view: dict[str, Any],
+    target: str,
+    *,
+    hops: int = DEFAULT_HOPS,
+    direction: Direction = "out",
+    include_footer: bool = True,
+    err_file=None,
+) -> tuple[int, str]:
+    """High-level entry used by ``build_atlas.main``.
+
+    Returns ``(exit_code, stdout_text)``. Messages for 2/3 go to ``err_file``.
+    """
+    err = err_file if err_file is not None else sys.stderr
+    hops, clamped = clamp_hops(hops)
+    if clamped:
+        print(f"note: --hops clamped to {hops}", file=err)
+
+    resolved = resolve_target(view, target)
+    if isinstance(resolved, ResolveNotFound):
+        print("not found", file=err)
+        return 2, ""
+    if isinstance(resolved, ResolveAmbiguous):
+        for cand in resolved.candidates:
+            print(cand, file=err)
+        return 3, ""
+
+    tree = walk(view, resolved, hops=hops, direction=direction)
+    text = format_tree(tree, direction=direction)
+    if include_footer:
+        text += footer(view) + "\n"
+    return 0, text
diff --git a/skills/codebase-atlas/scripts/build_atlas.py b/skills/codebase-atlas/scripts/build_atlas.py
index e0285201..a8b02717 100644
--- a/skills/codebase-atlas/scripts/build_atlas.py
+++ b/skills/codebase-atlas/scripts/build_atlas.py
@@ -8,8 +8,8 @@ Usage::
     python build_atlas.py --output /tmp/a.html  # write elsewhere
     python build_atlas.py --json-only           # emit the view-model, skip rendering
 
-Exit codes follow the convention the other architecture producers use:
-``0`` success or fresh, ``1`` input/IO error, ``2`` drift detected in check mode.
+Exit codes: ``0`` success or fresh, ``1`` input/IO error, ``2`` drift in
+``--check`` mode or ``--tree`` target not found, ``3`` ``--tree`` ambiguous target.
 """
 
 from __future__ import annotations
@@ -25,6 +25,7 @@ sys.path.insert(0, str(Path(__file__).resolve().parent))
 
 from atlas_model import AtlasInputError, build_view_model, load_graph  # noqa: E402
 from atlas_render import render_page  # noqa: E402
+from atlas_tree import DEFAULT_HOPS, render_tree  # noqa: E402
 
 DEFAULT_GRAPH = Path("docs/architecture-analysis/architecture.graph.json")
 DEFAULT_OUTPUT = Path("docs/architecture-analysis/atlas/index.html")
@@ -67,6 +68,18 @@ def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
         "--no-coverage", action="store_true",
         help="Skip the on-disk coverage scan (faster; drops the coverage banner).",
     )
+    parser.add_argument(
+        "--tree", metavar="TARGET", default=None,
+        help="Print an indented call tree for TARGET (symbol id, unique name, or file) instead of HTML.",
+    )
+    parser.add_argument(
+        "--hops", type=int, default=DEFAULT_HOPS,
+        help=f"Hop depth for --tree (default {DEFAULT_HOPS}, max 4).",
+    )
+    parser.add_argument(
+        "--direction", choices=("in", "out", "both"), default="out",
+        help="Edge direction for --tree: callees (out), callers (in), or both (default out).",
+    )
     return parser.parse_args(argv)
 
 
@@ -84,6 +97,18 @@ def main(argv: list[str] | None = None) -> int:
         print(f"error: {exc}", file=sys.stderr)
         return 1
 
+    if args.tree is not None:
+        code, text = render_tree(
+            payload,
+            args.tree,
+            hops=args.hops,
+            direction=args.direction,
+            include_footer=not args.no_coverage,
+        )
+        if text:
+            sys.stdout.write(text)
+        return code
+
     if args.json_only:
         json.dump(payload, sys.stdout, indent=2, sort_keys=True)
         sys.stdout.write("\n")
diff --git a/skills/explain-code/SKILL.md b/skills/explain-code/SKILL.md
new file mode 100644
index 00000000..2bc9421a
--- /dev/null
+++ b/skills/explain-code/SKILL.md
@@ -0,0 +1,68 @@
+---
+name: explain-code
+description: Answers a narrow question about how a specific piece of code works or connects with the smallest visual form that makes the point — grounded in the architecture graph when fresh. Use when the user asks how code flows or relates; use codebase-atlas for whole-repository views.
+category: Architecture
+tags: [architecture, visualization, explanation, mermaid, grounding]
+user_invocable: true
+related:
+  - codebase-atlas
+  - refresh-architecture
+---
+
+# Explain Code
+
+Answer a narrow question about the code with a small picture and a few sentences.
+Catalogue and brevity rules are adapted from humanlayer's MIT-licensed `show-me`
+skill; grounding and coverage disclosure are this repository's addition.
+
+**Deferred in v1:** no HTML files, no writing any file, no browser.
+
+## Rules
+
+1. Skip the preamble; keep prose brief (≤3 sentences beside the visual).
+2. Pick the **smallest** catalogue form that makes the key point.
+3. Include only the calls, files, and boundaries the current question needs.
+4. Place each visual next to the short text it supports.
+5. Every **sketching** reply ends with exactly one `Grounding:` line (see
+   `references/grounding.md`). Clarification and whole-repo redirects do not.
+
+## Catalogue
+
+| Form | When | Reference |
+|---|---|---|
+| Call tree | Control flow / who calls whom | `references/call-tree.md` |
+| Component tree | UI / module structure with paths | `references/component-tree.md` |
+| File tree | Responsibility layout | `references/file-tree.md` |
+| Sequence | Interaction over time (Mermaid) | `references/sequence.md` |
+| Structural diff | What changed in shape | `references/structural-diff.md` |
+
+## Grounding (summary)
+
+Before a **call tree**, check freshness with
+`python3 "<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py" --check`
+(exit `0` only = fresh). When fresh, obtain callers/callees from
+`python3 "<skill-base-dir>/../codebase-atlas/scripts/build_atlas.py" --tree …`.
+Never run `--ensure` or the analysis pipeline. Full contract, disclosure forms,
+ungrounded reasons, and exemptions: `references/grounding.md`.
+
+Whole-repository questions → name `/codebase-atlas` and stop (no `Grounding:` line).
+
+## Common Rationalizations
+
+| Rationalization | Why it's wrong |
+|---|---|
+| "I'll sketch from memory — the graph is probably fine" | Ungrounded trees look identical to grounded ones; run `--check` and disclose. |
+| "A whole-repo atlas page answers a narrow question better" | That is `/codebase-atlas`'s job; this skill stops and redirects. |
+| "I'll refresh the graph myself so the answer is grounded" | The skill never runs `--ensure` or the pipeline; disclose ungrounded instead. |
+
+## Red Flags
+
+- A sketching reply with no final `Grounding:` line.
+- A call tree that invents symbols not returned by `--tree` after a fresh check.
+- The skill invoked `--ensure` or opened/wrote a file.
+
+## Verification
+
+1. Confirm the catalogue form matches the question and cites a `references/*.md`.
+2. Confirm sketching replies end with exactly one `Grounding:` line (or an exempt clarification/redirect).
+3. Confirm sibling invocations use `<skill-base-dir>/../codebase-atlas/` and `<skill-base-dir>/../refresh-architecture/`.
diff --git a/skills/explain-code/references/call-tree.md b/skills/explain-code/references/call-tree.md
new file mode 100644
index 00000000..0d6add6d
--- /dev/null
+++ b/skills/explain-code/references/call-tree.md
@@ -0,0 +1,29 @@
+# Call tree
+
+## When to use
+
+Show runtime control flow — who calls whom for the current question.
+
+## Smallest-view rule
+
+Keep only the calls the question needs. Prefer `--hops 1` or `2`; widen only when
+a missing hop hides the point. Prefer one direction (`out` or `in`) over `both`.
+
+## Worked example
+
+Adapted from humanlayer's MIT `show-me` skill
+([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):
+
+```text
+submitForm
+  createSession
+    persistPrompt
+    launchAgent
+  navigateToSession
+```
+
+## File locations
+
+Every node should carry its file (and line when known), e.g.
+`createSession  (sessions/create.ts:40)`. When grounded, copy paths from
+`build_atlas.py --tree` output rather than inventing them.
diff --git a/skills/explain-code/references/component-tree.md b/skills/explain-code/references/component-tree.md
new file mode 100644
index 00000000..08e0c122
--- /dev/null
+++ b/skills/explain-code/references/component-tree.md
@@ -0,0 +1,28 @@
+# Component tree
+
+## When to use
+
+Show UI or module structure with the state and boundaries that matter for the
+question.
+
+## Smallest-view rule
+
+Collapse children that are not on the path of the question. One focused subtree
+beats a full app tree.
+
+## Worked example
+
+Adapted from humanlayer's MIT `show-me` skill
+([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):
+
+```tsx
+<SessionPage> (apps/example/src/routes/session.tsx)
+  useSessionEvents()
+  <SessionToolbar>
+    <RunSkillButton> (packages/ui)
+```
+
+## File locations
+
+Attach the defining file path in parentheses on each node that the reader might
+open. Read those files before sketching; this form is not graph-backed.
diff --git a/skills/explain-code/references/file-tree.md b/skills/explain-code/references/file-tree.md
new file mode 100644
index 00000000..91a2aaa6
--- /dev/null
+++ b/skills/explain-code/references/file-tree.md
@@ -0,0 +1,28 @@
+# File tree
+
+## When to use
+
+Show responsibility layout across a few directories — what lives where for this
+question.
+
+## Smallest-view rule
+
+Stop at the depth that names the responsibility. One-line comments on folders
+beat nested file dumps.
+
+## Worked example
+
+Adapted from humanlayer's MIT `show-me` skill
+([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):
+
+```text
+src/
+├── commands/       # parses user actions
+├── sessions/       # owns session state
+└── transport/      # sends API requests
+```
+
+## File locations
+
+The tree *is* the location map. Prefer real paths from the checkout; read the
+directories before sketching. Not graph-backed.
diff --git a/skills/explain-code/references/grounding.md b/skills/explain-code/references/grounding.md
new file mode 100644
index 00000000..cfec817b
--- /dev/null
+++ b/skills/explain-code/references/grounding.md
@@ -0,0 +1,112 @@
+# Grounding and coverage disclosure
+
+This reference is the contract for when a sketch is graph-backed versus
+source-read, and for the mandatory `Grounding:` line on every sketching reply.
+
+## Freshness (`--check`)
+
+Before sketching a **call tree**, run:
+
+```bash
+python3 "<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py" --check
+```
+
+Treat **exit code `0` alone** as fresh. Do **not** use `build_atlas.py --check`
+(that flag means HTML-page drift, exit `2`).
+
+Before invoking `--check`:
+
+- If the `--check` script or the architecture graph file is missing → reason
+  `graph absent` (do not spawn `--check`).
+
+When spawning `--check`:
+
+- OSError / exception before an exit code → `graph check failed`
+- Non-zero exit (including `1` for stale provenance) → `graph stale`
+
+The skill **never** runs `--ensure` or the analysis pipeline.
+
+## Call tree from `--tree`
+
+When `--check` exited `0`, obtain callers/callees with:
+
+```bash
+python3 "<skill-base-dir>/../codebase-atlas/scripts/build_atlas.py" --tree <target> [--hops N] [--direction in|out|both]
+```
+
+Build the call tree **only** from nodes that `--tree` prints. Do not invent
+symbols.
+
+`--tree` exits:
+
+| Exit | Meaning | Skill reaction |
+|---|---|---|
+| `0` | Tree printed | Grounded call tree + grounded disclosure |
+| `1` | Input/IO error | Source fallback; reason `graph check failed` |
+| `2` | Target not found | Source fallback; reason `symbol not in graph` |
+| `3` | Ambiguous name (sorted candidate ids on stderr) | List candidates and **ask**; no source fallback; **no** `Grounding:` line |
+| other / spawn failure | Unexpected | Source fallback; reason `graph check failed` |
+
+After a fresh `--check`, if `--tree` cannot be spawned or returns any exit other
+than `0`/`2`/`3`, use `graph check failed`.
+
+## Disclosure line (sketching replies only)
+
+Exactly one final line. Two reply shapes are **exempt** and MUST NOT carry
+`Grounding:`:
+
+1. **Ambiguous-symbol clarification** (`--tree` exit `3`)
+2. **Whole-repository redirect** (name `/codebase-atlas` and stop)
+
+### Grounded call tree
+
+Take the `--tree` footer (`graph @ <sha7> · <list> covered`). Copy the substring
+**after** `· ` and **before** the trailing ` covered`, then re-append ` covered`.
+Use `; ` after the sha (not the footer's `·`):
+
+```text
+Grounding: graph @ <sha7>; <language> <percent>% / <language> <percent>% covered
+```
+
+Preserve language order, ` / ` separators, and one-decimal percents. Percentages
+are the atlas optimistic upper bound (basename matching).
+
+### Ungrounded / non-graph-backed
+
+```text
+Grounding: source read, unverified (<reason>)
+```
+
+`<reason>` is exactly one of these, **first match wins**:
+
+1. `graph absent` — script or graph missing before `--check`
+2. `graph check failed` — `--check` could not be spawned; or after a fresh
+   `--check`, `--tree` could not be spawned, exits `1`, or returns any exit
+   other than `0`/`2`/`3`
+3. `graph stale` — `--check` ran and exited non-zero
+4. `symbol not in graph` — `--tree` exited `2`
+5. `form not graph-backed` — catalogue form other than a call tree
+
+Only a call tree built from `--tree` after a fresh `--check` may use the
+grounded form.
+
+## Non-call-tree forms
+
+For component tree, file tree, sequence, or structural diff: **read the
+relevant source files before sketching**, then disclose with
+`form not graph-backed`. Never claim the grounded `graph @` form for those.
+
+## Ask, don't guess
+
+On `--tree` exit `3`, print the candidate ids from stderr and ask which was
+meant. Do not pick one. Do not fall back to source for a guessed symbol.
+
+## Whole-repository questions
+
+Name `/codebase-atlas` and stop. No visual. No `Grounding:` line.
+
+## Refusals (D9)
+
+- Do not write files. Text and Mermaid go inline in the reply only.
+- Do not open a browser.
+- Do not answer "show me the whole architecture"; redirect as above.
diff --git a/skills/explain-code/references/sequence.md b/skills/explain-code/references/sequence.md
new file mode 100644
index 00000000..c9923d67
--- /dev/null
+++ b/skills/explain-code/references/sequence.md
@@ -0,0 +1,31 @@
+# Sequence diagram
+
+## When to use
+
+Show interaction, control flow, or data flow across participants over time.
+
+## Smallest-view rule
+
+Limit participants and messages to the current question. Prefer one happy path
+unless the question is about an error branch.
+
+## Worked example
+
+Adapted from humanlayer's MIT `show-me` skill
+([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):
+
+```mermaid
+sequenceDiagram
+    participant User
+    participant UI
+    participant Daemon
+    User->>UI: choose command
+    UI->>Daemon: send expanded prompt
+    Daemon-->>UI: stream result
+```
+
+## File locations
+
+Name the implementing file beside a participant or in the prose next to the
+diagram (e.g. `Daemon — daemon/server.ts`). Read those files before sketching.
+Not graph-backed.
diff --git a/skills/explain-code/references/structural-diff.md b/skills/explain-code/references/structural-diff.md
new file mode 100644
index 00000000..948a3652
--- /dev/null
+++ b/skills/explain-code/references/structural-diff.md
@@ -0,0 +1,43 @@
+# Structural diff
+
+## When to use
+
+The point is what changed in shape, and the surrounding structure already exists.
+
+## Smallest-view rule
+
+Diff only the nodes the question cares about. Match the diff shape to the topic
+(component vs file layout).
+
+## Worked example
+
+Adapted from humanlayer's MIT `show-me` skill
+([source](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)):
+
+For a component change:
+
+```diff
+ <SessionPage>
+   useSessionEvents()
+   <SessionToolbar>
++    <RunSkillButton />
+   <SessionTimeline>
++    <SkillResultCard />
+```
+
+For a file-layout change:
+
+```diff
+ src/
+ ├── commands/
++│   └── show-me.ts       # expands the slash command
+ ├── sessions/
+-└── transport.ts
++└── transport/
++    ├── client.ts
+```
+
+## File locations
+
+Paths in the diff are the locations. Confirm them by reading the tree before
+sketching. Not graph-backed.
diff --git a/skills/install-manifest.json b/skills/install-manifest.json
index 2967a2c7..6ff04eb4 100644
--- a/skills/install-manifest.json
+++ b/skills/install-manifest.json
@@ -61,6 +61,10 @@
       "parallel-infrastructure",
       "session-log"
     ],
+    "explain-code": [
+      "codebase-atlas",
+      "refresh-architecture"
+    ],
     "explore-feature": [
       "coordination-bridge",
       "refresh-architecture",
@@ -262,6 +266,9 @@
     "expedite": {
       "distribution": "portable"
     },
+    "explain-code": {
+      "distribution": "portable"
+    },
     "explore-feature": {
       "distribution": "portable"
     },
diff --git a/skills/pyproject.toml b/skills/pyproject.toml
index ac478628..3e3ec420 100644
--- a/skills/pyproject.toml
+++ b/skills/pyproject.toml
@@ -98,6 +98,7 @@ testpaths = [
     "tests/bug-scrub",
     "tests/tech-debt-analysis",
     "tests/cleanup-feature",
+    "tests/explain-code",
     "tests/explore-feature",
     "tests/parallel-infrastructure",
     "tests/project-context-runtime",
diff --git a/skills/tests/codebase-atlas/test_atlas_tree.py b/skills/tests/codebase-atlas/test_atlas_tree.py
new file mode 100644
index 00000000..98c67e82
--- /dev/null
+++ b/skills/tests/codebase-atlas/test_atlas_tree.py
@@ -0,0 +1,386 @@
+"""Tests for ``atlas_tree`` / ``build_atlas.py --tree`` (add-visual-code-explainer)."""
+
+from __future__ import annotations
+
+import copy
+import io
+import json
+import re
+import time
+from pathlib import Path
+
+import build_atlas
+import pytest
+from atlas_model import build_view_model
+from atlas_tree import MAX_HOPS, footer, render_tree, resolve_target
+
+COMMITTED_GRAPH = Path("docs/architecture-analysis/architecture.graph.json")
+LINE_RE = re.compile(
+    r"^(?P<indent> *)(?P<name>\S.*?)\s{2}\((?P<file>[^:]*):(?P<line>\d+)\)\s{2}\[(?P<kind>[^\]]+)\]"
+)
+
+
+def _view(tiny_graph: dict, tmp_path: Path, *, measure: bool = True) -> dict:
+    """Write graph + touch source files so coverage measure can run."""
+    graph_path = tmp_path / "g.json"
+    graph_path.write_text(json.dumps(tiny_graph), encoding="utf-8")
+    for node in tiny_graph["nodes"]:
+        f = node.get("file") or ""
+        if f and f != "(unfiled)":
+            p = tmp_path / f
+            if not p.exists():
+                p.write_text("# stub\n", encoding="utf-8")
+    return build_view_model(tiny_graph, tmp_path, measure=measure)
+
+
+def _tree_lines(text: str) -> list[str]:
+    return [ln for ln in text.splitlines() if ln and not ln.startswith("graph @") and ln not in ("callees:", "callers:")]
+
+
+def _parsed_nodes(text: str) -> list[dict]:
+    nodes = []
+    for ln in _tree_lines(text):
+        m = LINE_RE.match(ln)
+        assert m, f"unparseable tree line: {ln!r}"
+        nodes.append(m.groupdict())
+    return nodes
+
+
+class TestCalleesOrdering:
+    def test_callees_sorted_by_name_then_id(self, tiny_graph: dict, tmp_path: Path) -> None:
+        view = _view(tiny_graph, tmp_path, measure=False)
+        code, text = render_tree(view, "py:api.handler", hops=1, direction="out", include_footer=False)
+        assert code == 0
+        # handler calls _helper and save — sorted by name: _helper then save
+        body = _tree_lines(text)
+        assert body[0].startswith("handler  (api.py:10)  [function]")
+        assert "_helper" in body[1]
+        assert "save" in body[2]
+
+
+class TestCallersHopCap:
+    def test_callers_hops_1_and_more_suffix(self, tiny_graph: dict, tmp_path: Path) -> None:
+        graph = copy.deepcopy(tiny_graph)
+        # Give handler an inbound caller so hops=1 marks it with (+1 more).
+        graph["nodes"].append(
+            {
+                "id": "py:api.entry",
+                "kind": "function",
+                "language": "python",
+                "name": "entry",
+                "file": "api.py",
+                "span": {"start": 1, "end": 2},
+                "tags": [],
+                "signatures": {},
+            }
+        )
+        graph["edges"].append(
+            {
+                "from": "py:api.entry",
+                "to": "py:api.handler",
+                "type": "call",
+                "confidence": "high",
+                "evidence": "ast:call:handler",
+            }
+        )
+        view = _view(graph, tmp_path, measure=False)
+        code, text = render_tree(view, "py:store.save", hops=1, direction="in", include_footer=False)
+        assert code == 0
+        body = _tree_lines(text)
+        assert body[0].startswith("save  (store.py:5)  [function]")
+        caller_lines = body[1:]
+        assert len(caller_lines) == 2
+        handler_line = next(ln for ln in caller_lines if "handler" in ln)
+        assert "(+1 more)" in handler_line
+
+
+class TestNonCallEdgesExcluded:
+    def test_import_edges_never_appear(self, tiny_graph: dict, tmp_path: Path) -> None:
+        graph = copy.deepcopy(tiny_graph)
+        # B is save; add import edge handler -> something that must not show as callee
+        graph["nodes"].append(
+            {
+                "id": "py:store.imported",
+                "kind": "function",
+                "language": "python",
+                "name": "imported",
+                "file": "store.py",
+                "span": {"start": 40, "end": 41},
+                "tags": [],
+                "signatures": {},
+            }
+        )
+        graph["edges"].append(
+            {
+                "from": "py:api.handler",
+                "to": "py:store.imported",
+                "type": "import",
+                "confidence": "high",
+                "evidence": "import",
+            }
+        )
+        view = _view(graph, tmp_path, measure=False)
+        code, text = render_tree(view, "handler", hops=2, direction="out", include_footer=False)
+        assert code == 0
+        assert "imported" not in text
+        assert "save" in text
+
+
+class TestCyclePrintedOnce:
+    def test_cycle_suffix(self, tiny_graph: dict, tmp_path: Path) -> None:
+        graph = copy.deepcopy(tiny_graph)
+        # create

[diff truncated to fit packet budget; use Read/Grep for the remainder]

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- openspec/changes/add-visual-code-explainer/design.md
- openspec/changes/add-visual-code-explainer/proposal.md
- openspec/changes/add-visual-code-explainer/tasks.md
- openspec/changes/add-visual-code-explainer/work-packages.yaml
- skills/explain-code/references/call-tree.md
- skills/explain-code/references/component-tree.md
- skills/explain-code/references/file-tree.md
- skills/explain-code/references/grounding.md
- skills/explain-code/references/sequence.md
- skills/explain-code/references/structural-diff.md
- skills/install-manifest.json
- skills/pyproject.toml

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
- openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

#### Group 3 (default: `skills/*/SKILL.md`)
Applies to:
- skills/codebase-atlas/SKILL.md
- skills/explain-code/SKILL.md

Check that the workflow steps match what the referenced scripts actually accept (flags, return shapes). Verify examples are runnable as written. Flag instructions that silently assume coordinator, tier, or environment state without stating the fallback.

#### Group 4 (default: `skills/*/scripts/*.py`)
Applies to:
- skills/codebase-atlas/scripts/atlas_tree.py
- skills/codebase-atlas/scripts/build_atlas.py

Check for unhandled exceptions on the failure paths this module is meant to guard (network, subprocess, file I/O). Verify a function documented as "never raises" actually catches every exception class it claims to. Flag silent behavior changes to existing callers.

#### Group 5 (default: `skills/tests/**`)
Applies to:
- skills/tests/codebase-atlas/test_atlas_tree.py
- skills/tests/codebase-atlas/test_skill_md.py
- skills/tests/explain-code/test_behaviour.py
- skills/tests/explain-code/test_skill_md.py

Same standard as scripts/tests/: verify the test would fail if the behavior it targets were broken. Check that fixture paths use openspec_paths.change_dir rather than a literal openspec/changes/<id>/ path where the guide requires it.

### Spec excerpts
#### specs/codebase-analysis/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/skill-workflow/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

### Open ledger items
- [37] Design decisions D8 (module name / atlas_tree.py helper) and D9 (refusal list) are referenced by tasks 1.1, 1.3, 2.2, 2.5 in tasks.md and by packages wp-atlas-tree and wp-skill in work-packages.yaml, but design.md only defines decisions up through D7. Neither D8 nor D9 is documented in design.md.
- [38] Task 2.5 in tasks.md outlines writing references/grounding.md including handling tree tool failures and mapping them to 'graph check failed', but omits skill-workflow scenario 'Tree tool failure after fresh check' from its Spec scenarios list, despite enumerating all other grounding scenarios.
- [39] In .review-ledger/ledger.json, item 13 is marked as status 'retired' with retired_reason 'plan-review-adjudication-round-4', which conflicts with reviews/parked-disagreements.json where item 13 is tracked as an active parked disagreement.
- [40] The Atlas Symbol Tree Export requires module targets to resolve from either a full file path or a basename, but the only module-resolution scenario and task 1.1 cover a basename. The ordered resolution contract is also not exercised where a unique symbol name collides with a module path or basename. Add scenarios and tests for full-path resolution and the unique-name-before-module precedence.
- [41] The Atlas Symbol Tree Export says traversal SHALL use only the Python standard library and make no network requests, but no WHEN/THEN scenario or task verifies either constraint. This violates the rule that every SHALL/MUST be scenario-covered and leaves the security and operability boundary unenforced.
- [42] The grounding requirement maps failure to spawn or run run_architecture.py --check to `graph check failed`, but no scenario has that WHEN condition. The stale/absent scenario covers non-zero exits and missing files, while the tool-failure scenario covers only build_atlas.py --tree after a successful check. Task 2.2 merely checks that the reason token exists, so an implementation could misclassify a check spawn failure and still pass. Add a dedicated check-spawn-failure scenario and behavioral assertion.
- [43] The atlas requirement says every node line SHALL contain name, file, line, and kind, but the format scenario validates only the root line. Task 1.1 checks all printed nodes only by `(name, file)`, so incorrect line numbers or kinds on descendants would pass. Extend the scenario and test to validate every emitted node against all four fixture fields.
- [44] In `proposal.md` What Changes, the Frontmatter bullet lists six keys (`name, description, category, tags, user_invocable, related`) but then says the skill test asserts the "four surviving keys". Spec/tasks/D6 require explicit assertions for all six. The count is wrong and can mis-brief implementers of task 2.1.
- [45] Round-4 added skill-workflow scenario "Tree tool failure after fresh check" and task 2.2 asserts the grounding reference documents tree-tool-failure → `graph check failed`, but task 2.5 (author `references/grounding.md`) Spec scenarios still omit that scenario. The normative mapping lives in grounding.md; leaving it off 2.5 orphans the new scenario from the implementation task that must encode it.
- [46] Round-2 distribution scenarios remain under-wired in tasks: "Manifest declares portable distribution and atlas dependencies" is not listed on task 2.6 (only "Manifest validation passes"), and "Sibling skill paths use skill-base-dir form" is not listed on any task (2.5 documents `<skill-base-dir>/../codebase-atlas/` but does not cite the scenario). Implementers can miss the portable/deps and path-form acceptance checks.
- [47] skill-workflow scenario "Stale or absent graph falls back to source" THEN allows reason `graph check failed`, but its WHEN (`--check` exits non-zero, or script/graph missing) cannot produce that reason under the first-match table: missing script/graph → `graph absent`; non-zero `--check` → `graph stale`. D5's `--check` spawn/OSError → `graph check failed` path has no WHEN/THEN coverage ("Tree tool failure after fresh check" only covers `--tree` after a fresh `--check`).
- [48] In `session-log.md` Plan Review, `### Next Steps` still sits between round-1 and round-2 decisions and says to IMPLEMENT if converged, while rounds 3–4 adjudications (remove slimmed converge-result, extend task 1.1 scenarios, `--tree` failure → `graph check failed`, require source read for non-call-tree forms, proposal disclosure alignment; `plan_revision` → 6) are recorded only in `plan-findings.md`. The session log is the standing decision record and is stale mid-review.
- [49] Plan Review decision 2 in `session-log.md` understates `graph check failed` as "spawn failure or `--tree` exit 1", while D5 and the skill-workflow requirement also map any `--tree` exit other than `0`/`2`/`3` (after a fresh `--check`) to that reason. Drift from the closed decision table.
- [50] The parked disagreement item 13 indicates that 'Atlas target resolution SHALL accepts a module file path or basename, but only basename is covered' - this suggests the file path resolution aspect may not be fully tested or implemented despite being specified.
- [51] In specs/codebase-analysis/spec.md, the Atlas Symbol Tree Export requirement states '<target> SHALL resolve as exact node id, then unique symbol name, then module file path or basename' but the corresponding test scenarios only cover basename resolution explicitly. The 'Target resolution precedence' scenario mentions resolving exact node id before symbol name but doesn't explicitly test file path resolution.
- [52] While the design document mentions that task 1.1 covers file path resolution, there's no explicit scenario in the codebase-analysis spec that specifically tests module file path resolution as a distinct case from basename resolution.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.