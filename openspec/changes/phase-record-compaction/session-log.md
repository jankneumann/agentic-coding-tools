# Session Log: phase-record-compaction

---

## Phase: Plan (2026-04-25)

**Agent**: claude-code (Opus 4.7) | **Session**: N/A

### Decisions
1. **Unify session-log and coordinator handoff behind a single PhaseRecord** `architectural: skill-workflow` — Both formats already overlap ~70% (Context↔summary, Decisions↔decisions). Drift is structural risk; one in-memory dataclass renderable to both formats removes drift by construction. Existing `LoopState.handoff_ids` field (line 64) is dead code today — populating it is backward-compat.
2. **Best-effort failure semantics for write_both()** `architectural: skill-workflow` — Each of (markdown append, sanitize, coordinator write) is independent; failures log warnings without raising. Matches existing sanitizer behavior at `skills/session-log/SKILL.md:138`. Strict atomicity would couple every phase boundary to coordinator availability.
3. **Local-file fallback at `openspec/changes/<id>/handoffs/<phase>-<N>.json`** `architectural: skill-workflow` — When coordinator is unreachable, JSON payload writes to a git-tracked local file with the same content. Auto-numbered like `count_phase_iterations`. Restores synchronization at the next phase boundary.
4. **Sub-agent isolation only for IMPLEMENT, IMPL_REVIEW, VALIDATE** `architectural: software-factory-tooling` — These are the heaviest phases; IMPLEMENT additionally uses `isolation: "worktree"` for file mutations. Lighter phases (PLAN, INIT, transitions) stay in the driver conversation. Driver receives only `(outcome, handoff_id)` from sub-agents — never the transcript.
5. **Crash recovery: retry from scratch up to 3 attempts** `architectural: software-factory-tooling` — Phases write artifacts incrementally; a re-run sees prior partial state and continues. Simplest model that preserves work. After 3 failures, write `phase-failed` PhaseRecord and raise `PhaseEscalationError` to operator.
6. **Token instrumentation via `anthropic.messages.count_tokens` with proxy fallback** `architectural: observability` — SDK call when available, char-count/4 proxy when offline, `AUTOPILOT_TOKEN_PROBE=disabled` to skip. Emits `phase_token_pre`/`post` audit-trail entries at each `_HANDOFF_BOUNDARIES` transition. Provides verifiable measurement for the ≥30% reduction success criterion.
7. **PhaseRecord lives in `skills/session-log/scripts/phase_record.py`** — Session-log skill already owns the template, sanitizer, and integration pattern. Putting PhaseRecord here keeps render+sanitize+data-model collocated. Approach B (separate skill) would split ownership without isolation benefit.
8. **Append_phase_entry stays as deprecation-warned shim** — Other callers exist outside the six phase-boundary skills (e.g., merge-pull-requests via append_merge_entry, ad-hoc scripts). Hard removal would break silently. Shim re-implements as a thin wrapper around `PhaseRecord.write_both()` and emits `DeprecationWarning`. Removal scheduled for follow-up after one release.
9. **Single coordinated change, 6-package DAG (Approach A over B)** — User confirmed at Gate 1. Atomic merge surface, parallelism via coordinator work-queue, integration test pass validates end-to-end before merge. wp-autopilot-layer-2 positioned as last leaf — droppable from merge if Layer 2 hits trouble, recovering Approach B's escape hatch.
10. **Proceed independently of harness-engineering-features** — Both proposals are plan-only, draft status, 0/N tasks done. Different concerns (review loops + failure-pattern memory in harness vs. format unification + sub-agent isolation here). Coordinator file locks at implement time handle file-level coordination. PhaseRecord becomes available infrastructure harness can adopt later if useful.

### Alternatives Considered
- **Strict atomic write_both (rollback all 3 steps on any failure)** — rejected because it couples session-log liveness to coordinator availability and would cascade routine workflow failures into skill failures
- **Mid-phase checkpoint handoffs for crash recovery** — rejected as protocol overkill; phases write artifacts incrementally, so retry-from-scratch sees the same intermediate state
- **Two-change split (model first, autopilot wiring second)** — rejected at Gate 1 in favor of single coordinated change with last-leaf risk isolation; user prioritized atomicity and integration-test coherence over PR size
- **Wait for harness-engineering-features to ship first** — rejected because that proposal has been Draft for 16 days with no implementation activity; risky to gate this on uncertain timeline
- **Heuristic estimation for 30% reduction metric (no instrumentation)** — rejected; user wanted a verifiable success criterion measurable in CI rather than prose claim
- **Separate `skills/phase-record/` skill** — rejected because session-log already owns the template, sanitizer, and integration pattern; splitting would create two skills always loaded together with no isolation benefit
- **Schema versioning for session-log template (v2)** — rejected by user; older changes simply lack the new sections, renderers omit empty sections, no migration needed

