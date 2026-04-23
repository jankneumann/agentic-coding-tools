# Skill Runtime Sync — Spec Delta

## ADDED Requirements

### Requirement: Canonical-to-runtime skill sync

The system SHALL provide an `/update-skills` skill that synchronizes canonical skills under `skills/` into the runtime directories `.claude/skills/` and `.agents/skills/`, then commits and pushes the regenerated files.

#### Scenario: Skill edit propagates to both runtime directories

- **WHEN** a user edits `skills/<name>/SKILL.md` and runs `/update-skills`
- **THEN** `.claude/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md` MUST contain the same content as the canonical source
- **AND** the regenerated files MUST be staged in git

#### Scenario: No-op when nothing changed

- **WHEN** `/update-skills` runs and the canonical source matches both runtime directories already
- **THEN** the skill MUST exit successfully without creating an empty commit

#### Scenario: Conventional commit message

- **WHEN** `/update-skills` creates a commit because runtime files changed
- **THEN** the commit message MUST start with `chore(skills): sync runtime copies`

#### Scenario: Orchestrator aborts on sync-script failure

- **WHEN** `/update-skills` has completed install.sh successfully and then invokes `sync_agents_md.py` which exits non-zero
- **THEN** the skill MUST NOT create a commit
- **AND** the skill MUST exit with status 1
- **AND** the skill MUST print the sync script's stderr to its own stderr
- **AND** any install.sh changes already staged MUST remain staged (not reverted) so the user can inspect and recover manually

#### Scenario: Orchestrator aborts on install.sh failure

- **WHEN** `/update-skills` invokes `install.sh` and it exits non-zero
- **THEN** the skill MUST NOT invoke `sync_agents_md.py`
- **AND** the skill MUST NOT create a commit
- **AND** the skill MUST exit with status 1
- **AND** the skill MUST surface install.sh's exit code and stderr to the user

### Requirement: Push with bounded retry

The `/update-skills` skill SHALL push committed changes to the current branch on `origin`, with `git pull --rebase --autostash` immediately before push and bounded retry on push rejection.

#### Scenario: Successful push on first attempt

- **WHEN** `/update-skills` pushes and the push succeeds
- **THEN** the skill MUST exit with status 0
- **AND** report the pushed commit SHA

#### Scenario: Push rejected, rebase, retry

- **WHEN** `/update-skills` pushes and `git push origin <current-branch>` is rejected because the remote has new commits
- **THEN** the skill MUST run `git pull --rebase --autostash` and retry the push
- **AND** retry up to 3 total push attempts (attempt 1 with no preceding wait; on rejection, wait 1 second then attempt 2; on rejection, wait 2 seconds then attempt 3)
- **AND** the remote MUST be resolved explicitly as `origin` (not implicit from branch config)

#### Scenario: Push retry exhausted

- **WHEN** `/update-skills` exhausts all 3 push attempts
- **THEN** the skill MUST exit with status 1
- **AND** write to stderr a human-readable summary containing: each attempt's timestamp, the git error line from that attempt, and the SHA of the unpushed local HEAD commit
- **AND** write stdout a single machine-readable line: `UNPUSHED_COMMIT=<sha>` for automation to parse

### Requirement: AGENTS.md byte-identity to CLAUDE.md

The system SHALL maintain `AGENTS.md` as a byte-identical copy of `CLAUDE.md` at the repository root.

#### Scenario: Sync regenerates AGENTS.md after CLAUDE.md edit

- **WHEN** a user edits `CLAUDE.md` and runs `/update-skills`
- **THEN** `AGENTS.md` MUST be byte-identical to `CLAUDE.md` after the skill completes
- **AND** the regenerated `AGENTS.md` MUST be included in the same commit as the runtime-skills sync

#### Scenario: Pre-commit hook rejects drift

- **WHEN** a user attempts to commit with `CLAUDE.md` modified but `AGENTS.md` not regenerated
- **THEN** the pre-commit hook MUST exit non-zero
- **AND** print a message instructing the user to run `python3 skills/update-skills/scripts/sync_agents_md.py` (or `/update-skills`)

#### Scenario: Pre-commit hook passes when in sync

