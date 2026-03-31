# Proposal: Add Phase Session Logs

## Problem

The session-log infrastructure skill exists but no archived change has ever produced a `session-log.md`. The current approach tries to extract decisions retroactively from Claude Code's JSONL transcripts (Tier 1) or coordinator handoffs (Tier 2), both of which are fragile and agent-specific. When PRs are merged via `/merge-pull-requests` (especially cloud-created ones from Codex/Jules), there is no conversation history to extract from at all — triage decisions, vendor review findings, and user steering are lost.

## Solution

Refactor session-log from a retroactive extraction tool into a **living artifact** that agents append to at each workflow phase boundary. Since Claude, Codex, and Gemini all execute the same SKILL.md instructions, the agent itself writes structured decision records from its context window — the most reliable source.

### Key Changes

1. **Phase-boundary append pattern**: Each workflow skill (plan, iterate-plan, implement, iterate-implementation, validate, cleanup) appends a dated, agent-attributed section to `openspec/changes/<change-id>/session-log.md` as its final step before any approval gate.

2. **Sanitize-then-verify**: After every append, run `sanitize_session_log.py` on the file, then have the agent verify the output is coherent (catches both secret leaks and over-redaction).

3. **Merge log**: `/merge-pull-requests` writes to `docs/merge-logs/YYYY-MM-DD.md` (dated entries) capturing cross-PR triage reasoning, user decisions, vendor review findings, and merge/skip/close rationale. Brief PR comments are still posted on close/skip actions for contributor visibility.

4. **Retire extraction tiers**: Remove Tier 1 (JSONL transcript parsing) and Tier 2 (handoff document compilation) from `extract_session_log.py`. Keep the self-summary prompt template as a reference, and keep `sanitize_session_log.py` unchanged.

5. **Parallel review skills stay stateless**: `parallel-review-plan` and `parallel-review-implementation` are vendor-diverse and dispatched to external agents — they don't append to session-log.md directly. The orchestrating skill (plan-feature, implement-feature) captures review findings in its own session-log entry.

## Scope

- **In scope**: Refactor session-log skill, add append steps to 7 workflow skills, create merge-log pattern, update delta spec
- **Out of scope**: Changing the sanitization logic, modifying coordinator handoff format, adding session-log to non-workflow skills (bug-scrub, fix-scrub, explore-feature)

## Risks

- **File growth**: Append-only session-log.md could grow large for long-lived changes. Mitigated: most changes go through 3-5 phases; file stays under 200 lines.
- **Agent compliance**: Agents must follow the append template faithfully. Mitigated: template is embedded in SKILL.md instructions with concrete examples.
- **Sanitization false positives**: Over-redaction could mangle meaningful content. Mitigated: agent verifies output after sanitization.

## Success Criteria

- Every `/cleanup-feature` archive contains a `session-log.md` with at least one phase entry
- `/merge-pull-requests` produces dated merge-log entries in `docs/merge-logs/`
- `sanitize_session_log.py` runs after every append without blocking the workflow
- No secrets appear in committed session-log.md or merge-log files
