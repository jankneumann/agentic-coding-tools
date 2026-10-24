## ADDED Requirements

### Requirement: Why Trace Script

The `explain-code` skill SHALL ship a read-only script `skills/explain-code/scripts/why_trace.py` that, given a target `<path>:<line>` (and an optional `--symbol <name>`), emits exactly one JSON object on stdout describing the chain blame → commit → PR → change-id → decisions for that line. The object SHALL carry `schema_version: 1` and the keys `target`, `status`, `blame`, `commit`, `pr`, `pr_reason`, `change_ids`, `decisions`, and `null_result`. `status` SHALL be one of `traced`, `uncommitted`, `history_truncated`, `no_change_id`, or `no_decision_record`. A change id found only in commit or PR-merge text SHALL count only when it resolves to a change directory under `openspec/changes/` (active or archived), so a mention of a file such as `openspec/config.yaml` SHALL NOT yield a change id. The script SHALL parse Decision bullets only through `extract_decisions` and resolve supersession only through the supersession resolver in `skills/explore-feature/scripts/decision_index.py`; it SHALL NOT contain a second session-log parser. The script SHALL run only read-only git subcommands (`blame`, `show`, `log`, `rev-parse`, `ls-files`), SHALL NOT write any file, and SHALL NOT make network calls. Every blame, commit, and PR record SHALL carry a `pointer` of the form `git:<sha>`, and every decision record SHALL carry a `pointer` of the form `<session-log repo-relative path>#<phase-slug>/D<n>` and a boolean `mentions_target`. Output SHALL be deterministic for a given repository state.

#### Scenario: Full chain traced in a fixture repository

- **WHEN** `why_trace.py <path>:<line>` runs in a git repository where the line was last changed by a commit whose subject ends with `(#N)` and which touches `openspec/changes/archive/<date>-<id>/`, and that change's `session-log.md` has an `architectural:`-tagged Decision bullet
- **THEN** it SHALL exit `0` with `status` equal to `traced` and `null_result` equal to `null`
- **AND** `blame.sha` and `commit.sha` SHALL equal that commit's full sha, and `pr.number` SHALL equal `N`
- **AND** `change_ids` SHALL contain `<id>` with its `change_dir` resolved to the archive directory
- **AND** `decisions` SHALL contain that decision with its `title`, `rationale`, `capability`, `phase`, and `pointer`

#### Scenario: No change id resolvable

- **WHEN** the commit that last changed the line touches no `openspec/changes/` path and neither it nor its PR-merge commit names an `openspec/<id>` branch
- **THEN** it SHALL exit `0` with `status` equal to `no_change_id`
- **AND** `decisions` SHALL be `[]`
- **AND** `null_result.reason` SHALL be `no_change_id` with a non-empty `null_result.message`

#### Scenario: OpenSpec file mention is not a change id

- **WHEN** the commit that last changed the line touches no `openspec/changes/` path and its message names `openspec/config.yaml`
- **THEN** `change_ids` SHALL NOT contain `config`
- **AND** `status` SHALL be `no_change_id`

#### Scenario: Change found but no decision record covers it

- **WHEN** a change id is resolved but its `session-log.md` is absent or holds no `architectural:`-tagged Decision bullet
- **THEN** it SHALL exit `0` with `status` equal to `no_decision_record`, `decisions` equal to `[]`, and `null_result.reason` equal to `no_decision_record`
- **AND** `null_result.message` SHALL say, per change id, whether the change directory, its `session-log.md`, or an `architectural:`-tagged Decision bullet was the missing record

#### Scenario: Uncommitted line

- **WHEN** the target line exists in the working tree but has not been committed
- **THEN** it SHALL exit `0` with `status` equal to `uncommitted`, `commit` equal to `null`, `decisions` equal to `[]`, and `null_result.reason` equal to `uncommitted`

#### Scenario: Shallow-clone boundary reported as history_truncated

- **WHEN** the target line blames to a commit that git marks as a `boundary` and that commit is listed in the repository's shallow file, as in a `git clone --depth 1`
- **THEN** it SHALL exit `0` with `status` equal to `history_truncated` and `null_result.reason` equal to `history_truncated`
- **AND** `blame.sha` SHALL be the boundary commit's sha, and `commit`, `pr`, `change_ids` and `decisions` SHALL be `null`, `null`, `[]` and `[]`
- **AND** `null_result.message` SHALL name the boundary sha and say that the history is shallow
- **AND** a root commit in a full (non-shallow) history SHALL still be traced

