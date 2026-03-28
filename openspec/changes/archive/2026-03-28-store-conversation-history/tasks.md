# Tasks: store-conversation-history

## Task 1: Create session-log.md template and register in schema

- [x] Create `openspec/schemas/feature-workflow/templates/session-log.md` with structured sections (Summary, Key Decisions, Alternatives Considered, Trade-offs, Open Questions, Session Metadata)
- [x] Add `session-log` artifact entry to `openspec/schemas/feature-workflow/schema.yaml` (after `deferred-tasks`, marked as optional)
- [x] Add `session-log` rules to `openspec/config.yaml` (content structure, sanitization, conciseness requirements)

**Files**: `openspec/schemas/feature-workflow/templates/session-log.md` (NEW), `openspec/schemas/feature-workflow/schema.yaml`, `openspec/config.yaml`
**Dependencies**: None
**Traces to**: Session Log Artifact, Session Log Content Structure

## Task 2: Create sanitization script

- [x] Create `skills/session-log/scripts/sanitize_session_log.py` with regex patterns for common secret formats (API keys, tokens, passwords, connection strings, AWS credentials, private keys)
- [x] Implement Shannon entropy detection for high-entropy strings (>4.5 bits/char, >20 chars)
- [x] Implement path normalization (home dirs, hostnames)
- [x] Implement allowlist for common development identifiers (UUIDs, git SHAs, change-ids)
- [x] Exit code 0 on success, exit code 1 on sanitization errors
- [x] Add unit tests for secret detection patterns and edge cases

**Files**: `skills/session-log/scripts/sanitize_session_log.py` (NEW), `skills/session-log/scripts/test_sanitize_session_log.py` (NEW)
**Dependencies**: None
**Traces to**: Session Log Sanitization

## Task 3: Create extraction script

- [x] Create `skills/session-log/scripts/extract_session_log.py` implementing 3-tier extraction:
  - Tier 1: Claude Code session transcript parsing (read from local storage path)
  - Tier 2: Handoff document compilation (query coordinator if `CAN_HANDOFF=true`)
  - Tier 3: Generate structured prompts for agent self-summary fallback
- [x] Output structured markdown matching the `session-log.md` template sections
- [x] Support `--change-id`, `--agent-type`, and `--handoff-source` arguments
- [x] Add unit tests for extraction logic and tier fallback

**Files**: `skills/session-log/scripts/extract_session_log.py` (NEW), `skills/session-log/scripts/test_extract_session_log.py` (NEW)
**Dependencies**: None
**Traces to**: Session Log Extraction

## Task 4: Create session-log infrastructure skill

- [x] Create `skills/session-log/SKILL.md` documenting the infrastructure skill purpose, scripts, and usage
- [x] Document CLI interface: `python3 extract_session_log.py --change-id <id> [--agent-type claude|codex|gemini] [--handoff-source <path>]`
- [x] Document CLI interface: `python3 sanitize_session_log.py <input-path> <output-path>`

**Files**: `skills/session-log/SKILL.md` (NEW)
**Dependencies**: Task 2, Task 3
**Traces to**: Infrastructure Skill Packaging, Sibling-Relative Path Resolution

## Task 5: Integrate session log generation into linear-cleanup-feature

- [x] Add new step "Generate Session Log" between task migration (Step 5) and OpenSpec archive (Step 6)
- [x] Step calls extraction script with change-id, then sanitization script
- [x] On success: `git add` the session-log.md and include in archive commit
- [x] On failure: log warning, proceed with archive without session log
- [x] Include self-summary fallback instructions for when extraction fails

**Files**: `skills/linear-cleanup-feature/SKILL.md`
**Dependencies**: Task 4
**Traces to**: Cleanup Skill Session Log Integration (linear)

## Task 6: Integrate session log generation into parallel-cleanup-feature

- [x] Add new step "Generate Session Log" between task migration and archive steps
- [x] Collect handoff documents from all agent worktrees for the change-id
- [x] Consolidate into single session-log.md with per-agent sections
- [x] Apply sanitization and commit with archive
- [x] On failure: log warning, proceed without session log

**Files**: `skills/parallel-cleanup-feature/SKILL.md`
**Dependencies**: Task 4, Task 5
**Traces to**: Cleanup Skill Session Log Integration (parallel)

## Task 7: Add session-log to archive skill awareness

- [x] Verified archive skill already handles optional artifacts gracefully (warns about incomplete, doesn't block)
- [x] `session-log` registered with `optional: true` in schema.yaml — `openspec validate --strict` does not fail on absence

**Files**: No changes needed — archive skills already handle optional artifacts via `openspec status --json` artifact graph
**Dependencies**: Task 1
**Traces to**: Session Log Artifact (optional scenario)
