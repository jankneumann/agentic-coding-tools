# Follow-up: compact-hook gate semantics documentation

> Parent change: `fix-compact-hook-phase-boundary-detection` (archived 2026-09-08)
> Migrated by: `/cleanup-feature` archive sweep, 2026-09-08

## Why

The parent change stopped `check_compact.py` from firing premature `/compact`
requests mid-phase, by gating `_recent_phase_boundary()` on a cross-reference to
`loop-state.json.last_handoff_id`. That fix is merged and covered by a
`skill-workflow` requirement.

One task was labelled **out of scope for the change, to be done after merge to
main**: recording the gate semantics in `docs/lessons-learned.md` *if* they surface
as a recurring debugging touchstone. The condition is the point — the parent author
deliberately did not want a lessons-learned entry written speculatively for a fix
that might never confuse anyone again.

The archive sweep collects it here so the condition can actually be evaluated later,
rather than being lost as an unchecked box inside an archived change.

## What Changes

- Evaluate whether the compact-hook gate semantics have recurred as a debugging
  touchstone since the parent merged (2026-08, roughly 25 days of autopilot runs).
- If yes, add the entry to `docs/lessons-learned.md`: what the three false-positive
  classes looked like from the operator's seat, and that `last_handoff_id` is the
  authoritative "a phase actually completed" signal.
- If no, close this change with that finding recorded. A negative result is a real
  outcome here, not a failure to deliver.

## Impact

- Docs: `docs/lessons-learned.md` (conditionally)
- Specs: none. See `.openspec.yaml` — the gate requirement merged with the parent.

## Out of Scope

- Any change to `check_compact.py` behaviour, the 300-second window, or the
  threshold-based trigger. The parent settled all three.