#### Scenario: Invalid input rejected

- **WHEN** the target is not of the form `<path>:<positive integer>`, the path is not tracked by git, or the line is beyond the end of the file
- **THEN** it SHALL exit `2` and write a one-line error to stderr
- **AND** it SHALL write nothing to stdout

#### Scenario: Superseded decision reported

- **WHEN** a decision in the traced change is named by a later decision's `supersedes:` reference anywhere under `openspec/changes/**/session-log.md`
- **THEN** that decision's `superseded_by` SHALL be the superseding decision's reference, as resolved by `decision_index`

#### Scenario: Target mention flag

- **WHEN** a decision's title or rationale names the target's repo-relative path, its basename, or the `--symbol` value as a whole token
- **THEN** that decision's `mentions_target` SHALL be `true`
- **AND** otherwise it SHALL be `false`

#### Scenario: Near-miss name does not set the mention flag

- **WHEN** the target is `app.py` with `--symbol load` and a decision names only `myapp.py`, `lib/app.py`, `app.pyc`, or `loader`
- **THEN** that decision's `mentions_target` SHALL be `false`

#### Scenario: No side effects

- **WHEN** the script runs on any target
- **THEN** the repository's working tree, index, and refs SHALL be unchanged afterwards

### Requirement: Why Chain Reply Contract

The `explain-code` catalogue SHALL include a *why chain* form, documented in `skills/explain-code/references/why.md`, for questions of the form "why is this code like this?". No standalone `why` skill SHALL be added. `SKILL.md` SHALL document a five-tier evidence vocabulary — Direct, Supported, Inferred, Speculative, Unknown — and SHALL require that every claim sentence in a why-chain reply ends with a bracketed tier tag. Direct and Supported tags SHALL cite at least one `pointer` from the `why_trace` output. A link from a decision to the target line SHALL be tagged Direct only when that decision's `mentions_target` is `true`. `SKILL.md` SHALL document the **null-result rule**: when `why_trace` reports a non-null `null_result`, the reply SHALL lead with the statement that no decision record covers the line, tagged Unknown, and SHALL NOT present an inferred or speculative rationale as the answer. `SKILL.md` SHALL document the **embedded-hypothesis rule**: a reason asserted in the user's question SHALL be restated as a claim and given exactly one verdict — confirmed, contradicted, or untested — and SHALL NOT be used as a premise of the answer. A why-chain reply SHALL end with the existing non-call-tree grounding disclosure line.

#### Scenario: Why question answered with a tagged chain

- **WHEN** a user asks why a specific line or symbol is the way it is
- **THEN** the skill SHALL run `why_trace.py` for the resolved `<path>:<line>`
- **AND** the reply SHALL contain one fenced why chain and at most three tagged claim sentences
- **AND** the reply SHALL end with `Grounding: source read, unverified (form not graph-backed)`

#### Scenario: Null result reported as the finding

- **WHEN** the trace's `null_result` is non-null
- **THEN** the reply SHALL open with `No decision record covers <path>:<line>` and the reason, tagged `[Unknown]`
- **AND** at most one further sentence MAY offer a reading, tagged Inferred or Speculative

#### Scenario: Hypothesis in the question tested, not adopted

- **WHEN** the question asserts a reason, for example "this retry was added for the flaky coordinator, right?"
- **THEN** the reply SHALL restate that reason as a claim with exactly one verdict of confirmed, contradicted, or untested
- **AND** a confirmed or contradicted verdict SHALL cite a pointer, and an untested verdict SHALL be tagged Unknown

#### Scenario: Tier vocabulary documented in one place

- **WHEN** `skills/explain-code/SKILL.md` and `skills/explain-code/references/why.md` are inspected
- **THEN** `SKILL.md` SHALL name all five tiers and both rules and link directly to `references/why.md`
- **AND** the tier names listed in `references/why.md` SHALL, lowercased, equal the `evidence_level` enum in `review-findings.schema.json`

### Requirement: Review Finding Evidence Level

`openspec/schemas/review-findings.schema.json` and its install-assets mirror SHALL define, in `findings.items.properties`, an optional string property `evidence_level` with the enum `["direct", "supported", "inferred", "speculative", "unknown"]`. The property SHALL NOT be listed in `required`, SHALL NOT declare a `default`, and SHALL NOT be `readOnly`. The diff of each schema copy against its base SHALL consist of that one property only, and the two copies SHALL remain byte-identical. `review_findings_schema.prompt_contract()` SHALL expose the `evidence_level` enum, and both `prompt_contract_block()` and `vendor_review.build_review_prompt()` SHALL name the field as optional. No consensus or blocking logic SHALL read `evidence_level`. At ingest, findings coercion SHALL normalise a case or whitespace variant of an enum value to that value, and SHALL remove any other `evidence_level` value from the finding, recording a coercion note either way; an invalid `evidence_level` SHALL NOT cause the finding or the vendor payload to be rejected.

