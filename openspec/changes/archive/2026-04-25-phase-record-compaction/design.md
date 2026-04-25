# Design: Phase-Record Compaction

**Change ID**: phase-record-compaction
**Status**: Draft

## Design Decisions

### D1: PhaseRecord lives inside the session-log skill

**Decision**: `PhaseRecord`, `Decision`, `Alternative`, `TradeOff`, and `FileRef` dataclasses live in `skills/session-log/scripts/phase_record.py`, alongside the existing `extract_session_log.py` and `sanitize_session_log.py`.

**Rationale**: The session-log skill already owns the phase-entry template, sanitization pipeline, and call-site integration pattern. Putting `PhaseRecord` here keeps the rendering logic (markdown), the sanitization logic, and the data model collocated — consumers import one module instead of three. Creating a separate `skills/phase-record/` skill would split ownership across two directories with no cohesion benefit.

**Trade-offs**: The session-log skill's API surface grows. Accepted because the alternative (a separate skill) gives no real isolation — the two skills would always be loaded together.

### D2: `write_both()` is best-effort with each step independent

**Decision**: `PhaseRecord.write_both()` runs three steps sequentially — `append_markdown` → `sanitize_inplace` → `write_handoff` — and treats each step as an independent best-effort operation. Each step logs warnings on failure but does not raise. Markdown append is the only step that's nearly always safe (local file write); sanitizer failure (exit 1) follows existing skill convention of "log and continue"; coordinator unavailability triggers fallback to local-file mirror without raising.

**Rationale**: Matches the existing sanitizer behavior already documented in `skills/session-log/SKILL.md:138` ("If sanitization exits non-zero: do NOT commit, log warning, continue workflow"). Strict atomic semantics would couple every phase-boundary write to coordinator availability and make routine workflow failures cascade into skill failures. The user explicitly chose this trade-off at Gate 0 discovery.

**Trade-offs**: A partial failure can leave session-log and coordinator slightly out of sync (e.g., markdown appended but coordinator unreachable). Mitigation: the coordinator-unavailable branch falls back to a local file (`openspec/changes/<id>/handoffs/<phase>-<N>.json`) which gets git-tracked alongside the session-log, restoring synchronization at the next phase boundary.

### D3: Local-file fallback at `openspec/changes/<id>/handoffs/<phase>-<N>.json`

**Decision**: When `HandoffService.write()` returns `success=False` or raises (coordinator unreachable, policy denial, network error), `write_both()` writes the same payload as JSON to `openspec/changes/<change-id>/handoffs/<phase>-<N>.json`, where `<N>` auto-increments per phase like `count_phase_iterations` does for the markdown log. The file is git-tracked.

**Rationale**: Matches the local-first persistence strategy used elsewhere (proposal.md, tasks.md, validation reports — all live in `openspec/changes/<id>/`). The next phase's sub-agent (Layer 2) reads handoffs in priority order: coordinator → local file → none. Git tracking means handoffs survive worktree teardown.

**Trade-offs**: Adds a small directory of small JSON files per change. Negligible — typical change accumulates ~6-12 handoffs total.

### D4: Three-step pipeline ordering — markdown first, sanitize second, coordinator third

**Decision**: Steps run in this fixed order: (1) append markdown to `session-log.md`, (2) sanitize in-place, (3) write to coordinator. The sanitized markdown content is also what feeds the coordinator's `summary` and `decisions` JSONB fields after re-parsing.

**Rationale**: Sanitization must happen before coordinator write so secrets never leave the local filesystem. Sanitization happens after markdown append (rather than before) because the sanitizer operates on the file in-place — this matches the existing pattern at `skills/session-log/SKILL.md:122-139` exactly. Putting coordinator write last lets us include the sanitized content in the handoff payload, ensuring the coordinator never receives secrets.

**Trade-offs**: One extra file read between sanitize and coordinator-write to extract sanitized content. Negligible (file is small).

### D5: `append_phase_entry()` stays as a deprecated shim

**Decision**: The existing `append_phase_entry(change_id, phase_name, content, session_log_path=None)` function in `extract_session_log.py:32` is kept and re-implemented as a thin wrapper that constructs a minimal `PhaseRecord` from the prose content and calls `write_both()`. A `DeprecationWarning` is emitted on each call. Removal is scheduled for a follow-up change after one release.

**Rationale**: Other callers exist outside the six phase-boundary skills (e.g., `merge-pull-requests` writes to `merge-log` via `append_merge_entry`, but tooling and ad-hoc scripts may still use `append_phase_entry`). Hard-removal would break those silently. The shim preserves the call-site contract while routing through the new pipeline, so all writes get the new sanitization behavior consistently.

