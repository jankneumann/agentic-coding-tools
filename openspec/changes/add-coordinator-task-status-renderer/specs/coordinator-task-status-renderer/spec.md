## ADDED Requirements

### Requirement: Coordinator-Owned Status Block in tasks.md

The system SHALL provide a `coordinator-task-status-renderer` skill that regenerates a designated managed block inside `openspec/changes/<change-id>/tasks.md` from coordinator-recorded task state.

The managed block SHALL be delimited by HTML comments using the existing repo convention:

```
<!-- GENERATED: begin coordinator:tasks-status -->
...
<!-- GENERATED: end coordinator:tasks-status -->
```

The renderer SHALL replace only content between these markers and SHALL leave content outside the markers (hand-authored task definitions, prose, acceptance criteria) untouched.

The renderer SHALL be invoked with a single argument: the `<change-id>` of the OpenSpec change whose `tasks.md` it should update.

#### Scenario: Block content reflects current coordinator state

**WHEN** the renderer runs against a change-id whose coordinator issues exist
**THEN** each issue labeled `change:<change-id>` SHALL appear as one line in the managed block
**AND** each line SHALL be valid GFM checkbox syntax (`- [ ]` for non-`completed` status, `- [x]` for `completed`)
**AND** each line SHALL include the task key from `metadata.task_key`, the issue title, and a status annotation showing claimed_by (if set) and completion timestamp (if set)
**AND** lines SHALL be sorted by task key in ascending lexicographic order

#### Scenario: Hand-authored content outside the block is preserved

**WHEN** the renderer runs against a `tasks.md` that contains hand-authored prose above and below the managed-block markers
**THEN** the renderer SHALL produce a file whose content above the `begin` marker and below the `end` marker is byte-identical to the input
**AND** no other regions of the file SHALL be modified

#### Scenario: Re-render is idempotent when state has not advanced

**WHEN** the renderer runs twice against the same change-id with no intervening coordinator state changes
**THEN** the second invocation SHALL produce a file byte-identical to the first invocation's output
**AND** `git diff` SHALL show no changes after the second invocation

#### Scenario: Managed-block markers absent — renderer inserts them

**WHEN** the renderer runs against a `tasks.md` that does not yet contain the managed-block markers
**THEN** the renderer SHALL append the managed block at the end of the file
**AND** the appended block SHALL begin with `<!-- GENERATED: begin coordinator:tasks-status -->` and end with `<!-- GENERATED: end coordinator:tasks-status -->`

---

### Requirement: Coordinator-Unreachable Fallback

When the coordinator API cannot be reached, the renderer SHALL replace the managed block with an explicit stale-marker rather than blocking the calling operation or leaving the previous block unchanged.

#### Scenario: Coordinator HTTP call fails — block shows stale marker

**WHEN** the renderer is invoked and the coordinator API call (via `coordination_bridge.try_issue_list`) fails or returns an error
**THEN** the renderer SHALL replace the managed block with a single-line indicator: `> Coordinator unreachable at <ISO-8601 timestamp> — status frozen.`
**AND** the renderer SHALL exit with status 0 (success — the hook must not block)
**AND** the renderer SHALL log a single-line warning to stderr identifying the change-id and the failure mode

#### Scenario: Coordinator recovers — block repaints on next invocation

**WHEN** a prior invocation inserted the stale marker, the coordinator becomes reachable, and the renderer is invoked again
**THEN** the stale marker SHALL be replaced by the freshly rendered task list
**AND** the rendered content SHALL match the format defined in "Coordinator-Owned Status Block in tasks.md"

---

### Requirement: Pre-commit Hook Integration

The repository's `.githooks/pre-commit` hook SHALL invoke the renderer for any change-id whose `tasks.md` is among the staged files in the pending commit, and SHALL re-stage the file after rendering so that the committed `tasks.md` reflects current coordinator state.

#### Scenario: Staged tasks.md triggers renderer

**WHEN** a developer runs `git commit` after staging `openspec/changes/<change-id>/tasks.md`
**THEN** the pre-commit hook SHALL invoke the renderer with `<change-id>`
**AND** the hook SHALL run `git add` against the rendered file before the commit completes

#### Scenario: Unrelated commit does not trigger renderer

**WHEN** a developer runs `git commit` against staged files that do not include any `openspec/changes/<change-id>/tasks.md` path
**THEN** the pre-commit hook SHALL NOT invoke the renderer for any change-id
**AND** the commit SHALL proceed without additional latency from coordinator HTTP calls

#### Scenario: Renderer failure does not block commit

