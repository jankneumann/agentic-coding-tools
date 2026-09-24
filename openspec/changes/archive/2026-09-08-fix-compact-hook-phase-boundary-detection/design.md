# Design — Fix Compact-Hook Phase-Boundary Detection

## Problem Statement

`skills/session-bootstrap/scripts/hooks/check_compact.py` is a Stop hook that asks Claude Code to issue `/compact` at two trigger points: a context-threshold trip, or a "natural decomposition point" defined as "any handoff JSON written under `openspec/changes/*/handoffs/` within the last 300 seconds."

The decomposition-point detector (`_recent_phase_boundary()`, lines 258–284) globs `openspec/changes/*/handoffs/*.json` across every worktree the repo knows about (`_all_worktree_roots()`), keeps the newest entry with `mtime >= now - 300s`, and returns its phase name.

This breaks in three concrete scenarios observed during real autopilot runs:

| Scenario | Trigger | Why hook should defer |
|---|---|---|
| Sub-agent in flight | Autopilot dispatched a background `Agent(...)` for IMPLEMENT; the sub-agent's worktree write touched a handoff file | Orchestrator's `apply-outcome` has not yet run — dispatch metadata (agent ID, archetype, outcome wiring) is still needed in context |
| Stale mtime touch | Git checkout, IDE indexer, or backup process updated mtime on an archived handoff | No phase transition actually occurred |
| Sibling-worktree handoff | Parallel run on a different change-id wrote a handoff that the cross-worktree glob picked up | Not this loop's phase boundary |

In the 2026-05-30 autopilot run for `extract-gen-eval-package`, the hook fired with `"plan-iteration-1 handoff just written"` even though `loop-state.json.last_handoff_id` was `plan_review-3.json` — clearly stale, but the hook had no way to know.

## D1. Selected Approach: Cross-Reference `last_handoff_id`

The autopilot `apply-outcome` step writes `loop-state.json` with the just-consumed handoff path in the `last_handoff_id` field. That is the authoritative "the orchestrator just completed a phase" signal — it updates atomically, exactly when a real phase boundary occurs.

The fix: gate the existing mtime check on whether the handoff filename matches that change's `last_handoff_id`.

```python
def _recent_phase_boundary() -> str | None:
    cutoff = time.time() - PHASE_BOUNDARY_WINDOW_SEC
    newest_phase: str | None = None
    newest_mtime = 0.0
    seen: set[Path] = set()
    for root in _all_worktree_roots():
        for p in root.glob("openspec/changes/*/handoffs/*.json"):
            try:
                resolved = p.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            # NEW: gate on last_handoff_id from the loop-state.json
            # alongside this handoff file. If the orchestrator has not
            # yet consumed this handoff (apply-outcome step), the
            # mtime is from sub-agent activity, an mtime touch, or a
            # sibling worktree's write — not a real boundary.
            change_dir = p.parent.parent  # openspec/changes/<id>/
            loop_state_path = change_dir / "loop-state.json"
            try:
                loop_state = json.loads(loop_state_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue  # fail closed: no loop state = no boundary
            last_handoff = loop_state.get("last_handoff_id", "")
            if not isinstance(last_handoff, str) or not last_handoff.endswith(p.name):
                continue  # handoff present on disk but not yet applied
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest_phase = p.stem.rsplit("-", 1)[0]
    return newest_phase
```

### Why `endswith(p.name)` not full path equality

`last_handoff_id` is stored as a repo-relative path (`openspec/changes/<id>/handoffs/<phase>-<N>.json`), while `p` may be either a worktree-relative path or a fully-resolved absolute path depending on which `root` from `_all_worktree_roots()` is iterating. Comparing the basename is sufficient because each `<id>/handoffs/` directory namespaces filenames per change.

### Why fail-closed on missing/malformed loop-state.json

Two reasons:

