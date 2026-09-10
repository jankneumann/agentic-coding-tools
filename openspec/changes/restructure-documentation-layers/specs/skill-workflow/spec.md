# skill-workflow — delta for restructure-documentation-layers

Turns the append-only lessons rule into a maintained-corpus rule: every lesson carries a
status and an evidence pointer, superseded lessons name what replaced them, and no lesson
may cite a surface that no longer exists.

## MODIFIED Requirements

### Requirement: Documentation Update Per Iteration
Each iteration SHALL review whether genuinely new patterns, lessons, or gotchas were discovered and, if so, update the relevant documentation files.

Documentation updates SHALL follow the existing convention:
- Update CLAUDE.md or AGENTS.md directly if they are under 300 lines each
- If either file exceeds 300 lines, refactor into focused documents in docs/ and reference them

Every lesson bullet in `docs/lessons-learned.md` SHALL carry an inline `status:` tag with one of `active`, `superseded`, or `retired`, and an inline `evidence:` tag naming a repository path, a spec requirement, or a `docs/decisions/` entry that substantiates it. A `superseded` lesson SHALL also carry a `by:` tag naming the decision, archived change, or document that replaced it. Lessons marked `retired` SHALL be moved to `docs/archive/lessons-retired.md` at the next documentation sweep. A lesson SHALL NOT cite a skill, script, or file that does not exist in the repository.

#### Scenario: New lesson discovered during iteration
- **WHEN** an iteration reveals a pattern or gotcha not already documented
- **THEN** the skill SHALL add the lesson to CLAUDE.md, AGENTS.md, or the appropriate docs/ file
- **AND** a lesson added to `docs/lessons-learned.md` SHALL carry `status: active` and an `evidence:` tag
- **AND** include the documentation change in the iteration's commit

#### Scenario: No new lessons in an iteration
- **WHEN** an iteration's findings are variations of already-documented patterns
- **THEN** the skill SHALL NOT add redundant documentation

#### Scenario: Lesson superseded by a later decision
- **WHEN** an iteration finds that an existing lesson contradicts an `active` entry in `docs/decisions/` or the current implementation
- **THEN** the lesson SHALL be re-tagged `status: superseded` with a `by:` tag naming the superseding decision or change
- **AND** the lesson text SHALL NOT be deleted in the same iteration

#### Scenario: Lesson cites a removed surface
- **WHEN** a lesson bullet names a `/skill-name` with no `skills/<skill-name>/SKILL.md`, or a path that does not exist
- **THEN** the documentation structure test SHALL fail and name the lesson and the missing surface