### Trade-offs
- Accepted **best-effort write_both** over strict atomicity — phase-boundary writes proceed even when coordinator is unreachable; sync is restored at the next boundary via local-file fallback
- Accepted **6-skill simultaneous retrofit** over phased migration — eliminates drift window but increases PR size; rationale: change is mechanical (same pattern repeated 6 times)
- Accepted **driver opacity to sub-agent transcripts** over diagnostic introspection — driver `LoopState` delta after Layer 2 phase returns is bounded by `(outcome, handoff_id)`; intermediate state is observable only via filesystem artifacts the sub-agent writes (commits, validation-report.md)
- Accepted **idempotency burden at sub-agent call site** over framework-level checkpoint protocol — phase sub-agents doing irreversible operations (e.g., `git push`) must handle "I may have already done this" because the driver's retry contract is "we will call you again with the same input"
- Accepted **architectural-tag inline-span fragility** over structured-only representation — Decision.capability round-trips through markdown as `` `architectural: <capability>` `` to preserve compatibility with `make decisions` regenerator; structured field exists in PhaseRecord, but markdown emission must keep the inline format

### Open Questions
- [ ] Coordinator HTTP API key needs `register_feature` and `recall` permissions for full coordination — registered manually in this session, but autopilot dispatches should not require these specific permissions if degraded mode is supported (currently they fail silently with 403). Track as a follow-up: should `register_feature` / `recall` failures be treated as warnings or as hard errors during plan-feature?
- [ ] If `phase-token-meter` proxy estimate diverges from SDK count by >20%, do we report both numbers in the validation report and flag the divergence, or pick the more conservative (higher) value for the success criterion check?

### Completed Work
- Discovery: 4 questions answered (coordination strategy, atomic-failure semantics, crash recovery, metrics)
- Approach selection: Approach A (single coordinated change with 6-package staged DAG) confirmed at Gate 1
- Proposal artifact written
- Design.md with 10 design decisions written
- Spec delta for `skill-workflow` capability with 8 ADDED requirements and 21 scenarios written
- Tasks.md with 36 tasks across 6 phases (TDD-ordered, spec/decision references attached)
- Contracts: 2 JSON Schemas (phase-record, handoff-local-fallback) + README.md
- Work-packages.yaml with 6-package DAG; all four validators pass (openspec strict, work-packages schema, lock-keys canonicalization, parallel-zones scope/lock overlap)
- Coordinator `register_feature` attempted (403 — API key permission gap; not blocking)

### In Progress
- Awaiting Gate 2 plan approval before implementation begins

### Next Steps
- Gate 2: present complete plan to user for final approval
- On approval: `/implement-feature phase-record-compaction` dispatches the 6-package DAG via coordinator
- First package to execute: `wp-contracts` (no dependencies)
- Critical path: wp-contracts → wp-phase-record-model → wp-autopilot-layer-1 → wp-autopilot-layer-2 → wp-integration (5 packages serially); wp-skills-retrofit can parallelize with wp-autopilot-layer-1 and wp-autopilot-layer-2 after wp-phase-record-model

### Relevant Files
- `openspec/changes/phase-record-compaction/proposal.md` — feature description, motivation, approaches considered
- `openspec/changes/phase-record-compaction/design.md` — 10 design decisions with rationale and trade-offs
- `openspec/changes/phase-record-compaction/specs/skill-workflow/spec.md` — 8 ADDED requirements + 21 WHEN/THEN scenarios
- `openspec/changes/phase-record-compaction/tasks.md` — 36 tasks in 6 phases, TDD-ordered
- `openspec/changes/phase-record-compaction/contracts/schemas/phase-record.schema.json` — JSON Schema for the unified data model
- `openspec/changes/phase-record-compaction/contracts/schemas/handoff-local-fallback.schema.json` — JSON Schema for local-file fallback envelope
- `openspec/changes/phase-record-compaction/work-packages.yaml` — 6-package DAG with locks, scope, verification per package
- `skills/session-log/scripts/extract_session_log.py:32` — `append_phase_entry` to be wrapped by `write_both`
- `skills/session-log/SKILL.md:122-139` — append-sanitize-verify flow (model for write_both)
- `skills/autopilot/scripts/autopilot.py:47-72` — `LoopState` to add `last_handoff_id` field
- `skills/autopilot/scripts/autopilot.py:689-712` — `_HANDOFF_BOUNDARIES` + `_maybe_handoff` dispatch site to enrich
- `agent-coordinator/src/handoffs.py:105-224` — `HandoffService.write/read` API consumed unchanged
- `agent-coordinator/database/migrations/002_handoff_documents.sql` — handoff schema (no migration required)

### Context

Planning the `phase-record-compaction` change to address Opus 4.7's faster context-window accumulation in autopilot runs. The core insight from discussion was that artifacts (proposal.md, tasks.md, review-findings JSONs, validation reports) already capture phase outputs at full fidelity — only the conversation scaffolding around them needs to be discarded at boundaries. The user's mental model — "/clear at phase boundaries, then re-prime with artifacts + compacted handoff" — maps cleanly onto sub-agent isolation with structured handoff payloads. The design unifies the existing session-log and coordinator-handoff persistence mechanisms (currently overlapping ~70% but drifting) behind a single `PhaseRecord` data model, then wires autopilot to populate structured handoffs at existing boundaries (Layer 1) and run heavy phases as ephemeral sub-agents that return only `(outcome, handoff_id)` (Layer 2). Token-counting instrumentation provides a verifiable ≥30% peak-context-reduction success criterion. Approach A (single coordinated change with 6-package DAG) was selected over Approach B (split into model+wiring changes) because the work-package DAG already gives Approach B's parallelism benefit and the integration test pass at `wp-integration` validates end-to-end behavior before merge — something the split approach sacrifices. Risk mitigation: Layer 2 (the highest-risk piece) is positioned as the last leaf, droppable from merge without losing the format unification.
