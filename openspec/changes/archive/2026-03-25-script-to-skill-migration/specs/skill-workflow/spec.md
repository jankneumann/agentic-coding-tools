# Spec Delta: skill-workflow

## Why

Skills reference scripts at repo-root paths (e.g., `scripts/worktree.py`) that don't exist when skills are synced to other repos. This makes 21+ skills non-portable.

## ADDED Requirements

### Requirement: Infrastructure Skill Packaging

Scripts referenced by multiple skills MUST be packaged as infrastructure skills under `skills/` with a `SKILL.md` and a `scripts/` subdirectory.

#### Scenario: Shared script is packaged as infrastructure skill
- **GIVEN** a Python script in `scripts/` that is referenced by 2+ skills
- **WHEN** the skill packaging is evaluated
- **THEN** the script MUST exist in an infrastructure skill directory under `skills/<infra-skill>/scripts/`
- **AND** the infrastructure skill MUST have a `SKILL.md` file

### Requirement: Infrastructure Skills Are Not User-Invocable

Infrastructure skills MUST set `user_invocable: false` in their SKILL.md frontmatter and `category: Infrastructure`.

#### Scenario: Infrastructure skill frontmatter
- **GIVEN** an infrastructure skill directory under `skills/`
- **WHEN** the SKILL.md frontmatter is parsed
- **THEN** the `user_invocable` field MUST be `false`
- **AND** the `category` field MUST be `Infrastructure`

### Requirement: Infrastructure Skill API Documentation

Infrastructure skills MUST document all script entry points, arguments, outputs, and exit codes in their SKILL.md.

#### Scenario: Script API is documented
- **GIVEN** an infrastructure skill with scripts in `scripts/`
- **WHEN** the SKILL.md is reviewed
- **THEN** each script MUST have documented entry point, CLI arguments, stdout/stderr format, and exit codes

### Requirement: Sibling-Relative Path Resolution

Skills MUST reference infrastructure scripts using sibling-relative paths: `<skill-base-dir>/../<infra-skill>/scripts/<script>`.

#### Scenario: Skill references infrastructure script
- **GIVEN** a skill that depends on `worktree.py`
- **WHEN** the SKILL.md path reference is evaluated
- **THEN** the path MUST use the pattern `<skill-base-dir>/../worktree/scripts/worktree.py`
- **AND** MUST NOT use `scripts/worktree.py` (repo-root-relative)

### Requirement: No Repo-Root Script References

Skills MUST NOT reference scripts at repo-root paths (e.g., `scripts/X.py`) in SKILL.md instructions.

#### Scenario: SKILL.md has no repo-root script paths
- **GIVEN** any SKILL.md file under `skills/`
- **WHEN** scanned for path references
- **THEN** no references matching `scripts/<name>.py` without `<skill-base-dir>` prefix SHALL be found

### Requirement: Sibling-Relative Python Imports

Python scripts that import from other skill packages MUST use sibling-relative `sys.path` resolution, not repo-root-relative.

#### Scenario: Python cross-skill import
- **GIVEN** a Python script in `skills/<skill-a>/scripts/` that imports from `skills/<skill-b>/scripts/`
- **WHEN** the `sys.path` manipulation is evaluated
- **THEN** the path MUST resolve relative to the script location via `Path(__file__).parent.parent.parent / "<skill-b>" / "scripts"`

### Requirement: Infrastructure Skills Are Synced

`install.sh` MUST sync infrastructure skills alongside SDLC skills to all agent runtimes.

#### Scenario: install.sh syncs infrastructure skills
- **GIVEN** infrastructure skill directories exist under `skills/`
- **WHEN** `install.sh` is executed
- **THEN** infrastructure skills MUST appear in `.claude/skills/`, `.codex/skills/`, and `.gemini/skills/`

### Requirement: Source Script Sync

`install.sh` MUST copy source scripts from `scripts/` into infrastructure skill directories before syncing to agents.

#### Scenario: Source scripts are synced to infra skill
- **GIVEN** `scripts/worktree.py` exists as the source of truth
- **WHEN** `install.sh` is executed
- **THEN** `skills/worktree/scripts/worktree.py` MUST be updated to match the source

### Requirement: Cross-Repo Portability

Skills MUST function correctly when synced to a directory with no `scripts/` at the repo root.

#### Scenario: Skill works without repo-root scripts
- **GIVEN** skills are synced to a fresh directory via `install.sh`
- **AND** the target directory has no `scripts/` at root level
- **WHEN** a skill that depends on `worktree.py` is invoked
- **THEN** it MUST resolve the script via sibling-relative path from the infrastructure skill
