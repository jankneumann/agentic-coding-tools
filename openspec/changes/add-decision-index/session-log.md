# Session Log: add-decision-index

---

## Phase: Plan (2026-04-16)

**Agent**: claude_code | **Session**: adr-evaluation-GeYN0

### Decisions
1. **Extend archive-intelligence with a new emitter pass** `architectural: software-factory-tooling` — reuses the existing walker over `openspec/changes/**/session-log.md`; avoids duplicating archive-discovery and incremental-indexing logic in a parallel script.
2. **Inline backtick tag `architectural: <capability>` on Decision bullets** `architectural: skill-workflow` — kebab-case identifiers are already allowlisted by `sanitize_session_log.py` and backticks are not scanned; requires zero sanitizer changes.
3. **Per-bullet tag granularity over per-phase tagging** `architectural: skill-workflow` — a single phase commonly contains Decisions affecting multiple capabilities; per-bullet avoids the one-capability-per-phase constraint and the list-of-tags ambiguity.
4. **Split spec deltas across skill-workflow and software-factory-tooling** `architectural: skill-workflow` — tagging schema is a write-side concern belonging to skill-workflow; emission is a cross-change projection belonging to software-factory-tooling; keeping them in separate deltas matches existing ownership.
5. **Heuristic classifier plus agent review for systematic backfill** `architectural: software-factory-tooling` — roughly thirty archived session-logs make pure manual labeling infeasible; pure heuristic produces enough miscategorizations to poison trust in the index on day one; hybrid gives coverage with curation.
6. **One markdown file per capability under docs/decisions/** `architectural: software-factory-tooling` — aligns the read-side axis with `openspec/specs/<capability>/`; archaeology questions are asked per-capability, not globally; scrolling a monolithic index does not serve the use case.
7. **Explicit supersession via `supersedes: <change-id>#D<n>` syntax** `architectural: skill-workflow` — inferred supersession introduces wrong-but-confident heuristic calls; explicit is verifiable at CI time and auditable by readers.
8. **Generated README over hand-maintained README** `architectural: software-factory-tooling` — the capability set will grow over time (16 today); hand-maintenance diverges from reality; `make decisions` emits the README as part of the same pass.
9. **Introduce `make decisions` and CI staleness check as a first-class generalizable pattern** `architectural: software-factory-tooling` — today neither `make architecture` nor any other regenerate-then-diff build step runs in CI, meaning stale generated artifacts can land on main undetected; this change introduces the pattern for decisions and opens a follow-up to extend it to architecture.

### Alternatives Considered
- Approach B, standalone walker under skills/session-log/: rejected because it duplicates the archive walker in `archive_index.py` and splits which-archived-changes-exist state across two scripts, inviting divergence.
- Approach C, YAML sidecar per change (`decisions.yaml`): rejected because it requires writing every Decision twice — once in session-log prose, once as structured data — or demoting session-log to a YAML-driven artifact; a far heavier process shift than the indexing gap justifies. Reconsiderable later if session-logs move toward structured data for unrelated reasons.
- Per-phase architectural tag on the phase header: rejected because a single phase often contains Decisions affecting multiple capabilities; this would force a one-capability-per-phase discipline (unnatural) or a list-of-tags schema (ambiguous when bullets do not map 1-to-1 to tags).
- Pure heuristic backfill without review: rejected because keyword-only classification miscategorizes often enough to damage trust in the index on day one.
- Skip backfill and tag only going forward: rejected because it leaves the index empty for months and delivers no immediate value against the motivating archaeology use case.
- Global ADR numbering (ADR-0001, ADR-0002, and so on): rejected because it buries the per-capability narrative; readers ask questions in capability terms, not by global ordinal.
- Extend `sanitize_session_log.py` to understand the tag explicitly: rejected as unnecessary — the existing allowlist already accepts kebab-case identifiers and backticks are already non-scanned.

### Trade-offs
- Accepted per-bullet tagging verbosity over per-phase tag simplicity because precision in the index beats fewer keystrokes in the log.
- Accepted hybrid backfill review cost over pure heuristic speed because initial index quality compounds — a miscategorized bootstrap poisons every future query.
- Accepted coupling the decision index cadence to archive-intelligence runs over a decoupled independent walker because a single source of truth for archive state eliminates cross-script drift.
- Accepted inline tag in prose over separate structured sidecar because single-write economy preserves the existing session-log discipline and avoids bifurcating the data model.
- Accepted explicit supersession declaration over inferred supersession because wrong-but-confident inference damages reader trust more than occasional missed links damage completeness.

### Open Questions
- [ ] Exact form of the `supersedes:` reference syntax. Design.md proposes `supersedes: <change-id>#D<n>` (decision index within phase) but the `#D<n>` numbering convention needs to survive phase iterations and cross-phase supersession. Alternative: title-hash or phase-slug anchors.
- [ ] Deterministic phase-entry anchor scheme for back-reference links (for example, `session-log: <change-id>/<phase-slug>/D<n>`) that remains stable across re-sanitization runs.
- [ ] Whether the emitter should silently skip archived changes that predate the session-log convention (no `session-log.md` file), or emit an info-level note. Lean toward silent-skip to keep output quiet, but this is a reader-experience call.
- [ ] Whether `make architecture` should adopt the same CI staleness-check pattern in a follow-up change once `make decisions` proves it.
- [ ] Sanitizer observation: `sanitize_session_log.py` treats paired double-quote marks across many lines as a single quoted string and flags the interior as high-entropy. Authors should keep interior rhetorical quotes balanced on the same line, or use italics/backticks for emphasis. Worth capturing as a Decision in `docs/decisions/skill-workflow.md` once the emitter ships, and worth a defensive test case in the sanitizer suite.

### Context
Planning goal: introduce a per-capability decision index so that archaeology questions about how the system arrived at its current state can be answered per capability rather than by reading many per-change session-logs in chronological order. Exploration revealed the existing Archive Intelligence Pipeline already walks session-logs for machine-readable indexing, so the right move is to extend it with a new emitter rather than add a parallel walker. Sequential tier (no coordinator available, scope small). Gate 1 confirmed Approach A; Gate 2 pending.