**Trade-offs**: Two API surfaces during transition. Accepted because the shim is shallow (~10 lines) and the deprecation warning makes the migration discoverable.

### D6: Sub-agent return contract — `(outcome: str, handoff_id: str)`

**Decision**: Phase sub-agents (Layer 2) invoked via `Agent(...)` return exactly two pieces of information to the autopilot driver: an `outcome` string (matching the existing phase-callback outcome vocabulary: `"continue"`, `"escalate"`, `"abort"`, etc.) and a `handoff_id` string referencing the structured `PhaseRecord` they wrote at exit. The driver never reads the sub-agent's transcript and never passes structured data back through the function-return interface.

**Rationale**: This is the core compaction mechanism. The driver's `LoopState` after a sub-agent call equals `LoopState before + {last_handoff_id, handoff_ids[-1]}` — a bounded delta. All conversation context the sub-agent accumulated is discarded on return. The next phase's sub-agent reads the handoff via `read_handoff(handoff_id=...)` or the local fallback file.

**Trade-offs**: The driver cannot inspect intermediate state during a phase sub-agent's run for diagnostic purposes. Mitigation: the sub-agent writes interim artifacts (commits, `validation-report.md`, etc.) that are visible on the filesystem; if a phase fails, the driver retries with the same incoming handoff and the artifacts on disk provide partial-progress recovery.

### D7: Worktree isolation only for `IMPLEMENT`

**Decision**: Of the three Layer-2 phases (`IMPLEMENT`, `IMPL_REVIEW`, `VALIDATE`), only `IMPLEMENT` invokes `Agent(..., isolation: "worktree")`. `IMPL_REVIEW` and `VALIDATE` run in the shared checkout because they're predominantly read-only or produce isolated artifacts (review findings JSON, validation report).

**Rationale**: Worktree isolation has setup cost (~5-15s for fresh worktree) and only pays off when the phase mutates files in ways that could conflict with parallel work. `IMPL_REVIEW` reads code and writes findings to a per-package JSON file in the change directory (no conflict surface). `VALIDATE` produces `validation-report.md` and uses Docker but doesn't mutate the source tree. Only `IMPLEMENT` writes substantial code.

**Trade-offs**: A bug in `IMPL_REVIEW` or `VALIDATE` could in theory corrupt the shared checkout. Accepted because both phases already run in the shared checkout under the current architecture without issues, and the corruption blast radius is contained by git (uncommitted changes can be inspected and discarded).

### D8: Crash recovery via retry-from-scratch with the same incoming handoff (max 3 attempts)

**Decision**: When a phase sub-agent crashes, exits non-zero, or returns malformed output, the autopilot driver re-invokes it with the same `(artifacts manifest, incoming PhaseRecord)` prompt up to 3 times. Each retry is a fresh sub-agent (no transcript inheritance). After the third failure, the driver writes a `phase-failed` PhaseRecord to the coordinator and raises `PhaseEscalationError(phase_name, last_attempt_error)` to the operator.

**Rationale**: Phase artifacts are written incrementally (commits, partial files), so a re-run sees the prior partial state and continues. This is the simplest recovery model that preserves work — no checkpoint protocol, no mid-phase handoff coordination. The user explicitly chose this trade-off at Gate 0 discovery.

**Trade-offs**: A phase doing irreversible side effects (e.g., `git push` in cleanup, `gh pr merge`) needs idempotency at the call site. The driver's retry contract is "we will call you again with the same input"; the sub-agent must handle "I may have already done this." Mitigation: cleanup-feature already uses `--force-with-lease` semantics for push and `gh pr merge --auto` (which is idempotent on a merged PR). Document this contract in the phase-agent README.

### D9: Token instrumentation via `anthropic.messages.count_tokens` with transcript-length proxy fallback

**Decision**: At each phase boundary, autopilot records two numbers to the coordinator audit trail: `pre_phase_tokens` and `post_phase_tokens`. The primary measurement uses `anthropic.messages.count_tokens(messages=...)` if the SDK is available; the fallback proxy is `sum(len(msg["content"]) for msg in messages) / 4` (rough char-to-token ratio). A configuration flag `AUTOPILOT_TOKEN_PROBE=disabled` skips measurement entirely for offline runs.

**Rationale**: The SDK's `count_tokens` is the authoritative source but requires network. The proxy gives a usable estimate offline. ~50 LOC: a thin `phase_token_meter.py` helper and 6 call sites in `autopilot.py` (one per phase entry/exit).