1. **Genuine non-autopilot flows** (e.g. a human writing a handoff by hand for a one-off change, or a legacy `linear-*` skill that doesn't maintain loop-state). For these, the threshold trigger (line 311) still catches genuine high-context turns. Better to defer false-positives than to compact mid-thought.
2. **Race protection**: if `loop-state.json` is mid-write (autopilot's `apply-outcome` is doing the update right now), JSON decode could fail transiently. Skipping for this Stop event is safe; the next Stop event will read a fully-written state.

## D2. Why Not a Marker File (Approach 1 from Proposal)

The proposal already explained the high-level rationale. Concretely:

- A marker file `.autopilot/<id>/in-flight.json` would require autopilot's dispatch path to add `Path(".autopilot").mkdir; write marker` and the apply-outcome path to add `marker.unlink(missing_ok=True)`. That's two new write sites that must stay synchronized with the existing `last_handoff_id` update — duplicating state.
- Crash recovery becomes a concern: if the orchestrator dies between dispatch and apply-outcome, the marker file is leaked. The hook would need a TTL/staleness check, growing in complexity.
- It couples session-bootstrap to autopilot. Other orchestrator skills (autopilot-roadmap, future ones) would each need to maintain their own marker.

Cross-referencing `last_handoff_id` reuses a field that already has crash-clean semantics: even after a crash, the field reflects the last successfully-consumed handoff, never claiming a phase completed when it didn't.

## D3. Test Plan

Add `skills/tests/session-bootstrap/test_check_compact_phase_boundary.py` with these cases (using `tmp_path` to materialize fake worktrees):

| Case | Setup | Expected `_recent_phase_boundary()` return |
|---|---|---|
| True positive | `loop-state.json.last_handoff_id` = `path/to/plan_review-3.json`; that file's mtime is fresh | `"plan_review"` |
| False positive — sub-agent in flight | `loop-state.json.last_handoff_id` = `plan_review-3.json` (older mtime); a fresh `implement-1.json` written by a sub-agent | `None` |
| False positive — stale mtime touch | `loop-state.json.last_handoff_id` = `plan_review-3.json` (matches); but a stale `plan-iteration-1-1.json` also has fresh mtime | `"plan_review"` (the matching one wins, not the stale one) |
| False positive — missing loop-state | Fresh handoff present; no `loop-state.json` | `None` |
| False positive — malformed loop-state | Fresh handoff present; `loop-state.json` contains `not json` | `None` |
| Outside window | `loop-state.json.last_handoff_id` matches; handoff mtime is older than 300s | `None` |

We DO NOT need to test the threshold trigger interaction — it is independent and unchanged. We DO NOT need a full Claude-Code-harness integration test; the hook is a stdin/stdout filter exercised by unit tests at the function level.

## D4. Backward Compatibility

| Surface | Before | After |
|---|---|---|
| `check_compact.py` API (stdin/stdout JSON contract) | unchanged | unchanged |
| Hook configuration (Claude Code Stop hook registration) | unchanged | unchanged |
| Threshold trigger semantics | unchanged | unchanged |
| Phase boundary trigger | fires on any fresh handoff mtime | fires only when handoff is applied to loop-state.json |
| Behavior for non-OpenSpec sessions (no `openspec/changes/`) | no boundary trigger; threshold only | unchanged |
| Behavior for OpenSpec sessions without loop-state.json | boundary trigger fires on any handoff mtime | boundary trigger never fires; threshold trigger still works |

The last row is a *deliberate* behavior change for sessions that author OpenSpec handoffs manually without autopilot. In practice these sessions are rare and short-lived (one-shot writes), and the threshold trigger remains the safety net for genuine context pressure.

## D5. Edge Cases

### E1. Handoff written, then `apply-outcome` writes loop-state in the same window

Both files end up with mtime in the 300s window. The handoff filename matches `last_handoff_id` → boundary detected → `/compact` requested. Correct.

### E2. `apply-outcome` writes loop-state but doesn't touch the handoff file

If apply-outcome refreshes loop-state.json (e.g. updating phase_archetype) without writing a new handoff, the handoff mtime falls below the 300s cutoff eventually → no boundary signal. Correct (compaction was already requested when the original handoff was written).

### E3. Background sub-agent writes handoff but autopilot orchestrator never applies (sub-agent failure)

Sub-agent writes `implement-1.json` then fails. Orchestrator never updates `last_handoff_id`. The handoff is on disk with fresh mtime; `last_handoff_id` still points at the previous phase's handoff. Hook does NOT request compaction → orchestrator handles the failure → on the next successful apply-outcome the right boundary fires. Correct.

### E4. Parallel sub-agents in sibling worktrees write handoffs

Each sibling worktree has its own `openspec/changes/<id>/loop-state.json`. The cross-worktree glob picks up handoffs from both, but each sub-loop's `last_handoff_id` only matches its own consumed handoff. False positives across sub-loops are eliminated.

### E5. `loop-state.json` exists but `last_handoff_id` is `null` or absent

This happens at the very start of a change (before the first apply-outcome). `last_handoff = loop_state.get("last_handoff_id", "")` returns `""`; `"".endswith(p.name)` is False → no boundary signal. The threshold trigger remains. Correct.
