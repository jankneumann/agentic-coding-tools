# Fix Compact-Hook Phase-Boundary Detection

## Why

The `check_compact.py` Stop hook fires premature `/compact` requests during in-flight autopilot phases. Its `_recent_phase_boundary()` detector treats *any* handoff JSON whose mtime falls inside the 300-second window as a phase-completion signal, regardless of whether the orchestrator has consumed that handoff. This produces three false-positive classes:

1. **Sub-agent in flight** — autopilot dispatches a background sub-agent (e.g. for IMPLEMENT); the sub-agent reads/writes handoffs under its own worktree, the orchestrator's Stop hook fires, sees a recent handoff mtime, and demands `/compact` — even though the orchestrator is mid-phase and needs the dispatch metadata to consume the eventual completion notification.
2. **Stale-mtime touches** — git checkout, IDE indexing, backup tools, or even `cat`-style reads from tooling can update mtimes on previously-archived handoffs, causing the hook to mistake an old `plan-iteration-1-1.json` for a freshly-written boundary.
3. **Sibling-worktree handoffs** — `_all_worktree_roots()` globs handoffs across every checkout known to git; a parallel run on a different change-id can trigger compaction in this run's session.

Empirical evidence: during the `extract-gen-eval-package` autopilot run on 2026-05-30, the hook fired immediately after IMPLEMENT dispatch with `"plan-iteration-1 handoff just written"` — even though `loop-state.json.last_handoff_id` was `plan_review-3.json` and IMPLEMENT had just started. Acceding to the request would have discarded the in-flight sub-agent handle.

The underlying data the hook needs is already on disk: `loop-state.json.last_handoff_id` is updated atomically by autopilot's `apply-outcome` step and is the authoritative signal for "the orchestrator has just completed a phase."

## What Changes

- Gate `_recent_phase_boundary()` on cross-referencing `loop-state.json.last_handoff_id`. A handoff with recent mtime SHALL only be treated as a phase boundary when its filename matches the `last_handoff_id` of the change it belongs to.
- Fall back safely when `loop-state.json` is missing or malformed (treat as "no boundary signal" — the threshold trigger remains active to catch genuine high-context turns).
- Add unit tests covering the three false-positive scenarios plus the true-positive case.
- Update `skill-workflow` capability spec with a requirement codifying the gate semantics.
- Resync runtime mirrors so `.claude/skills/` and `.agents/skills/` pick up the change.

## Out of Scope

- Adding marker files (e.g. `.autopilot/in-flight`) maintained by autopilot. The cross-reference approach uses existing state and avoids new bidirectional coupling.
- Changing the threshold-based trigger (70% of context limit) or the SDK/proxy token estimation strategy.
- Changing autopilot dispatch protocol or `apply-outcome` semantics. Autopilot writes `last_handoff_id` exactly when it currently does; the fix only changes how the hook reads it.
- Cloud-harness compaction policy. The hook already degrades cleanly in non-OpenSpec sessions.

## Approaches Considered

### Approach 1: Marker File Maintained by Autopilot (Rejected)

Have autopilot write `.autopilot/<change-id>/in-flight.json` on dispatch and delete it on `apply-outcome`. The hook checks for any marker and defers if present.

Pros:
- Conceptually crisp: marker explicitly represents "phase dispatch in flight."
- Decoupled from handoff-naming conventions.

Cons:
- Requires changes to autopilot's dispatch and apply-outcome paths.
- Needs cleanup-on-crash semantics (stale marker after orchestrator OOM).
- Duplicates state that `last_handoff_id` already encodes.
- Couples session-bootstrap to autopilot (each new orchestrator skill would need to maintain its own marker).

Effort: M

### Approach 2: Cross-Reference `last_handoff_id` (Recommended)

Gate the existing handoff-mtime check on whether the filename matches `loop-state.json.last_handoff_id`. Read loop-state.json defensively (treat missing/malformed as "no boundary").

Pros:
- Single source of truth: `apply-outcome` updates `last_handoff_id` atomically.
- No autopilot changes; the fix is contained in `check_compact.py`.
- Backward-compatible: changes without a `loop-state.json` (manual handoffs, legacy flows) gracefully skip the gate.
- Works uniformly for inline-prose dispatch, background-`Agent` dispatch, and provider-neutral dispatch.

Cons:
- The hook now reads `loop-state.json` schema fields, creating a minor cross-skill dependency.
- A handoff written by a different skill that doesn't update `last_handoff_id` would be ignored — but those flows don't currently trigger phase-boundary compaction either.

Effort: S

### Approach 3: Suppress Hook During Background-Agent Runs (Rejected)

Detect whether any background Agent is in flight (via Claude Code's session state) and skip the boundary check entirely until they complete.

Pros:
- No dependency on OpenSpec state.
- Conceptually simple.

Cons:
- Suppresses *all* boundary triggers including legitimate ones (e.g. a quick `/iterate-on-plan` that completed while a background agent was running).
- Requires reaching into Claude Code session state that the hook doesn't currently see.
- The threshold trigger should still fire mid-phase if context is genuinely full.

Effort: M

## Selected Approach

Approach 2. The fix is ~15 lines, surgical, and uses state autopilot already maintains. Unit tests cover the false-positive and true-positive cases. No autopilot changes are required; documentation updates are limited to the `skill-workflow` capability spec.

## Impact

- Affected specs: `skill-workflow` (one ADDED requirement)
- Affected skills: `session-bootstrap` (single file: `scripts/hooks/check_compact.py`)
- Affected tests: new test file under `skills/tests/session-bootstrap/`
- Affected docs: none (the behavior is internal; CLAUDE.md does not currently document hook semantics)
- Runtime mirrors: `.claude/skills/session-bootstrap/`, `.agents/skills/session-bootstrap/` (resynced via `install.sh`)