#### Scenario: Prompt contract includes the field

- **WHEN** `review_findings_schema.prompt_contract()` is called
- **THEN** its enums SHALL include `evidence_level` with the five values in schema order
- **AND** `prompt_contract_block()` SHALL contain a line naming `evidence_level` as OPTIONAL

#### Scenario: Vendor prompt names every enum value

- **WHEN** `vendor_review.build_review_prompt()` renders its vocabulary block
- **THEN** every `evidence_level` enum value SHALL appear in the prompt

#### Scenario: Existing findings documents still validate

- **WHEN** every committed per-vendor findings document under `openspec/changes/**/findings-*.json` is validated against the schema with `evidence_level`
- **THEN** its validation errors SHALL be a subset of its validation errors against the same schema without `evidence_level`

#### Scenario: Finding with an evidence level validates

- **WHEN** an otherwise valid finding carries `"evidence_level": "inferred"`
- **THEN** it SHALL validate
- **AND** a finding carrying `"evidence_level": "certain"` SHALL fail validation

#### Scenario: Invalid evidence level dropped, finding kept

- **WHEN** a vendor payload of several findings is ingested and one finding carries `"evidence_level": "very-high"`
- **THEN** the dispatch SHALL succeed with every finding kept
- **AND** that finding SHALL have no `evidence_level`, and the result's coercion notes SHALL record the drop
- **AND** a finding carrying `"evidence_level": "Direct"` SHALL be kept with `evidence_level` equal to `direct`

## MODIFIED Requirements

### Requirement: Visual Code Explainer Skill

The repository SHALL provide a user-invocable skill `explain-code` that answers a narrow question about the code with the smallest visual form that makes the key point clear, drawn from a fixed catalogue: indented call tree, component tree with file paths, file tree with one-line responsibility comments, Mermaid sequence diagram, structural (tree) diff, and why chain. The skill SHALL keep prose brief, SHALL place each visual next to the short text it supports, and SHALL include only the calls, files, and boundaries the current question needs. The skill's `SKILL.md` SHALL be an index of at most 150 lines that links directly to one `references/<form>.md` file per visual form, with no nested reference files. Apart from the read-only `scripts/why_trace.py`, the skill SHALL ship no executable code. In this version the skill SHALL NOT write HTML files, SHALL NOT write any file, and SHALL NOT open a browser.

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
- **AND** it MAY read the architecture graph and source files read-only, and MAY run the read-only `why_trace.py`, as part of grounding

### Requirement: Explainer Distribution Wiring

`skills/install-manifest.json` SHALL declare `"explain-code": {"distribution": "portable"}` and a `cross_skill_dependencies` entry `"explain-code": ["codebase-atlas", "explore-feature", "refresh-architecture"]`. `skills/pyproject.toml` `testpaths` SHALL list `tests/explain-code`. All runtime references from `explain-code` to sibling skills SHALL use the `<skill-base-dir>/../<skill>/` form.

#### Scenario: Manifest validation passes

- **WHEN** `skills/install.sh --check` runs after the skill is added
- **THEN** the manifest validator SHALL report zero errors
- **AND** every sibling reference in `skills/explain-code/**` SHALL be covered by the declared cross-skill dependencies

#### Scenario: Manifest declares portable distribution and sibling dependencies

- **WHEN** `skills/install-manifest.json` is read after the skill is added
- **THEN** `explain-code` SHALL declare `"distribution": "portable"`
- **AND** `cross_skill_dependencies` SHALL list `codebase-atlas`, `explore-feature`, and `refresh-architecture` for `explain-code`

#### Scenario: Sibling skill paths use skill-base-dir form

- **WHEN** `skills/explain-code/**` references a co-installed sibling skill
- **THEN** the reference SHALL use the `<skill-base-dir>/../<skill>/` form

#### Scenario: Tests collected by the default sweep

- **WHEN** `skills/.venv/bin/python -m pytest` runs from `skills/` with no path arguments
- **THEN** tests under `skills/tests/explain-code/` SHALL be collected without import errors
