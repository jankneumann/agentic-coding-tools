# Design: Store Conversation History with OpenSpec Changes

## Context

OpenSpec changes already archive proposal, design, specs, tasks, and validation artifacts — capturing what was planned and what was built. Missing is the *reasoning* behind implementation choices: why a particular approach was chosen, what alternatives were considered and rejected, and what trade-offs were accepted. This context currently lives only in ephemeral agent sessions that are discarded after cleanup.

The project already has several context-persistence mechanisms:
- **Handoff documents** (coordinator DB) — structured session-boundary summaries with decisions and next_steps
- **Episodic memory** (coordinator DB) — outcome-focused events with lessons learned
- **Audit trail** (coordinator DB) — immutable operation log

However, none of these are committed to git alongside the change artifacts, and database-backed storage requires the coordinator to be running — which is optional.

## Goals

1. Capture decision rationale as a git-committed artifact alongside each OpenSpec change
2. Work without the coordinator (standalone mode) — the agent can always self-summarize
3. No secrets or sensitive information committed to the repository
4. Minimal disruption to the existing cleanup workflow

## Non-Goals

1. Full conversation transcript storage — too verbose, contains code already in diffs
2. Real-time conversation streaming — only capture at cleanup time
3. Replacing handoff documents or episodic memory — those serve different purposes (cross-session continuity vs. permanent record)
4. Capturing session history for non-OpenSpec work

## Decisions

### Decision 1: File-based artifact in the OpenSpec change directory (not database)

**Chosen**: Store as `session-log.md` in `openspec/changes/<change-id>/`, archived with the change.

**Alternatives considered**:
- *Database table in coordinator* — Rejected because: (a) requires coordinator to be running, (b) doesn't travel with the repo when cloned, (c) handoff/memory tables already serve the ephemeral use case
- *Separate git branch for logs* — Rejected because: adds operational complexity, fragments context away from the change it describes
- *Append to existing proposal.md or design.md* — Rejected because: pollutes planning artifacts with implementation-time observations, breaks the principle that planning artifacts are frozen before implementation

**Trade-off**: File size in git history. Mitigated by enforcing a 500-line summary limit and requiring distillation rather than transcription.

### Decision 2: Three-tier extraction strategy (transcript → handoffs → self-summary)

**Chosen**: Attempt extraction in priority order:
1. **Agent session transcript** (e.g., Claude Code's local session storage) — richest source
2. **Handoff document history** (if coordinator available) — structured but less detailed
3. **Agent self-summary** — the agent summarizes from its current context window as a last resort

**Alternatives considered**:
- *Only self-summary* — Rejected because: misses context from earlier sessions that have been compressed out of the context window
- *Only transcript parsing* — Rejected because: not all agents expose transcripts, and it's fragile to format changes
- *Require coordinator for all history* — Rejected because: coordinator is optional and many users run in standalone mode

**Trade-off**: Self-summary quality degrades for very long sessions where early context has been compressed. Acceptable because handoff documents (tier 2) capture session-boundary decisions even when the full transcript is lost.

### Decision 3: Sanitization as a hard gate

**Chosen**: Run a sanitization script with regex-based secret detection and entropy analysis. If the script fails (exit code 1), the session log is NOT committed. Cleanup proceeds without it.

**Alternatives considered**:
- *Sanitize and always commit* — Rejected because: a sanitization failure could mean secrets slipped through
- *Manual review required* — Rejected because: adds friction, defeats the automation purpose
- *Skip sanitization entirely* — Rejected because: unacceptable risk of committing API keys, tokens, or connection strings

**Trade-off**: Aggressive redaction may occasionally remove non-sensitive content (false positives on high-entropy strings). Preferable to the alternative of leaking secrets.

### Decision 4: Infrastructure skill (not inline script)

**Chosen**: Package extraction and sanitization as `skills/session-log/` with scripts under `scripts/`.

**Alternatives considered**:
- *Inline in cleanup skill SKILL.md* — Rejected because: the sanitization logic is non-trivial and benefits from unit testing; the Sibling-Relative Path Resolution and Infrastructure Skill Packaging requirements mandate this pattern
- *Part of agent-coordinator* — Rejected because: this operates on local files, not coordinator state

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Session transcript format changes across Claude Code versions | Tier 2 (handoffs) and tier 3 (self-summary) provide fallback |
| Sanitization misses a novel secret pattern | Entropy-based detection catches unknown formats; exit-on-error prevents committing |
| Large session logs bloat git history | 500-line limit enforced; summarization required |
| Self-summary may hallucinate or omit important context | Structured sections constrain the output; handoff documents provide ground-truth anchors |

## Migration Plan

No migration needed — this is a purely additive change. Existing archived changes remain valid without `session-log.md`. The artifact is registered as optional in the schema.