- **WHEN** a user commits and `CLAUDE.md` and `AGENTS.md` are byte-identical
- **THEN** the `sync_agents_md.py --check` invocation MUST exit 0 with empty stderr
- **AND** the pre-commit framework MAY print its own hook-id/status line; the underlying script MUST NOT contribute additional output

### Requirement: Opt-in SessionStart auto-pull

The system SHALL provide a SessionStart hook that runs `git pull --rebase --autostash` on the current branch when explicitly enabled, and SHALL be a no-op otherwise.

#### Scenario: Auto-pull enabled and tree clean

- **WHEN** a session starts with `AGENTIC_AUTO_PULL=1` and the working tree is clean
- **THEN** the hook MUST run `git pull --rebase --autostash` on the current branch
- **AND** continue session start regardless of pull outcome (silent on network failure)

#### Scenario: Auto-pull enabled but tree dirty

- **WHEN** a session starts with `AGENTIC_AUTO_PULL=1` and the working tree has uncommitted changes
- **THEN** the hook MUST skip the pull and log a single line stating the skip reason
- **AND** session start MUST proceed normally

#### Scenario: Auto-pull disabled (default)

- **WHEN** a session starts and `AGENTIC_AUTO_PULL` is unset or not equal to `1`
- **THEN** the hook MUST exit 0 immediately without running any git command

#### Scenario: Auto-pull wired for both runtimes

- **WHEN** the change has been implemented
- **THEN** a single `auto_pull.py` helper MUST exist at `skills/session-bootstrap/scripts/hooks/auto_pull.py`
- **AND** `.claude/settings.json`'s SessionStart hooks block MUST contain an entry that invokes `auto_pull.py`
- **AND** `skills/session-bootstrap/scripts/bootstrap-cloud.sh` (the Codex Maintenance Script) MUST contain an invocation of `auto_pull.py`
- **AND** both wiring points MUST pass through the same `AGENTIC_AUTO_PULL=1` gate so opt-in behavior is consistent across runtimes

### Requirement: Sync script as standalone tool

The `sync_agents_md.py` script SHALL be invocable independently of the `/update-skills` skill, supporting both regenerate-mode and check-only mode.

#### Scenario: Regenerate mode copies CLAUDE.md to AGENTS.md

- **WHEN** `python3 skills/update-skills/scripts/sync_agents_md.py` is run
- **THEN** the script MUST overwrite `AGENTS.md` with the byte-content of `CLAUDE.md`
- **AND** exit with status 0

#### Scenario: Check mode reports drift

- **WHEN** `python3 skills/update-skills/scripts/sync_agents_md.py --check` is run and the files differ
- **THEN** the script MUST exit with status 2
- **AND** print a unified diff to stderr

#### Scenario: Check mode reports in-sync

- **WHEN** `python3 skills/update-skills/scripts/sync_agents_md.py --check` is run and the files are byte-identical
- **THEN** the script MUST exit with status 0 silently

#### Scenario: Missing source file

- **WHEN** the script runs and `CLAUDE.md` does not exist at the repo root
- **THEN** the script MUST exit with status 1
- **AND** print an error message naming the missing path

### Requirement: Install-hooks bootstrap is idempotent

The `install-hooks.sh` script SHALL install the pre-commit framework and wire it to `.git/hooks/pre-commit`, and SHALL be safe to re-run without harmful side effects.

#### Scenario: First-run installation

- **WHEN** `install-hooks.sh` runs on a fresh clone where `skills/.venv/` does not yet exist
- **THEN** the script MUST invoke `uv sync --all-extras` inside `skills/` to create the venv and install pre-commit
- **AND** then invoke `skills/.venv/bin/pre-commit install` to create `.git/hooks/pre-commit`
- **AND** exit with status 0 when both steps succeed

#### Scenario: Idempotent re-run

- **WHEN** `install-hooks.sh` runs a second time on a repo where pre-commit is already installed and hooks are already wired
- **THEN** `uv sync --all-extras` MUST exit 0 (no-op when dependencies are already in-sync)
- **AND** `pre-commit install` MUST exit 0 (safe overwrite of the existing hook)
- **AND** the script MUST exit 0 without printing error messages

#### Scenario: Missing uv binary

- **WHEN** `install-hooks.sh` runs and the `uv` command is not on the PATH
- **THEN** the script MUST exit with status 1
- **AND** print an error message instructing the user to install `uv` per the CLAUDE.md Python Environment section
