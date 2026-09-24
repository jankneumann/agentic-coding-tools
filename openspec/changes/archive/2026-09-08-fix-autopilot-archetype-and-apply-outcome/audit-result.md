# Audit Result — fix-autopilot-archetype-and-apply-outcome

Authoritative record of the Task 1 audit findings across all four V2 causal
layers plus the V1 archetype mapping. Referenced by proposal.md (§V2) and
design.md (D1, D6, D10).

Audit performed: 2026-07-08. Codebase state: `openspec/fix-autopilot-archetype-and-apply-outcome` branch.

## V1 — VALIDATE archetype mapping (Task 1.1 / 1.2)

- **Finding**: `phase_mapping.VALIDATE` resolved to `analyst`
  (`agent-coordinator/archetypes.yaml`). The `analyst` system_prompt declares
  the role read-only ("Report structured findings without making changes"),
  which contradicts the VALIDATE task (writes evidence artifacts + PhaseRecord).
  `phase_mapping.VAL_FIX` already resolved to `implementer` (write-capable) —
  no change needed there.
- **Decision**: V1 fix required. Introduce `validator` (write_capable: true),
  remap `VALIDATE → validator`. Add a structured `write_capable` field to every
  archetype and enforce it at resolution time (no substring matching).
- **Acted on by**: Task 2.1–2.5, 2.7.

## Layer A — does `apply-outcome` write `current_phase`? (Task 1.3 / 1.4)

- **Finding**: `skills/autopilot/scripts/phase_agent.py :: apply_phase_outcome`
  (the implementation behind `runner.py apply-outcome`) does **NOT** write
  `current_phase`. It writes only `handoff_ids`, `last_handoff_id`, and
  `phase_archetype`. Evidence: the only `state[...] = ` assignments were to
  `handoff_ids`, `last_handoff_id`, `phase_archetype` (pre-change lines
  ~1120–1127). No `current_phase` mutation anywhere in the function.
  - `phase_history` was **NOT** appended by `apply-outcome` (the field existed
    in production loop-state.json files but was written elsewhere / by prose).
  - The `--phase` argument was **NOT** validated against loop-state
    `current_phase`.
- **Decision**: Layer A `current_phase`-write removal was a **no-op** (already
  clean). Still added, per plan: (a) a phase-mismatch guard, (b) the
  `--allow-phase-mismatch` escape hatch, (c) codified `phase_history` append.
- **Acted on by**: Task 3.1 (no-op, documented here), 3.2–3.6.

## Layer B / C — dispatch prompt prohibitions today (Task 1.6)

- **Finding**: The rendered dispatch prompt (`phase_agent._build_prompt`) told
  the sub-agent to "Return exactly (outcome, handoff_id)" but did **NOT**
  forbid running `runner.py apply-outcome` (Layer B) nor forbid editing
  `loop-state.json` directly (Layer C). Both escape hatches were open.
- **Decision**: Layer B + C fix required. Append both prohibitions to every
  write-capable phase's prompt (the 11 phases in `_WORKTREE_PHASES`).
- **Acted on by**: Task 4.1–4.3.

## Layer D — orchestrator next-phase transition table (Task 1.5)

- **Finding**: The orchestrator uses a **single centralized** transition table:
  `skills/autopilot/scripts/autopilot.py :: TRANSITIONS` (a `dict`), consulted
  by `transition(state, outcome)`. For `(IMPLEMENT, complete)` it already maps
  to **`IMPL_ITERATE`** — the correct target. `CLEANUP` does not appear anywhere
  in `autopilot.py` (nor elsewhere in the autopilot skill). The observed
  `IMPLEMENT=complete → CLEANUP` bug therefore did **NOT** originate in the
  orchestrator's table.
- **Decision**: Layer D table correction was a **no-op** (table already correct
  and centralized — the D10.1 "distributed logic" branch does not apply). The
  bug most plausibly originated from Layer B/C (a sub-agent taking initiative to
  hand-write state / commit) — closed by the prompt prohibitions. Added a
  regression test pinning `(IMPLEMENT, complete) → IMPL_ITERATE` and asserting
  CLEANUP is not a state. No follow-up structural-extraction change is needed.
- **Acted on by**: Task 5.1 (branch (a): centralized, only verify), 5.3, 5.4
  (verified against SKILL.md sections 4–8), 5.5 (added
  `apply_outcome_or_escalate` for the ESCALATE-on-failure transition), 6.6.

## Other consumers of `archetypes.yaml` (Task D3.2)

- **Finding**: The live schema/loader is `agent-coordinator/src/agents_config.py`
  (`ARCHETYPES_SCHEMA` + `load_archetypes_config`). A stale duplicate JSON schema
  exists at `openspec/schemas/archetypes.schema.json` (schema_version const 1,
  model enum opus/sonnet/haiku) that is not wired into runtime validation. No
  external (out-of-repo) consumers are known.
- **Decision**: Add `write_capable` (required) to the live schema and to the
  stale JSON schema for consistency. Test fixtures in
  `tests/test_archetypes_config.py` and `tests/test_phase_archetype_resolution.py`
  updated to include the now-required field.
