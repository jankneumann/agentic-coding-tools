## ADDED Requirements

### Requirement: Visual Code Explainer Skill

The repository SHALL provide a user-invocable, prompt-only skill `show-me` that answers a narrow question about the code with the smallest visual form that makes the key point clear, drawn from a fixed catalogue: indented call tree, component tree with file paths, file tree with one-line responsibility comments, Mermaid sequence diagram, and structural (tree) diff. The skill SHALL keep prose brief, SHALL place each visual next to the short text it supports, and SHALL include only the calls, files, and boundaries the current question needs. The skill's `SKILL.md` SHALL be an index of at most 150 lines that links directly to one `references/<form>.md` file per visual form, with no nested reference files. In this version the skill SHALL NOT write HTML files, SHALL NOT write any file, and SHALL NOT open a browser.

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

Before sketching a call tree, the skill SHALL determine graph freshness by running the read-only `run_architecture.py --check` from the co-installed `refresh-architecture` skill via `<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py`, treating exit code `0` alone as fresh. When fresh, the skill SHALL obtain callers and callees from `build_atlas.py --tree` (co-installed `codebase-atlas`) and SHALL build the call tree only from nodes that export returns. When stale, absent, or failing, the skill SHALL read source directly and label the sketch unverified. Every reply SHALL end with exactly one disclosure line: `Grounding: graph @ <sha7>; <language> <percent>% covered …` when grounded, or `Grounding: source read, unverified (graph <stale|absent|check failed>)` when not. The skill SHALL NOT run a refresh, `--ensure`, or the analysis pipeline itself.

#### Scenario: Fresh graph grounds the call tree

- **WHEN** `run_architecture.py --check` exits `0` and the question names a symbol present in the graph
- **THEN** the call tree SHALL contain only nodes returned by `build_atlas.py --tree`
- **AND** the disclosure line SHALL read `Grounding: graph @ <sha7>; …` with per-language coverage percentages copied from the `--tree` footer

#### Scenario: Stale or absent graph falls back to source

- **WHEN** `run_architecture.py --check` exits non-zero, or the script or graph file is missing
- **THEN** the skill SHALL still answer, drawing the sketch from the source files it reads
- **AND** the disclosure line SHALL read `Grounding: source read, unverified (graph <reason>)`
- **AND** the skill SHALL NOT invoke `--ensure` or the analysis pipeline

#### Scenario: Symbol outside graph coverage

- **WHEN** the graph is fresh but `build_atlas.py --tree` exits `2` (target not found) for the requested symbol
- **THEN** the skill SHALL fall back to source reading for that symbol
- **AND** the disclosure line SHALL use the unverified form with reason `symbol not in graph`

#### Scenario: Disclosure line present on every answer

- **WHEN** the skill produces any reply, grounded or not
- **THEN** the final line of the reply SHALL begin with `Grounding:`
- **AND** the reply SHALL contain exactly one such line

### Requirement: Explainer Frontmatter Without Triggers

The `show-me` `SKILL.md` frontmatter SHALL declare `name`, `description`, `category: Architecture`, `tags`, `user_invocable: true`, and `related: [codebase-atlas, refresh-architecture]`, and SHALL NOT declare a `triggers:` key. The `description` SHALL state, in third person, both what the skill does and when to use it, including that whole-repository views belong to `codebase-atlas`. The skill's `test_skill_md.py` SHALL assert the declared keys explicitly rather than through the shared `assert_required_keys_present` helper while that helper still requires `triggers`, so the test passes whether or not `rewrite-skill-frontmatter` has landed. The `SKILL.md` SHALL end with the `## Common Rationalizations`, `## Red Flags`, and `## Verification` sections required of user-invocable skills.

#### Scenario: Frontmatter valid in both orderings

- **WHEN** `skills/tests/show-me/test_skill_md.py` runs before or after `rewrite-skill-frontmatter` merges
- **THEN** it SHALL pass in both states
- **AND** it SHALL fail if any of `name`, `description`, `category`, `tags`, `user_invocable`, or `related` is missing or empty

#### Scenario: Description carries the trigger condition

- **WHEN** the frontmatter `description` is read
- **THEN** it SHALL name the capability (visual explanation of a specific piece of code) and the use condition (a narrow question about how code works or connects)
- **AND** it SHALL direct whole-repository requests to `codebase-atlas`

### Requirement: Explainer Distribution Wiring

`skills/install-manifest.json` SHALL declare `"show-me": {"distribution": "portable"}` and a `cross_skill_dependencies` entry `"show-me": ["codebase-atlas", "refresh-architecture"]`. `skills/pyproject.toml` `testpaths` SHALL list `tests/show-me`. All runtime references from `show-me` to sibling skills SHALL use the `<skill-base-dir>/../<skill>/` form.

#### Scenario: Manifest validation passes

- **WHEN** `skills/install.sh --check-only` runs after the skill is added
- **THEN** the manifest validator SHALL report zero errors
- **AND** every sibling reference in `skills/show-me/**` SHALL be covered by the declared cross-skill dependencies

#### Scenario: Tests collected by the default sweep

- **WHEN** `skills/.venv/bin/python -m pytest` runs from `skills/` with no path arguments
- **THEN** tests under `skills/tests/show-me/` SHALL be collected without import errors
