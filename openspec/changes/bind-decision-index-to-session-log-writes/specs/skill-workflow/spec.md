# skill-workflow — delta

## MODIFIED Requirements

### Requirement: Phase Record Persistence Pipeline

The `PhaseRecord.write_both()` method SHALL persist the record through a four-step pipeline in this fixed order: (1) append the rendered markdown to `openspec/changes/<change-id>/session-log.md`, (2) run `sanitize_session_log.py` in-place on the file, (3) write the structured payload to the coordinator via `HandoffService.write(...)` or fall back to a local file, (4) regenerate the per-capability decision index that the appended markdown invalidates.

Each step SHALL be best-effort with independent failure handling. A failure in any step SHALL log a warning to stderr and SHALL NOT raise an exception. The method SHALL return a `PhaseWriteResult` dataclass containing `markdown_path: Path | None`, `sanitized: bool`, `handoff_id: str | None`, `handoff_local_path: Path | None`, and `warnings: list[str]`.

When the coordinator write fails (returns `success=False`, raises, or times out), `write_both()` SHALL write the same payload as JSON to `openspec/changes/<change-id>/handoffs/<phase-slug>-<N>.json` where `<phase-slug>` is `phase_name.lower().replace(" ", "-")` and `<N>` auto-increments per phase using the same counting logic as `count_phase_iterations`.

Step four SHALL run unconditionally, with no flag or environment variable governing it. A session-log entry carries the capability-tagged decisions the index is derived from, so writing one without regenerating produces drift the writer created and the writer alone can prevent.

#### Scenario: All three steps succeed
- **WHEN** `PhaseRecord(...).write_both()` is called with coordinator available
- **THEN** the markdown SHALL be appended to `session-log.md`
- **AND** the sanitizer SHALL run in-place and exit zero
- **AND** the coordinator SHALL receive a `write_handoff` call returning `success=True`
- **AND** the result SHALL contain `handoff_id` and `markdown_path`, with `warnings = []`

#### Scenario: Coordinator unavailable triggers local-file fallback
- **WHEN** `PhaseRecord(...).write_both()` is called and the coordinator returns `success=False` or raises
- **THEN** the markdown append and sanitization SHALL still complete
- **AND** the JSON payload SHALL be written to `openspec/changes/<change-id>/handoffs/<phase-slug>-<N>.json`
- **AND** the result SHALL contain `handoff_local_path` set to the JSON file path
- **AND** the result SHALL contain a warning describing the coordinator failure
- **AND** no exception SHALL be raised

#### Scenario: Sanitizer failure does not block coordinator write
- **WHEN** `PhaseRecord(...).write_both()` is called and the sanitizer exits non-zero
- **THEN** the markdown append SHALL still complete
- **AND** the coordinator write SHALL still proceed using the unsanitized in-memory payload
- **AND** the result SHALL contain `sanitized=False` and a warning describing the sanitizer failure

#### Scenario: Markdown append failure does not block coordinator write
- **WHEN** `PhaseRecord(...).write_both()` is called and the markdown append fails (e.g., disk full, permission denied)
- **THEN** the coordinator write SHALL still proceed
- **AND** the result SHALL contain `markdown_path=None` and a warning describing the append failure

#### Scenario: Regeneration leaves the decision index current
- **GIVEN** a session-log entry carrying at least one capability-tagged decision
- **WHEN** `PhaseRecord(...).write_both()` completes
- **THEN** the per-capability decision index SHALL match what a fresh regeneration would produce
- **AND** a subsequent regeneration SHALL produce no further change

#### Scenario: Regeneration failure does not lose the session log
- **WHEN** `PhaseRecord(...).write_both()` is called and the regeneration step raises or exits non-zero
- **THEN** the appended markdown SHALL remain on disk unchanged
- **AND** the result SHALL still report `markdown_path` and the handoff outcome
- **AND** the result SHALL contain a warning describing the regeneration failure
- **AND** no exception SHALL be raised

#### Scenario: Regeneration is skipped when the generator is absent
- **GIVEN** a checkout in which the decision-index generator cannot be resolved
- **WHEN** `PhaseRecord(...).write_both()` is called
- **THEN** the first three steps SHALL complete as before
- **AND** the result SHALL contain a warning naming the missing generator
- **AND** no exception SHALL be raised

## ADDED Requirements

### Requirement: Session-log persistence is orchestrator-scoped

`PhaseRecord.write_both()` SHALL be invoked only from orchestrator phase-boundary steps, never from a work-package worker.

Step four writes the decision index at `docs/decisions/`, which lies outside the declared write scope of every work package. A worker that called `write_both()` would therefore write outside its `write_allow` and fail the deterministic scope check. The restriction is presently a convention of how the phase-boundary skills are written; this requirement makes it enforceable so the coupling cannot be broken silently by a future skill.

#### Scenario: No worker call site invokes the persistence pipeline
- **WHEN** the skill payload is inspected for `write_both()` call sites
- **THEN** every call site SHALL belong to an orchestrator phase-boundary step
- **AND** no work-package worker prompt SHALL invoke it

### Requirement: Decision-index drift remains a gate finding

Binding regeneration to session-log writes SHALL NOT remove, weaken, or make optional the drift gate's check on the decision index.

The binding removes one cause of drift; other causes remain, including a hand-edited session log, a manual archive move, and any future writer that bypasses `PhaseRecord`. A check that stopped reporting those would trade a narrow convenience for the class of silent divergence the gate exists to prevent.

#### Scenario: A hand-edited session log still reports drift
- **GIVEN** a session-log file edited directly, without `PhaseRecord.write_both()`
- **WHEN** the deterministic context drift gate runs
- **THEN** the decision-index producer SHALL report drift
- **AND** that finding SHALL contribute to the blocking exit code on every event where blocking drift counts