**Trade-offs**: Proxy estimates can drift from actual token counts by ±20%. Accepted because the success criterion (≥30% reduction) has enough margin to tolerate proxy noise; production runs use the SDK call when available.

### D10: Markdown rendering preserves `architectural:` tag round-trip

**Decision**: `Decision.capability` (kebab-case string) round-trips through the markdown rendering as the inline span `` `architectural: <capability>` ``, positioned between the title and the `—` delimiter. `Decision.supersedes` round-trips as `` `supersedes: <change-id>#D<n>` ``. The inline-span format is unchanged from the current template at `skills/session-log/SKILL.md:97-104`.

**Rationale**: The `make decisions` regenerator at `Makefile` parses these inline spans to build per-capability indexes (`docs/decisions/<capability>.md`). Changing the format would silently break the index regeneration. Round-trip preservation means: a `PhaseRecord` parsed from markdown produces an identical `PhaseRecord` after `render_markdown()`, and the decision-index regenerator continues to work without modification.

**Trade-offs**: The structured `Decision.capability` field duplicates information already encoded in the markdown. Accepted because programmatic consumers (next-phase sub-agents) get the structured form, while human readers and the index regenerator get the markdown form, without either having to parse the other.

## Data Flow Diagram

```
Phase boundary in autopilot
        │
        ▼
   build_phase_record(state, prev, next)
        │
        ▼
   PhaseRecord (in-memory dataclass)
        │
        ├──── render_markdown() ──► append to session-log.md ──► sanitize_inplace() ──┐
        │                                                                              │
        └──── to_handoff_payload() ──► HandoffService.write() ◄────────────────────────┘
                                              │
                                              ▼
                              Success: handoff_id ──► state.handoff_ids.append()
                                                    └─► state.last_handoff_id = id
                                              │
                                              ▼
                              Failure: write JSON to openspec/changes/<id>/handoffs/<phase>-<N>.json
                                                    └─► state.last_handoff_id = "local:<path>"
        │
        ▼
   Next phase sub-agent receives:
        - artifacts manifest (paths only)
        - last_handoff_id (resolves to PhaseRecord via coord or local file)
        - phase task instructions
```

## Cross-Cutting Concerns

### Test strategy

- **Unit (round-trip)**: `PhaseRecord ↔ markdown ↔ PhaseRecord` produces equal objects; same for `PhaseRecord ↔ handoff_payload ↔ PhaseRecord`
- **Integration (write_both)**: tmp-dir based test exercising all three steps with mock coordinator (success), real local-file fallback (coordinator-unavailable), and partial sanitizer failure
- **Skill-level**: each of the six phase-boundary skill SKILL.md files has at least one test asserting that running the skill produces both a session-log.md entry AND a coordinator handoff (or local-file fallback) with matching content
- **Autopilot Layer 1**: `_HANDOFF_BOUNDARIES` set continues to fire; structured payload now matches `PhaseRecord` schema; `state.handoff_ids` accumulates
- **Autopilot Layer 2**: sub-agent invocation contract test asserts driver's `LoopState` delta after phase return is bounded (no transcript leak)
- **Crash recovery**: simulated sub-agent failure triggers 3 retries; final failure raises `PhaseEscalationError`
- **Token instrumentation**: counts recorded for at least 4 of 9 boundaries on a representative run; reduction ≥30% comparing pre-Layer-2 vs post-Layer-2

### Migration / Rollout

This change has no schema migration (handoff_documents JSONB columns unchanged) and no data migration (existing session-log.md files keep working — they just lack `Completed Work` and `Relevant Files` sections, which renderers omit when empty). The `LoopState` field additions (`last_handoff_id`) default to `None`, so existing autopilot snapshots load unchanged.

After merge, the existing `LoopState.handoff_ids: list[str]` field begins being populated (it's been dead code since introduction). No external observable change beyond the new sections in session-log.md and rows appearing in `handoff_documents`.

### Backward compatibility

- `append_phase_entry()` remains as a deprecation-warned shim that constructs a minimal `PhaseRecord` and calls `write_both()` — no caller change required
- `count_phase_iterations()` and `append_merge_entry()` are unchanged (used by `merge-pull-requests`, out of scope)
- The session-log template gains optional sections; existing logs render without them
- Coordinator handoff_documents rows already accept the JSONB array fields used by `PhaseRecord`; schema unchanged

## Open Questions

None at design freeze. Discovery answered the four genuine ambiguities (coordination, atomic-failure semantics, crash recovery, metrics).
