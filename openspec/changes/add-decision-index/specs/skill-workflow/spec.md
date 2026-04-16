# skill-workflow — Delta Spec for add-decision-index

## ADDED Requirements

### Requirement: Phase Entry Decision Tagging

Session-log Phase Entries SHALL support an optional inline `architectural: <capability>` marker on individual Decision bullets to identify decisions that warrant inclusion in the per-capability decision index.

The tag SHALL use the syntax `` `architectural: <kebab-case-capability>` `` — a backtick-delimited inline code span containing the literal key `architectural`, a colon, a single space, and a kebab-case identifier matching a capability directory under `openspec/specs/`.

The tag MAY appear anywhere within a Decision bullet's first line (after the title, before the rationale, or at the end). Only the first occurrence per bullet SHALL be counted by the index emitter; subsequent occurrences SHALL be ignored to keep the extraction rule deterministic.

Decision bullets without an `architectural:` tag SHALL remain valid and SHALL NOT be required to include one. Untagged Decisions document decisions that do not warrant cross-change surfacing (routine, scoped, already-superseded-in-same-change, etc.).

The tag MUST NOT alter the existing Phase Entry section structure (Decisions, Alternatives Considered, Trade-offs, Open Questions, Context). The `sanitize_session_log.py` rules SHALL continue to accept tagged entries without modification — verified by the existing allowlist for kebab-case identifiers up to 52 characters and the sanitizer's non-scanning of backtick inline code.

#### Scenario: Single tagged decision in a phase entry
- **WHEN** a workflow skill appends a Phase Entry containing `1. **Pin worktrees during overnight pauses** \`architectural: software-factory-tooling\` — prevents GC`
- **THEN** the entry SHALL be written to `session-log.md` unchanged after sanitization
- **AND** the decision-index emitter SHALL extract exactly one Decision tagged with capability `software-factory-tooling`

#### Scenario: Multiple decisions in one phase targeting different capabilities
- **WHEN** a phase entry contains two Decision bullets with different `architectural:` tags (e.g., `skill-workflow` and `agent-coordinator`)
- **THEN** each Decision SHALL appear in its respective capability's index file
- **AND** both references SHALL link back to the same originating phase entry

#### Scenario: Untagged decision remains valid
- **WHEN** a phase entry contains a Decision bullet without any `architectural:` tag
- **THEN** the entry SHALL validate and commit without warnings
- **AND** the Decision SHALL be excluded from `docs/decisions/<capability>.md` output

#### Scenario: Tag with invalid capability is reported
- **WHEN** a phase entry contains `\`architectural: no-such-capability\`` where no `openspec/specs/no-such-capability/` directory exists
- **THEN** the emitter SHALL emit a warning identifying the change-id, phase name, and invalid capability
- **AND** the emitter SHALL exit with a non-zero status if invoked in `--strict` mode (used by CI)
- **AND** in non-strict mode the emitter SHALL skip the malformed Decision and continue processing other entries

#### Scenario: Sanitizer preserves tagged decisions
- **WHEN** `sanitize_session_log.py` runs in-place on a session-log containing `\`architectural: skill-workflow\`` inline tags
- **THEN** the tag SHALL remain unredacted in the output
- **AND** no `[REDACTED:*]` markers SHALL appear on the tag string
