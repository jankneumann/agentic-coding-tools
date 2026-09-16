## Review Round 1

The packet is complete; do not explore the repo for missing artifacts.

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
index c93dd0ff..72d47e64 100644
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
 
@@ -57,8 +60,12 @@ build_atlas.py --tree <target> [--hops N] [--direction out|in|both] [--graph PAT
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
@@ -70,20 +77,39 @@ fixed graph and arguments (NFR "Determinism").
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
 
 Every reply ends with exactly one line, never omitted, never collapsed:
 
-- grounded: `Grounding: graph @ <sha7>; python 14% / sql 37% covered`
-- ungrounded: `Grounding: source read, unverified (graph <stale|absent|check failed>)`
+- grounded call tree:
+  `Grounding: graph @ <sha7>; python 14.4% / sql 37.0% covered`
+  The coverage list (everything after `· ` and before the trailing
+  ` covered` in the `--tree` footer from D3) is copied verbatim — same
+  language order, ` / ` separators, and one-decimal percents — so the
+  disclosure and footer cannot drift. The line uses `; ` after the sha
+  (not the footer's `·`) and always starts with `Grounding:`.
+- ungrounded / non-graph-backed:
+  `Grounding: source read, unverified (<reason>)`
+  where `<reason>` is exactly one of:
+  - `graph stale` — `run_architecture.py --check` exited non-zero
+  - `graph absent` — graph file or `--check` script missing
+  - `graph check failed` — `--check` could not run (error/exception)
+  - `symbol not in graph` — `--tree` exited `2`
+  - `form not graph-backed` — reply used a catalogue form other than a
+    call tree (component/file/sequence/structural-diff are model-authored)
 
-The grounded form copies the footer `--tree` prints (D3) so the two cannot
-drift. The percentages are the atlas's optimistic upper bound and the reference
-file says so.
+Only a call tree built from `--tree` after a fresh `--check` may use the
+grounded form. The percentages are the atlas's optimistic upper bound and
+the grounding reference says so.
 
 ### D6 — Frontmatter without `triggers:`; explicit key test
 
@@ -106,8 +132,9 @@ the checkout; otherwise as pytest tests marked `e2e`. Independently of the
 harness, three **deterministic** tests always run in CI and encode the same
 three behaviours at the level the prompt can be checked without an LLM:
 
-1. `SKILL.md` instructs the disclosure line for both grounded and ungrounded
-   paths (D5 strings present in the grounding reference).
+1. `SKILL.md` / grounding reference instruct the disclosure line for grounded
+   and ungrounded paths (D5 strings and the full ungrounded reason set present
+   in the grounding reference).
 2. `SKILL.md` instructs redirecting whole-repository questions to
    `/codebase-atlas` (string present, and the atlas is in `related:`).
 3. `SKILL.md` instructs never running `--ensure` or the analysis pipeline
diff --git a/openspec/changes/add-visual-code-explainer/plan-findings.md b/openspec/changes/add-visual-code-explainer/plan-findings.md
new file mode 100644
index 00000000..bd7e6058
--- /dev/null
+++ b/openspec/changes/add-visual-code-explainer/plan-findings.md
@@ -0,0 +1,24 @@
+# Plan Findings — add-visual-code-explainer
+
+## Iteration 1 (2026-09-16) — autopilot-plan-iterate
+
+`openspec validate add-visual-code-explainer --strict` passed before and after fixes.
+
+### Findings
+
+| # | Dimension | Criticality | Finding | Resolution |
+|---|---|---|---|---|
+| 1 | consistency / assumptions | high | D2 and proposal Selected Approach claimed `run_architecture.py --check` uses exit `2` for drift. Live contract: exit `0` fresh, exit `1` when provenance is not fresh. Exit `2` belongs to `build_atlas.py --check` (stale HTML page). | Corrected D2, D4 aside, proposal Selected Approach, session-log decision 2. Spec already used "exit 0 only / non-zero". |
+| 2 | consistency / clarity | medium | D5 ungrounded template `(graph <stale\|absent\|check failed>)` omitted `symbol not in graph` and did not define disclosure for non-call-tree forms; "copies footer verbatim" conflicted with `Grounding:` + `;` vs footer `·`. | Expanded D5 reason set; clarified footer→disclosure mapping; added skill-workflow scenario "Non-call-tree form is not graph-backed"; updated tasks 2.2/2.5. |
+| 3 | consistency / parallelizability | medium | `work-packages.yaml` package descriptions omitted tasks 1.5, 2.7–2.8, and 3.5 even though `tasks.md` and merge depends_on require them. | Widened WP task ranges to 1.1–1.5, 2.1–2.8, 3.1–3.5; bumped `plan_revision` to 2. |
+| 4 | consistency / clarity | medium | Proposal "What Changes" still promised behavioural scenarios in "replay-harness shape"; D7 already specified deterministic CI checks + optional harness. | Aligned proposal Tests bullet with D7. |
+| 5 | completeness | medium | Session-log open question still asked about `show-me` vs `explain-code` after Gate 2 rename; Context still said `skills/show-me/`. | Closed OQ; fixed Context naming. |
+
+### Left as low (no churn)
+
+- Proposal NFR node/edge counts (1,903 / 1,199) slightly behind current committed graph (~1,953 / 1,228); timing NFR still uses the committed graph.
+- `tiny_graph` has no cycle/import edges by default; task 1.1 already builds derived fixtures.
+
+### Outcome
+
+Medium+ findings fixed in plan artifacts only. Ready for PLAN_REVIEW.
diff --git a/openspec/changes/add-visual-code-explainer/proposal.md b/openspec/changes/add-visual-code-explainer/proposal.md
index 6e209922..70ea4344 100644
--- a/openspec/changes/add-visual-code-explainer/proposal.md
+++ b/openspec/changes/add-visual-code-explainer/proposal.md
@@ -57,7 +57,8 @@ that gates them, and the analysis that motivated this change is fresh.
   the existing `symbolEdges` adjacency from `build_view_model()` and prints an indented tree
   with file path and line per node, hop-capped at 4 to match the page's slider.
   Output is byte-stable for a fixed graph. Exit codes follow the existing
-  contract (`0` ok, `1` input error, `2` symbol not found).
+  contract (`0` ok, `1` input error, `2` symbol not found) plus `3` for an
+  ambiguous name, which the skill resolves by asking rather than guessing.
 - **Frontmatter written for the post-`rewrite-skill-frontmatter` world.** The new
   `SKILL.md` carries `name, description, category, tags, user_invocable, related`
   with a description that states capability and trigger condition in third
@@ -72,12 +73,15 @@ that gates them, and the analysis that motivated this change is fresh.
   `"tests/explain-code"`. Runtime mirrors regenerate via `skills/install.sh`.
 - **Tests.** `skills/tests/explain-code/test_skill_md.py` (frontmatter parses,
   explicit key presence, references resolve, related resolve, tail block
-  present) plus **three behavioural scenarios** in the replay-harness shape that
-  `invert-skill-test-suite-to-behavioural` prescribes: (1) a grounded question
-  yields a call tree whose nodes all exist in the fixture graph and a
-  `graph @` disclosure; (2) a stale graph yields a source-read sketch with an
-  `unverified` disclosure; (3) a whole-repo question is redirected to
-  `/codebase-atlas` rather than answered with a giant tree.
+  present) plus **three deterministic behavioural checks** in
+  `test_behaviour.py` that encode the behaviours
+  `invert-skill-test-suite-to-behavioural` wants without blocking on that
+  change (0/10 tasks today): (1) grounding reference contains both D5
+  disclosure forms; (2) `SKILL.md` redirects whole-repo questions to
+  `/codebase-atlas`; (3) `SKILL.md` forbids `--ensure` / the analysis
+  pipeline. The "grounded call tree invents no symbols" assertion lives in
+  `tests/codebase-atlas/test_atlas_tree.py` (fixture node ids only). Optional
+  trajectory-harness fixtures are task 2.8 when the harness is present.
   `skills/tests/codebase-atlas/` gains `test_atlas_tree.py` and the flag tuple
   in `test_skill_md.py` gains `--tree`.
 
@@ -171,8 +175,9 @@ disclosure line makes that visible rather than hiding it.
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
 
@@ -198,7 +203,7 @@ affected.
 - New: `skills/explain-code/SKILL.md`, `skills/explain-code/references/*.md`,
   `skills/tests/explain-code/`.
 - Modified: `skills/codebase-atlas/scripts/build_atlas.py` (new flag and a
-  `tree.py` helper module — no bare-named `models`/`utils` modules, per
+  `atlas_tree.py` helper module — no bare-named `models`/`utils` modules, per
   `collect-uncollected-skill-tests`), `skills/codebase-atlas/SKILL.md` (flag
   table row only), `skills/tests/codebase-atlas/test_skill_md.py`,
   `skills/install-manifest.json`, `skills/pyproject.toml`,
diff --git a/openspec/changes/add-visual-code-explainer/session-log.md b/openspec/changes/add-visual-code-explainer/session-log.md
index ac09731b..4a47f0cb 100644
--- a/openspec/changes/add-visual-code-explainer/session-log.md
+++ b/openspec/changes/add-visual-code-explainer/session-log.md
@@ -9,8 +9,8 @@
 
 ### Decisions
 1. **Adopt show-me's catalogue as prose; ground only the call tree in code** `architectural: code-visualization` — The catalogue works because it is a prompt, so it stays a prompt. Determinism is bought only where it pays: the call tree, via a new codebase-atlas --tree flag over the existing symbolEdges adjacency. A scripted explainer for every form would duplicate the atlas view-model and generate_views Mermaid emitters in a third skill, and sequence diagrams need runtime ordering the static graph lacks.
-2. **Freshness is decided by the existing run_architecture.py --check contract** `architectural: code-visualization` — Exit 0 alone means fresh; exit 1, exit 2, a missing script, or a missing graph all mean ungrounded. Re-deriving freshness from git_sha in prose would create a second, weaker definition alongside the architecture-refresh contract the atlas already mirrors. The skill never runs --ensure or the pipeline.
-3. **Mandatory one-line coverage disclosure on every answer** `architectural: code-visualization` — The codeviz proposal's standing principle is that a visualisation must disclose its own coverage. The grounded form copies the --tree footer verbatim so the two cannot drift; the ungrounded form names the reason (stale, absent, check failed, symbol not in graph). This is the improvement on show-me, which trusts model memory silently.
+2. **Freshness is decided by the existing run_architecture.py --check contract** `architectural: code-visualization` — Exit 0 alone means fresh; any non-zero exit (the script returns 1 when provenance is not fresh), a missing script, or a missing graph all mean ungrounded. Do not confuse with build_atlas.py --check (exit 2 = stale HTML page). Re-deriving freshness from git_sha in prose would create a second, weaker definition alongside the architecture-refresh contract. The skill never runs --ensure or the pipeline.
+3. **Mandatory one-line coverage disclosure on every answer** `architectural: code-visualization` — The codeviz proposal's standing principle is that a visualisation must disclose its own coverage. The grounded form copies the --tree footer coverage list (after `· `) so percents cannot drift; the ungrounded form names an exact reason (`graph stale|absent|check failed`, `symbol not in graph`, or `form not graph-backed`). This is the improvement on show-me, which trusts model memory silently.
 4. **Frontmatter omits triggers; the skill test asserts keys explicitly** `architectural: skill-authoring` — rewrite-skill-frontmatter deletes triggers from all 52 skills, but the canonical spec and REQUIRED_FRONTMATTER_KEYS still require it. Asserting the six surviving keys directly instead of calling assert_required_keys_present makes the skill valid in both merge orderings, so this change does not block on that one.
 5. **Behavioural scenarios are CI-wired deterministically, harness-optional** `architectural: skill-authoring` — invert-skill-test-suite-to-behavioural wants three behavioural scenarios per user-invocable skill but is 0/10 tasks. Three deterministic prompt-content tests plus the fixture-node assertion in test_atlas_tree.py encode the same behaviours today; harness fixtures are a conditional task.
 
@@ -25,7 +25,7 @@
 - Accepted Coverage percentages are an optimistic upper bound over Exact path-based coverage because The analyzer records bare basenames, so one graph name can match several on-disk files. Fixing node identity is a separate prerequisite change (issue #275); the reference file states the number is a ceiling.
 
 ### Open Questions
-- [ ] Skill directory name is show-me, crediting humanlayer's MIT source. Confirm at Gate 2 if explain-code or sketch-code is preferred.
+- [x] Skill directory name — resolved at Gate 2: `explain-code` (not `show-me` / `sketch-code`). `show-me` stays the upstream humanlayer credit only.
 - [ ] The trajectory-scenario harness format for task 2.8 was not verified present in this checkout; the task is conditional and records 'harness absent' if it is not.
 - [ ] Whether the follow-up change should widen add-visual-plan-review's 'OpenSpec proposals only' boundary or create a separate general-artifact capability for HTML output.
 
@@ -41,5 +41,21 @@
 - `openspec/changes/add-visual-code-explainer/work-packages.yaml` — wp-atlas-tree and wp-skill in parallel, wp-integration last
 
 ### Context
-Planned a question-driven visual code explainer skill adopting humanlayer's MIT show-me format catalogue and brevity rules, grounded in this repo's architecture graph. Selected the prompt-only approach: skills/show-me/ ships no scripts, and the single piece of new code is a --tree symbol export in codebase-atlas that walks the existing symbolEdges adjacency. Scope was cut at discovery from six items to two (skill + --tree); HTML output, the feature-slice call tree, diff rendering, the plan-review playbook, and the atlas description rewrite were deferred to a follow-up.
+Planned a question-driven visual code explainer skill adopting humanlayer's MIT show-me format catalogue and brevity rules, grounded in this repo's architecture graph. Selected the prompt-only approach: skills/explain-code/ ships no scripts, and the single piece of new code is a --tree symbol export in codebase-atlas that walks the existing symbolEdges adjacency. Scope was cut at discovery from six items to two (skill + --tree); HTML output, the feature-slice call tree, diff rendering, the plan-review playbook, and the atlas description rewrite were deferred to a follow-up.
+
+## Phase: Plan Iterate (2026-09-16)
+
+**Agent**: autopilot-plan-iterate | **Session**: N/A
+
+### Decisions
+1. **Correct freshness exit-code docs to the live `run_architecture.py --check` contract** `architectural: code-visualization` — Exit 0 only is fresh; non-zero (typically 1 for stale provenance) is ungrounded. Atlas `--check` exit 2 is a different CLI and must not be mixed into D2.
+2. **Pin exact ungrounded disclosure reasons including non-call-tree forms** `architectural: code-visualization` — Reasons are `graph stale|absent|check failed`, `symbol not in graph`, and `form not graph-backed`. Only `--tree`-backed call trees may use the grounded form.
+
+### Next Steps
+- Proceed to PLAN_REVIEW.
+
+### Relevant Files
+- `openspec/changes/add-visual-code-explainer/plan-findings.md` — iteration 1 findings table
+- `openspec/changes/add-visual-code-explainer/design.md` — D2/D4/D5 corrections
+- `openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md` — disclosure reason alignment
 
diff --git a/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md b/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
index e0c04fac..f5cd83f3 100644
--- a/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
+++ b/openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
@@ -2,7 +2,7 @@
 
 ### Requirement: Atlas Symbol Tree Export
 
-`skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional `--hops N` (default `2`, maximum `4`, larger values clamped with a stderr note) and `--direction out|in|both` (default `out`), and SHALL print an indented text tree to stdout instead of rendering the page. The traversal SHALL walk the symbol-level adjacency produced by `build_view_model()` (`symbolEdges`) restricted to edges whose `ty` is `call` — `import` and every other edge type are dependencies, not calls, and SHALL NOT appear as callers or callees — using only the Python standard library and making no network requests. Each line SHALL show `<name>  (<file>:<line>)  [<kind>]`, children SHALL be sorted by name then id, a node already on the current path SHALL be printed once with the suffix `(cycle)` and not expanded, and a parent whose children exceed `--hops` SHALL carry the suffix `(+<n> more)`. The output SHALL end with a footer `graph @ <sha7> · <language> <percent>% covered` per language present unless `--no-coverage` is given. `<target>` SHALL resolve as exact node id, then unique symbol name, then module file path or basename (rooting the tree at the module with its own symbols as hop 1). Exit codes SHALL be `0` success, `1` input or IO error, `2` target not found or ambiguous (candidates listed on stderr). Output SHALL be byte-identical across runs for a fixed graph and arguments.
+`skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional `--hops N` (default `2`, maximum `4`, larger values clamped with a stderr note) and `--direction out|in|both` (default `out`), and SHALL print an indented text tree to stdout instead of rendering the page. The traversal SHALL walk the symbol-level adjacency produced by `build_view_model()` (`symbolEdges`) restricted to edges whose `ty` is `call` — `import` and every other edge type are dependencies, not calls, and SHALL NOT appear as callers or callees — using only the Python standard library and making no network requests. Each line SHALL show `<name>  (<file>:<line>)  [<kind>]`, children SHALL be sorted by name then id, a node already on the current path SHALL be printed once with the suffix `(cycle)` and not expanded, and a parent whose children exceed `--hops` SHALL carry the suffix `(+<n> more)`. The output SHALL end with a single footer line `graph @ <sha7> · <language> <percent>% / <language> <percent>% covered`, one `<language> <percent>%` entry per language present, sorted by language name and joined with ` / `, with `<percent>` printed to exactly one decimal place as `Coverage.percent` returns it (for example `14.4%`, `37.0%`), unless `--no-coverage` is given. `<target>` SHALL resolve as exact node id, then unique symbol name, then module file path or basename (rooting the tree at the module with its own symbols as hop 1). Exit codes SHALL be `0` success, `1` input or IO error, `2` target not found, `3` target ambiguous (candidate ids listed on stderr, one per line, sorted). Output SHALL be byte-identical across runs for a fixed graph and arguments.
 
 #### Scenario: Callees tree for a symbol
 
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
 
diff --git a/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md b/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md
index bcb27546..aa909872 100644
--- a/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md
+++ b/openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md
@@ -31,7 +31,7 @@ The repository SHALL provide a user-invocable, prompt-only skill `explain-code`
 
 ### Requirement: Explainer Grounding and Coverage Disclosure
 
-Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh. When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that export returns. When stale, absent, or failing, the skill SHALL read source directly and label the sketch unverified. Every reply SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% covered …` when grounded, or `Grounding: source read, unverified (graph <stale|absent|check failed>)` when not. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.
+Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh (any non-zero exit means ungrounded; the script returns `1` when provenance is not fresh). When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that `build_atlas.py --tree` returns. When stale, absent, or failing, the skill SHALL read source directly and label the sketch unverified. Every reply SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% / <language> <percent>% covered` when grounded (coverage list copied verbatim from the `--tree` footer after its `· ` separator, including order and ` / ` separators), or `Grounding: source read, unverified (<reason>)` when not, where `<reason>` is one of `graph stale`, `graph absent`, `graph check failed`, `symbol not in graph`, or `form not graph-backed`. Only a call tree built from `--tree` after a fresh `--check` MAY use the grounded form; other catalogue forms SHALL use `form not graph-backed`. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.
 
 #### Scenario: Fresh graph grounds the call tree
 
@@ -43,14 +43,26 @@ Before sketching a call tree, the skill SHALL determine graph freshness by runni
 
 - **WHEN** `run_architecture.py --check` exits non-zero, or the script or graph file is missing
 - **THEN** the skill SHALL still answer, drawing the sketch from the source files it reads
-- **AND** the disclosure line SHALL read `Grounding: source read, unverified (graph <reason>)`
+- **AND** the disclosure line SHALL read `Grounding: source read, unverified (<reason>)` with reason `graph stale`, `graph absent`, or `graph check failed` as appropriate
 - **AND** the skill SHALL NOT invoke `--ensure` or the analysis pipeline
 
 #### Scenario: Symbol outside graph coverage
 
 - **WHEN** the graph is fresh but `build_atlas.py --tree` exits `2` (target not found) for the requested symbol
 - **THEN** the skill SHALL fall back to source reading for that symbol
-- **AND** the disclosure line SHALL use the unverified form with reason `symbol not in graph`
+- **AND** the disclosure line SHALL read `Grounding: source read, unverified (symbol not in graph)`
+
+#### Scenario: Non-call-tree form is not graph-backed
+
+- **WHEN** the skill answers with a catalogue form other than a call tree
+- **THEN** the disclosure line SHALL read `Grounding: source read, unverified (form not graph-backed)`
+- **AND** the skill SHALL NOT claim the grounded `graph @` form for that reply
+
+#### Scenario: Ambiguous symbol asks instead of guessing
+
+- **WHEN** the graph is fresh and `build_atlas.py --tree` exits `3` (ambiguous name) for the requested symbol
+- **THEN** the skill SHALL list the candidate ids from stderr and ask which one was meant
+- **AND** the skill SHALL NOT fall back to source reading or sketch a tree for any candidate
 
 #### Scenario: Disclosure line present on every answer
 
diff --git a/openspec/changes/add-visual-code-explainer/tasks.md b/openspec/changes/add-visual-code-explainer/tasks.md
index e7243d68..9d9a33d8 100644
--- a/openspec/changes/add-visual-code-explainer/tasks.md
+++ b/openspec/changes/add-visual-code-explainer/tasks.md
@@ -5,8 +5,8 @@ Within each phase, test tasks precede the implementation they verify (TDD RED 
 
 ## Phase 1 — `codebase-atlas --tree` export (package `wp-atlas-tree`)
 
-- [ ] 1.1 Write `skills/tests/codebase-atlas/test_atlas_tree.py` against the `tiny_graph` fixture: callees tree ordering, callers with `--hops 1` and `(+n more)` suffix, `(cycle)` printed once, basename target roots at the module, unknown target exits `2`, ambiguous name exits `2` with candidates on stderr, byte-identical output across two runs, footer percentages equal `Coverage.percent`, output contains only fixture node ids, a mixed-edge fixture (a copy of `tiny_graph` plus one `import` edge) proving import edges never appear as callers or callees, and a `≤ 2 s` timing test on the committed graph (skipped when absent)
-  **Spec scenarios**: codebase-analysis "Callees tree for a symbol", "Callers tree with hop cap", "Non-call edges are excluded", "Cycle is printed once", "File target gives the aggregated module view", "Unknown or ambiguous target exits 2", "Deterministic output", "Coverage footer matches the page banner"
+- [ ] 1.1 Write `skills/tests/codebase-atlas/test_atlas_tree.py` against the `tiny_graph` fixture: callees tree ordering, callers with `--hops 1` and `(+n more)` suffix, `(cycle)` printed once, basename target roots at the module, unknown target exits `2`, ambiguous name exits `3` with sorted candidates on stderr, byte-identical output across two runs, footer percentages equal `Coverage.percent`, output contains only fixture node ids, a mixed-edge fixture (a copy of `tiny_graph` plus one `import` edge) proving import edges never appear as callers or callees, and a `≤ 2 s` timing test on the committed graph (skipped when absent)
+  **Spec scenarios**: codebase-analysis "Callees tree for a symbol", "Callers tree with hop cap", "Non-call edges are excluded", "Cycle is printed once", "File target gives the aggregated module view", "Unknown target exits 2", "Ambiguous target exits 3", "Deterministic output", "Coverage footer matches the page banner"
   **Design decisions**: D3 (format), D4 (resolution), D7 (fixture-only nodes), D8 (module name)
   **Dependencies**: None
   **Size**: M
@@ -17,8 +17,8 @@ Within each phase, test tasks precede the implementation they verify (TDD RED 
   **Dependencies**: 1.1
   **Size**: M
 
-- [ ] 1.3 Wire `--tree`, `--hops`, `--direction` into `build_atlas.py` `parse_args()` and dispatch in `main()` after `build_view_model()` and before the render path, honouring `--no-coverage` and returning `0/1/2`
-  **Spec scenarios**: codebase-analysis "Unknown or ambiguous target exits 2", "Coverage footer matches the page banner"
+- [ ] 1.3 Wire `--tree`, `--hops`, `--direction` into `build_atlas.py` `parse_args()` and dispatch in `main()` after `build_view_model()` and before the render path, honouring `--no-coverage` and returning `0/1/2/3`
+  **Spec scenarios**: codebase-analysis "Unknown target exits 2", "Ambiguous target exits 3", "Coverage footer matches the page banner"
   **Design decisions**: D3, D8
   **Dependencies**: 1.2
   **Size**: S
@@ -47,8 +47,8 @@ Within each phase, test tasks precede the implementation they verify (TDD RED 
   **Dependencies**: None
   **Size**: S
 
-- [ ] 2.2 Write `skills/tests/explain-code/test_behaviour.py` — three deterministic behavioural checks: grounding reference contains both D5 disclosure forms; `SKILL.md` redirects whole-repository questions to `/codebase-atlas`; `SKILL.md` forbids `--ensure` and the analysis pipeline
-  **Spec scenarios**: skill-workflow "Disclosure line present on every answer", "Whole-repository question redirected", "Stale or absent graph falls back to source"
+- [ ] 2.2 Write `skills/tests/explain-code/test_behaviour.py` — three deterministic behavioural checks: grounding reference contains both D5 disclosure forms and the full ungrounded reason set (`graph stale|absent|check failed`, `symbol not in graph`, `form not graph-backed`); `SKILL.md` redirects whole-repository questions to `/codebase-atlas`; `SKILL.md` forbids `--ensure` and the analysis pipeline
+  **Spec scenarios**: skill-workflow "Disclosure line present on every answer", "Whole-repository question redirected", "Stale or absent graph falls back to source", "Non-call-tree form is not graph-backed"
   **Design decisions**: D2, D5, D7, D9
   **Dependencies**: None
   **Size**: S
@@ -67,8 +67,8 @@ Within each phase, test tasks precede the implementation they verify (TDD RED 
   **Dependencies**: 2.3
   **Size**: M
 
-- [ ] 2.5 Write `references/grounding.md` — the `--check` freshness command (D2), the `--tree` invocation via `<skill-base-dir>/../codebase-atlas/`, how to copy the footer into the disclosure line (D5), the symbol-not-in-graph fallback, the whole-repository redirect, and the refusal list (D9)
-  **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Symbol outside graph coverage", "Disclosure line present on every answer"
+- [ ] 2.5 Write `references/grounding.md` — the `--check` freshness command (D2: exit `0` only = fresh; non-zero ungrounded), the `--tree` invocation via `<skill-base-dir>/../codebase-atlas/`, how to map the footer coverage list into the `Grounding:` line (D5), the ungrounded reason set including `symbol not in graph` (exit `2`) and `form not graph-backed`, the ask-don't-guess rule for an ambiguous name (exit `3`), the whole-repository redirect, and the refusal list (D9)
+  **Spec scenarios**: skill-workflow "Fresh graph grounds the call tree", "Stale or absent graph falls back to source", "Symbol outside graph coverage", "Non-call-tree form is not graph-backed", "Ambiguous symbol asks instead of guessing", "Disclosure line present on every answer"
   **Design decisions**: D2, D5, D9
   **Dependencies**: 2.3
   **Size**: S
diff --git a/openspec/changes/add-visual-code-explainer/work-packages.yaml b/openspec/changes/add-visual-code-explainer/work-packages.yaml
index cc739615..fecb450c 100644
--- a/openspec/changes/add-visual-code-explainer/work-packages.yaml
+++ b/openspec/changes/add-visual-code-explainer/work-packages.yaml
@@ -3,7 +3,7 @@ schema_version: 1
 feature:
   id: add-visual-code-explainer
   title: "Visual code explainer — explain-code skill grounded through codebase-atlas --tree"
-  plan_revision: 1
+  plan_revision: 2
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

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- openspec/changes/add-visual-code-explainer/design.md
- openspec/changes/add-visual-code-explainer/plan-findings.md
- openspec/changes/add-visual-code-explainer/proposal.md
- openspec/changes/add-visual-code-explainer/session-log.md
- openspec/changes/add-visual-code-explainer/tasks.md
- openspec/changes/add-visual-code-explainer/work-packages.yaml

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/add-visual-code-explainer/specs/codebase-analysis/spec.md
- openspec/changes/add-visual-code-explainer/specs/skill-workflow/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

### Spec excerpts
#### specs/codebase-analysis/spec.md
## ADDED Requirements

### Requirement: Atlas Symbol Tree Export

`skills/codebase-atlas/scripts/build_atlas.py` SHALL accept `--tree <target>` with optional `--hops N` (default `2`, maximum `4`, larger values clamped with a stderr note) and `--direction out|in|both` (default `out`), and SHALL print an indented text tree to stdout instead of rendering the page. The traversal SHALL walk the symbol-level adjacency produced by `build_view_model()` (`symbolEdges`) restricted to edges whose `ty` is `call` — `import` and every other edge type are dependencies, not calls, and SHALL NOT appear as callers or callees — using only the Python standard library and making no network requests. Each line SHALL show `<name>  (<file>:<line>)  [<kind>]`, children SHALL be sorted by name then id, a node already on the current path SHALL be printed once with the suffix `(cycle)` and not expanded, and a parent whose children exceed `--hops` SHALL carry the suffix `(+<n> more)`. The output SHALL end with a single footer line `graph @ <sha7> · <language> <percent>% / <language> <percent>% covered`, one `<language> <percent>%` entry per language present, sorted by language name and joined with ` / `, with `<percent>` printed to exactly one decimal place as `Coverage.percent` returns it (for example `14.4%`, `37.0%`), unless `--no-coverage` is given. `<target>` SHALL resolve as exact node id, then unique symbol name, then module file path or basename (rooting the tree at the module with its own symbols as hop 1). Exit codes SHALL be `0` success, `1` input or IO error, `2` target not found, `3` target ambiguous (candidate ids listed on stderr, one per line, sorted). Output SHALL be byte-identical across runs for a fixed graph and arguments.

#### Scenario: Callees tree for a symbol

- **WHEN** `build_atlas.py --tree <symbol-id>` runs against a graph containing that symbol
- **THEN** stdout SHALL start with the symbol's line and list its callees indented two spaces per hop, sorted by name
- **AND** the exit code SHALL be `0`

#### Scenario: Callers tree with hop cap

- **WHEN** `--direction in --hops 1` is given for a symbol with callers two hops away
- **THEN** only direct callers SHALL be printed
- **AND** each printed caller that has further callers SHALL carry a `(+<n> more)` suffix

#### Scenario: Non-call edges are excluded

- **WHEN** the graph contains `A calls B` and `A imports C`, and `--tree A --direction both` runs
- **THEN** `B` SHALL be listed under `callees:`
- **AND** `C` SHALL NOT appear anywhere in the output

#### Scenario: Cycle is printed once

- **WHEN** the graph contains `A calls B` and `B calls A` and `--tree A --hops 4` runs
- **THEN** `A` SHALL appear under `B` exactly once with the suffix `(cycle)`
- **AND** it SHALL NOT be expanded further

#### Scenario: File target gives the aggregated module view

- **WHEN** `--tree <file-basename>` names a module in the graph
- **THEN** the root line SHALL be the module and hop 1 SHALL be the module's own symbols
- **AND** subsequent hops SHALL follow those symbols' `call` edges

#### Scenario: Unknown target exits 2

- **WHEN** `--tree` names a symbol that is not in the graph
- **THEN** the exit code SHALL be `2`
- **AND** stderr SHALL contain `not found`

#### Scenario: Ambiguous target exits 3

- **WHEN** `--tree` names a bare symbol name matching several node ids
- **THEN** the exit code SHALL be `3`, distinct from not-found
- **AND** stderr SHALL list the candidate ids, one per line, sorted

#### Scenario: Deterministic output

- **WHEN** the same `--tree` invocation runs twice against the same graph file
- **THEN** the two stdout outputs SHALL be byte-identical

#### Scenario: Coverage footer matches the page banner

- **WHEN** `--tree` runs without `--no-coverage`
- **THEN** the footer percentages SHALL equal the `Coverage.percent` values `build_view_model()` computes for the same repository root


#### specs/skill-workflow/spec.md
## ADDED Requirements

### Requirement: Visual Code Explainer Skill

The repository SHALL provide a user-invocable, prompt-only skill `explain-code` that answers a narrow question about the code with the smallest visual form that makes the key point clear, drawn from a fixed catalogue: indented call tree, component tree with file paths, file tree with one-line responsibility comments, Mermaid sequence diagram, and structural (tree) diff. The skill SHALL keep prose brief, SHALL place each visual next to the short text it supports, and SHALL include only the calls, files, and boundaries the current question needs. The skill's `SKILL.md` SHALL be an index of at most 150 lines that links directly to one `references/<form>.md` file per visual form, with no nested reference files. In this version the skill SHALL NOT write HTML files, SHALL NOT write any file, and SHALL NOT open a browser.

#### Scenario: Narrow question answered with the smallest visual

- **WHEN** a user asks how a specific function, module, or message path works or connects
- **THEN** the skill SHALL reply with exactly one visual form from the catalogue and at most three sentences of prose
- **AND** every node in the visual SHALL carry its file location

#### Scenario: Whole-repository question redirected

- **WHEN** a user asks for the whole architecture, the full dependency graph, or a repository-wide map
- **THEN** the skill SHALL NOT render a repository-wide tree
- **AND** it SHALL name `/codebase-atlas` as the tool for that question and stop

#### Scenario: Progressive disclosure layout

- **WHEN** the skill directory is inspected
- **THEN** `SKILL.md` SHALL be at most 150 lines
- **AND** each catalogue form SHALL have its own `references/<form>.md` reachable by a direct link from `SKILL.md`
- **AND** no reference file SHALL link to a further reference file

#### Scenario: No file or browser side effects

- **WHEN** the skill answers any question
- **THEN** it SHALL emit text and Mermaid inline in the reply only
- **AND** it SHALL NOT create, modify, or open any file

### Requirement: Explainer Grounding and Coverage Disclosure

Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh (any non-zero exit means ungrounded; the script returns `1` when provenance is not fresh). When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that `build_atlas.py --tree` returns. When stale, absent, or failing, the skill SHALL read source directly and label the sketch unverified. Every reply SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% / <language> <percent>% covered` when grounded (coverage list copied verbatim from the `--tree` footer after its `· ` separator, including order and ` / ` separators), or `Grounding: source read, unverified (<reason>)` when not, where `<reason>` is one of `graph stale`, `graph absent`, `graph check failed`, `symbol not in graph`, or `form not graph-backed`. Only a call tree built from `--tree` after a fresh `--check` MAY use the grounded form; other catalogue forms SHALL use `form not graph-backed`. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.

#### Scenario: Fresh graph grounds the call tree

- **WHEN** `run_architecture.py --check` exits `0` and the question names a symbol present in the graph
- **THEN** the call tree SHALL contain only nodes returned by `build_atlas.py --tree`
- **AND** the disclosure line SHALL read `Grounding: graph @ <sha7>; …` with per-language coverage percentages copied from the `--tree` footer

#### Scenario: Stale or absent graph falls back to source

- **WHEN** `run_architecture.py --check` exits non-zero, or the script or graph file is missing
- **THEN** the skill SHALL still answer, drawing the sketch from the source files it reads
- **AND** the disclosure line SHALL read `Grounding: source read, unverified (<reason>)` with reason `graph stale`, `graph absent`, or `graph check failed` as appropriate
- **AND** the skill SHALL NOT invoke `--ensure` or the analysis pipeline

#### Scenario: Symbol outside graph coverage

- **WHEN** the graph is fresh but `build_atlas.py --tree` exits `2` (target not found) for the requested symbol
- **THEN** the skill SHALL fall back to source reading for that symbol
- **AND** the disclosure line SHALL read `Grounding: source read, unverified (symbol not in graph)`

#### Scenario: Non-call-tree form is not graph-backed

- **WHEN** the skill answers with a catalogue form other than a call tree
- **THEN** the disclosure line SHALL read `Grounding: source read, unverified (form not graph-backed)`
- **AND** the skill SHALL NOT claim the grounded `graph @` form for that reply

#### Scenario: Ambiguous symbol asks instead of guessing

- **WHEN** the graph is fresh and `build_atlas.py --tree` exits `3` (ambiguous name) for the requested symbol
- **THEN** the skill SHALL list the candidate ids from stderr and ask which one was meant
- **AND** the skill SHALL NOT fall back to source reading or sketch a tree for any candidate

#### Scenario: Disclosure line present on every answer

- **WHEN** the skill produces any reply, grounded or not
- **THEN** the final line of the reply SHALL begin with `Grounding:`
- **AND** the reply SHALL contain exactly one such line

### Requirement: Explainer Frontmatter Without Triggers

The `explain-code` `SKILL.md` frontmatter SHALL declare `name`, `description`, `category: Architecture`, `tags`, `user_invocable: true`, and `related: [codebase-atlas, refresh-architecture]`, and SHALL NOT declare a `triggers:` key. The `description` SHALL state, in third person, both what the skill does and when to use it, including that whole-repository views belong to `codebase-atlas`. The skill's `test_skill_md.py` SHALL assert the declared keys explicitly rather than through the shared `assert_required_keys_present` helper while that helper still requires `triggers`, so the test passes whether or not `rewrite-skill-frontmatter` has landed. The `SKILL.md` SHALL end with the `## Common Rationalizations`, `## Red Flags`, and `## Verification` sections required of user-invocable skills.

#### Scenario: Frontmatter valid in both orderings

- **WHEN** `skills/tests/explain-code/test_skill_md.py` runs before or after `rewrite-skill-frontmatter` merges
- **THEN** it SHALL pass in both states
- **AND** it SHALL fail if any of `name`, `description`, `category`, `tags`, `user_invocable`, or `related` is missing or empty

#### Scenario: Description carries the trigger condition

- **WHEN** the frontmatter `description` is read
- **THEN** it SHALL name the capability (visual explanation of a specific piece of code) and the use condition (a narrow question about how code works or connects)
- **AND** it SHALL direct whole-repository requests to `codebase-atlas`

### Requirement: Explainer Distribution Wiring

`skills/install-manifest.json` SHALL declare `"explain-code": {"distribution": "portable"}` and a `cross_skill_dependencies` entry `"explain-code": ["codebase-atlas", "refresh-architecture"]`. `skills/pyproject.toml` `testpaths` SHALL list `tests/explain-code`. All runtime references from `explain-code` to sibling skills SHALL use the `<skill-base-dir>/../<skill>/` form.

#### Scenario: Manifest validation passes

- **WHEN** `skills/install.sh --check` runs after the skill is added
- **THEN** the manifest validator SHALL report zero errors
- **AND** every sibling reference in `skills/explain-code/**` SHALL be covered by the declared cross-skill dependencies

#### Scenario: Tests collected by the default sweep

- **WHEN** `skills/.venv/bin/python -m pytest` runs from `skills/` with no path arguments
- **THEN** tests under `skills/tests/explain-code/` SHALL be collected without import errors


### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.