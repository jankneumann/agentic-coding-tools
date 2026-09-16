## ADDED Requirements

### Requirement: Visual Code Explainer Skill

The repository SHALL provide a user-invocable, prompt-only skill `explain-code` that answers a narrow question about the code with the smallest visual form that makes the key point clear, drawn from a fixed catalogue: indented call tree, component tree with file paths, file tree with one-line responsibility comments, Mermaid sequence diagram, and structural (tree) diff. The skill SHALL keep prose brief, SHALL place each visual next to the short text it supports, and SHALL include only the calls, files, and boundaries the current question needs. The skill's `SKILL.md` SHALL be an index of at most 150 lines that links directly to one `references/<form>.md` file per visual form, with no nested reference files. In this version the skill SHALL NOT write HTML files, SHALL NOT write any file, and SHALL NOT open a browser.

#### Scenario: Narrow question answered with the smallest visual

- **WHEN** a user asks how a specific function, module, or message path works or connects, and the named target is resolvable without an ambiguous-symbol clarification
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
- **AND** it SHALL NOT create or modify any file, and SHALL NOT open a browser or otherwise present a user-facing file side effect
- **AND** it MAY read the architecture graph and source files read-only as part of grounding

### Requirement: Explainer Grounding and Coverage Disclosure

Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh (any non-zero exit means ungrounded; the script returns `1` when provenance is not fresh). When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that `build_atlas.py --tree` returns. When `--tree` exits `3` (ambiguous target), the skill SHALL list the candidate ids from stderr and ask which one was meant, and SHALL NOT fall back to source reading or sketch a tree. When stale, absent, or failing (including `--tree` exit `2`), the skill SHALL read source directly and label the sketch unverified. Every sketching reply (a catalogue visual was emitted) SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% / <language> <percent>% covered` when grounded (coverage list taken from the `--tree` footer by copying the substring after `· ` and before the trailing ` covered`, then re-appending ` covered`, preserving language order and ` / ` separators), or `Grounding: source read, unverified (<reason>)` when not, where `<reason>` is chosen by first-match order: `graph absent` (script or graph missing before `--check`), `graph check failed` (`--check` could not be spawned, or `--tree` exits `1` after a fresh `--check`), `graph stale` (`--check` ran and exited non-zero), `symbol not in graph` (`--tree` exited `2`), or `form not graph-backed` (non-call-tree catalogue form). Ambiguous-symbol clarification replies and whole-repository redirect replies SHALL NOT carry a `Grounding:` line. Only a call tree built from `--tree` after a fresh `--check` MAY use the grounded form; other catalogue forms SHALL use `form not graph-backed`. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.

#### Scenario: Fresh graph grounds the call tree

- **WHEN** `run_architecture.py --check` exits `0` and the question names a symbol present in the graph
- **THEN** the call tree SHALL contain only nodes returned by `build_atlas.py --tree`
- **AND** the disclosure line SHALL read `Grounding: graph @ <sha7>; …` with per-language coverage percentages copied from the `--tree` footer per the substring rule above

#### Scenario: Stale or absent graph falls back to source

- **WHEN** `run_architecture.py --check` exits non-zero, or the script or graph file is missing
- **THEN** the skill SHALL still answer, drawing the sketch from the source files it reads
- **AND** the disclosure line SHALL read `Grounding: source read, unverified (<reason>)` with reason `graph stale`, `graph absent`, or `graph check failed` per the first-match order above
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
- **AND** the reply SHALL NOT include a `Grounding:` line

#### Scenario: Whole-repository redirect has no disclosure line

- **WHEN** a user asks for the whole architecture, the full dependency graph, or a repository-wide map
- **THEN** the skill SHALL name `/codebase-atlas` and stop
- **AND** the reply SHALL NOT include a `Grounding:` line

#### Scenario: Disclosure line present on every sketching answer

- **WHEN** the skill produces a sketching reply (a catalogue visual was emitted), grounded or not
- **THEN** the final line of the reply SHALL begin with `Grounding:`
- **AND** the reply SHALL contain exactly one such line

### Requirement: Explainer Frontmatter Without Triggers

The `explain-code` `SKILL.md` frontmatter SHALL declare `name`, `description`, `category: Architecture`, `tags`, `user_invocable: true`, and `related: [codebase-atlas, refresh-architecture]`, and SHALL NOT declare a `triggers:` key. The `description` SHALL state, in third person, both what the skill does and when to use it, including that whole-repository views belong to `codebase-atlas`. The skill's `test_skill_md.py` SHALL assert the declared keys explicitly rather than through the shared `assert_required_keys_present` helper while that helper still requires `triggers`, so the test passes whether or not `rewrite-skill-frontmatter` has landed. The `SKILL.md` SHALL end with the `## Common Rationalizations`, `## Red Flags`, and `## Verification` sections required of user-invocable skills.

#### Scenario: Frontmatter valid in both orderings

- **WHEN** `skills/tests/explain-code/test_skill_md.py` runs before or after `rewrite-skill-frontmatter` merges
- **THEN** it SHALL pass in both states
- **AND** it SHALL fail if any of `name`, `description`, `category`, `tags`, `user_invocable`, or `related` is missing or empty

#### Scenario: Frontmatter omits triggers and sets Architecture category

- **WHEN** the `explain-code` `SKILL.md` frontmatter is read
- **THEN** it SHALL NOT declare a `triggers:` key
- **AND** `category` SHALL be `Architecture`
- **AND** `user_invocable` SHALL be `true`
- **AND** `related` SHALL include `codebase-atlas` and `refresh-architecture`

#### Scenario: Skill markdown ends with required tail sections

- **WHEN** the `explain-code` `SKILL.md` body is read
- **THEN** it SHALL end with the `## Common Rationalizations`, `## Red Flags`, and `## Verification` sections

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

#### Scenario: Manifest declares portable distribution and atlas dependencies

- **WHEN** `skills/install-manifest.json` is read after the skill is added
- **THEN** `explain-code` SHALL declare `"distribution": "portable"`
- **AND** `cross_skill_dependencies` SHALL list `codebase-atlas` and `refresh-architecture` for `explain-code`

#### Scenario: Sibling skill paths use skill-base-dir form

- **WHEN** `skills/explain-code/**` references a co-installed sibling skill
- **THEN** the reference SHALL use the `<skill-base-dir>/../<skill>/` form

#### Scenario: Tests collected by the default sweep

- **WHEN** `skills/.venv/bin/python -m pytest` runs from `skills/` with no path arguments
- **THEN** tests under `skills/tests/explain-code/` SHALL be collected without import errors
