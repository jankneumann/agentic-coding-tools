# Fix Compact-Hook Session Scope

## Why

The compact hooks (`check_compact.py` on Stop, `precompact_handoff.py` on PreCompact) have two defects that surfaced together on 2026-09-13, when the Stop hook blocked a session with `agent=unknown` over a phase handoff that session did not write.

1. **Phase-boundary detection is repository-scoped, not session-scoped.** `_recent_phase_boundary()` globs handoffs across every worktree `git worktree list` knows about. The 2026-09-08 change (`fix-compact-hook-phase-boundary-detection`) gated candidates on `loop-state.json.last_handoff_id`, which rejects *unapplied* sibling handoffs, but another session's *applied* handoff passes that gate. So any concurrent autopilot run that completes a phase blocks every other session in the repository for five minutes. `precompact_handoff.py:_latest_phase_record()` has the same scan and folds whichever session's handoff is newest into this session's pre-compact snapshot.
2. **The compact-pending flag is keyed on an identity that is almost always absent.** Both hooks key `~/.claude/compact-pending-<id>.flag` on `AGENT_ID`, which local Claude Code sessions do not set. Every session therefore shares `compact-pending-unknown.flag`. One session's un-cleared flag silently disables the threshold and boundary triggers for every other session, and one session's `/compact` re-arms them for all of them.

## What Changes

- New stdlib module `skills/session-bootstrap/scripts/hooks/session_scope.py`, imported by both hooks:
  - `session_key(payload)` gives the flag identity. Precedence: hook-payload `session_id` → `SESSION_ID` → `AGENT_ID` → transcript-path hash → `unknown`. It is sanitized to be filesystem-safe. Claude Code sends `session_id` to both Stop and PreCompact and keeps it across `/compact`, so the two hooks derive the same key.
  - `load_session_scope(payload)` collects the session's working directories from the `cwd` field on transcript rows (plus the payload `cwd`), and keeps the transcript text.
  - `SessionScope.owns_handoff(path, roots)` accepts a handoff only when its owning worktree (the most specific root, since linked worktrees nest under the main checkout) is one the session worked in AND its change id appears in the transcript.
- `_recent_phase_boundary(payload)` applies the ownership check after the mtime and applied-handoff gates, so the transcript is read only when an applied candidate exists.
- `_latest_phase_record(payload)` considers only owned handoffs.
- The block reason and snapshot summary report `session=<key>` instead of `agent=<AGENT_ID>`.
- The duplicated `_all_worktree_roots` copies are removed from both hooks.

## Approaches Considered

### Approach 1: Scope the scan to the hook process cwd only (Rejected)

It is simple and needs no transcript read. But hooks run with the project directory as cwd, while autopilot applies outcomes inside a feature worktree. The feature worktree's boundary would never fire, which is the path the 2026-05 worktree-aware scan was added to support.

### Approach 2: Require the handoff payload's `session_id` to match (Rejected)

It would be exact, but PhaseRecords are written with `session_id: null` today (every handoff on disk has it null), so this would disable the boundary trigger outright until every writer is changed.

### Approach 3: Transcript-derived worktrees + change-id mention (Selected)

It uses data Claude Code already records. Worktree ownership stops cross-worktree leaks. The change-id mention stops leaks within a shared checkout, such as a pull bringing in another run's `loop-state.json`. Measured cost: 0.06s to scan a 12 MB transcript, paid only when an applied candidate exists.

## Out of Scope

- Changing PhaseRecord writers to populate `session_id`.
- Garbage-collecting old per-session flag files.
- Threshold values and token estimation.