**WHEN** the renderer exits with a non-zero status (e.g., from a non-coordinator error such as malformed `tasks.md`)
**THEN** the pre-commit hook SHALL log a warning identifying the change-id
**AND** the commit SHALL proceed without re-staging the file

---

### Requirement: Post-merge Hook Integration

The repository's `.githooks/post-merge` hook SHALL invoke the renderer for any change-id whose `tasks.md` was modified by the merge operation that triggered the hook.

#### Scenario: Pull updates a tasks.md — renderer fires

**WHEN** a developer runs `git pull` or `git merge` and the merge result touches `openspec/changes/<change-id>/tasks.md`
**THEN** the post-merge hook SHALL invoke the renderer with `<change-id>`
**AND** the rendered file SHALL be written to the working tree but SHALL NOT be auto-committed

#### Scenario: Pull touches no tasks.md — renderer skipped

**WHEN** a `git pull` produces a merge whose changed files do not include any `openspec/changes/<change-id>/tasks.md` path
**THEN** the post-merge hook SHALL NOT invoke the renderer
**AND** no coordinator HTTP calls SHALL be made

---

### Requirement: Seeding at /plan-feature Gate 2

The `/plan-feature` skill SHALL POST a coordinator issue for each task in `tasks.md` when the user approves the plan at Gate 2 (Plan Approval).

Each issue SHALL be created with:
- `issue_type = "task"`
- `labels = ["change:<change-id>", "wp:<work-package-id>"]` (work-package label optional if tasks aren't yet partitioned)
- `metadata.task_key = "<T1, T2, ...>"` (the task identifier appearing in `tasks.md`)
- `metadata.change_id = "<change-id>"`
- `metadata.tasks_md_anchor = "<line number of the originating task in tasks.md>"` (optional, best-effort)
- `depends_on = [<UUIDs of issues for upstream tasks>]` derived from task dependencies declared in `tasks.md`

The seeding step SHALL be idempotent: re-invoking it for the same change-id SHALL NOT create duplicate issues. Duplicate detection SHALL key on the pair `(metadata.change_id, metadata.task_key)`.

#### Scenario: Plan approved — issues created in coordinator

**WHEN** the user selects "Approve — proceed to implementation" at `/plan-feature` Gate 2
**THEN** `/plan-feature` SHALL POST one coordinator issue per task listed in `tasks.md`
**AND** each issue SHALL carry the labels and metadata specified above
**AND** the initial status of each issue SHALL be `pending`

#### Scenario: Re-run after partial seeding

**WHEN** `/plan-feature` Gate 2 is re-approved for a change-id that already has some coordinator issues with `metadata.change_id = "<change-id>"`
**THEN** `/plan-feature` SHALL detect existing issues by `(change_id, task_key)` pair
**AND** SHALL create issues only for task_keys not already present
**AND** SHALL NOT modify or delete existing issues

#### Scenario: Coordinator unreachable at Gate 2 — seeding is non-blocking

**WHEN** the user approves at Gate 2 and the coordinator API is unreachable
**THEN** `/plan-feature` SHALL log a warning identifying the change-id and the unseeded task_keys
**AND** `/plan-feature` SHALL exit successfully without creating issues
**AND** the next invocation of the renderer (via hook) SHALL display the coordinator-unreachable stale marker until issues can be created

---

### Requirement: Skill Packaging

The renderer SHALL be packaged as a new skill at `skills/coordinator-task-status-renderer/` with `user_invocable: false` (it is invoked by hooks and other skills, not by the user directly).

The skill SHALL include:
- `SKILL.md` with frontmatter conforming to the repo's existing schema
- `scripts/render_tasks_status.py` — the main renderer entry point
- `scripts/seed_tasks_from_md.py` — the seeder invoked by `/plan-feature`

#### Scenario: Skill is auto-installed by skills/install.sh

**WHEN** `skills/install.sh` runs against the repo
**THEN** the new skill SHALL appear under `.claude/skills/coordinator-task-status-renderer/` and `.agents/skills/coordinator-task-status-renderer/`
**AND** the installed `SKILL.md` SHALL contain valid frontmatter with `user_invocable: false`

#### Scenario: Tests live outside the shipped skill directory

**WHEN** `skills/install.sh` runs
**THEN** any tests under `skills/tests/coordinator-task-status-renderer/` SHALL NOT be copied into the runtime skill directories
**AND** tests SHALL be runnable via `skills/.venv/bin/python -m pytest skills/tests/coordinator-task-status-renderer/`
