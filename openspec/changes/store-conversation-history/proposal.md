# Proposal: Store Conversation History with OpenSpec Changes

## Why

When a feature is completed and archived, the design rationale, trade-offs considered, alternatives rejected, and key discussion points from the agent session are lost. Git preserves *what* changed (diffs) and OpenSpec artifacts capture the *plan* (proposal, specs, tasks), but neither captures the *why* behind implementation decisions — the back-and-forth reasoning that led to specific approaches. This context is valuable for future maintainers, for understanding why alternatives were rejected, and for debugging unexpected behaviors months later.

## What Changes

- **New artifact**: `session-log.md` — a structured, sanitized summary of the agent conversation capturing decision rationale, trade-offs, alternatives considered, and key discussion points. Generated during cleanup and archived with the change.
- **Schema update**: Register `session-log` as an optional artifact in `feature-workflow/schema.yaml`
- **Config update**: Add `session-log` rules to `config.yaml` governing content structure and sanitization
- **Cleanup skill updates**: Add a session log generation step to `linear-cleanup-feature` and `parallel-cleanup-feature` before archiving
- **Sanitization script**: New infrastructure skill `session-log` with a Python script to detect and redact secrets, API keys, tokens, and other sensitive patterns before the log is committed to git
- **Multi-agent support**: Capture logs from Claude Code, Codex, and other agents using a provider-agnostic extraction approach

## Impact

### Affected Specs
- `skill-workflow` — delta: `specs/skill-workflow/spec.md` (new requirements for session-log artifact generation, sanitization, and cleanup integration)

### Affected Architecture Layers
- **Execution** — Cleanup skill instruction files that guide agent behavior during the cleanup phase
- **Governance** — OpenSpec schema and config that define artifact conventions

### Affected Code/Files
- `openspec/schemas/feature-workflow/templates/session-log.md` (NEW)
- `openspec/schemas/feature-workflow/schema.yaml` (MODIFY)
- `openspec/config.yaml` (MODIFY)
- `skills/linear-cleanup-feature/SKILL.md` (MODIFY)
- `skills/parallel-cleanup-feature/SKILL.md` (MODIFY)
- `skills/session-log/SKILL.md` (NEW — infrastructure skill)
- `skills/session-log/scripts/sanitize_session_log.py` (NEW)
- `skills/session-log/scripts/extract_session_log.py` (NEW)

## Rollback Plan

All changes are to markdown instruction files, YAML config, and a standalone Python sanitization script — no runtime coordinator code. Rollback is a simple revert of the commit. Pre-existing changes without `session-log.md` continue to work because the artifact is optional and cleanup skills skip the step if session context is unavailable.
