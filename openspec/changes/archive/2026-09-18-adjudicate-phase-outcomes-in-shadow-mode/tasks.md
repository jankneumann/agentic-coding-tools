# Tasks: Adjudicate phase outcomes in shadow mode

> Change ID: `adjudicate-phase-outcomes-in-shadow-mode`

## Tasks

### Phase 1 — Signal gathering (D3)

- [x] 1.1 `_git_diff_stat(worktree_path) -> str | None` — runs `git diff
  --stat main...HEAD` (or the feature worktree's own merge base) inside
  `.git-worktrees/<change-id>/`; returns `None` on a missing worktree,
  subprocess error, or non-zero exit.
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.2 `_test_output_tail(change_dir, *, lines=40) -> str | None` — the
  last N lines of `validation-report.md` when present under `change_dir`;
  `None` otherwise.
  **Design decisions**: D3
  **Dependencies**: None
- [x] 1.3 `_read_local_handoff(change_dir, phase, handoff_id) -> dict | None`
  — reads the most recent `handoffs/<phase-slug>-*.json` local-fallback file
  matching `phase`'s slug; `None` when the directory or a matching file
  doesn't exist, or the JSON fails to parse.
  **Design decisions**: D4 (grounding)
  **Dependencies**: None
- [x] Checkpoint: unit tests for each signal gatherer covering the present
  and every absent/error case.

### Phase 2 — Adjudication call and shared envelope (D1, D2, D4)

- [x] 2.1 New `skills/autopilot/scripts/phase_outcome_shadow.py`:
  guarded `system_one_decisions` import (module-level, looked up at call
  time per the established stubbing rule).
  **Dependencies**: None
- [x] 2.2 `build_outcome_adjudication_entry(*, phase, claimed_outcome,
  expected_outcomes, handoff_record, diff_stat, test_output_tail) -> dict |
  None` — builds the state payload from whichever signals are non-`None`,
  asks the two questions (D2), and on a usable answer set returns the
  shared envelope (D4, reusing `gatekeeper_shadow._shadow_entry_dict` or an
  equivalent shared helper — see 2.3). Returns `None` on `decide()`
  unavailability or a malformed answer set.
  **Design decisions**: D1, D2, D3, D4
  **Dependencies**: 2.1
- [x] 2.3 Factor the shadow-envelope builder out of `gatekeeper_shadow.py`
  into a location both modules import (or have `phase_outcome_shadow.py`
  import `gatekeeper_shadow._shadow_entry_dict` directly) so the envelope
  shape is defined exactly once.
  **Design decisions**: D4
  **Dependencies**: 2.2
- [x] Checkpoint: unit tests for `build_outcome_adjudication_entry`
  covering agreement, disagreement, and every unavailability branch.

### Phase 3 — Wiring into `apply_phase_outcome` (D1)

- [x] 3.1 `apply_phase_outcome` gains the adjudication step on the
  non-replay path: gathers the three signals (Phase 1), calls
  `build_outcome_adjudication_entry`, and appends the result to its own
  `history` list before `_save_state` — the exact insertion point `ri-06`
  used for the GATEKEEPER shadow entry, generalized to every phase.
  **Design decisions**: D1
  **Dependencies**: 1.1, 1.2, 1.3, 2.2
- [x] 3.2 `runner.py`'s `_cmd_apply_outcome` already passes `change_dir`
  (from `ri-06`); confirm the worktree path
  (`repo_root / ".git-worktrees" / change_id`) is derived the same way and
  needs no new CLI flag.
  **Dependencies**: 3.1
- [x] Checkpoint: ran the full `skills/autopilot` test suite, confirmed
  every pre-existing `apply_phase_outcome` test
  (`test_apply_phase_outcome.py`, `test_apply_outcome_contract.py`) passes
  unmodified.

### Phase 4 — Replay safety, degradation, and reporting

- [x] 4.1 Replay test: two `apply_phase_outcome` calls with the same
  `handoff_id` produce exactly one shadow entry and one `decide()` call —
  the replay early-return path never reaches the adjudication step,
  mirroring `ri-06`'s own replay-safety test.
  **Spec scenarios**: skill-workflow.phase-outcome-shadow-record-per-transition
  **Dependencies**: 3.1
- [x] 4.2 Safety-isolation test: a disagreeing shadow judgment (judged
  outcome differs from claimed) leaves the claimed outcome, the recorded
  `phase_history` bare entry, and a subsequent `transition(state, outcome)`
  call byte-identical to today's.
  **Spec scenarios**: skill-workflow.phase-outcome-transition-unchanged
  **Dependencies**: 3.1
- [x] 4.3 Degradation tests: module unavailable, `decide()` returns `None`,
  and "every signal is `None`" (no handoff record, no diff stat, no test
  output) each record nothing — explicitly NOT via `record_degraded` (D6).
  **Spec scenarios**: skill-workflow.phase-outcome-shadow-unavailable-degrades-silently
  **Dependencies**: 3.1
- [x] 4.4 `skills/autopilot/scripts/phase_outcome_shadow_report.py` —
  disagreement-rate reporting, mirroring `gatekeeper_shadow_report.py`.
  **Design decisions**: D5
  **Dependencies**: 3.1
- [x] 4.5 `attribute_disagreements(entries, review_findings)` — the
  attribution mechanism (D5), unit-tested against a constructed fixture
  with at least one disagreement vindicating each side. Real-sprint
  wiring deferred (see design.md Non-goals).
  **Design decisions**: D5
  **Dependencies**: 4.4
- [x] Checkpoint: ran the full `skills/autopilot` + `skills/tests/autopilot`
  suite, `ruff check` clean, `test_host_assisted_invariant.py` and
  `test_no_sdk_import_outside_package.py` both pass, and
  `tests/openspec_paths/test_change_path_stability.py` passes (no literal
  `openspec/changes/<id>/` path pinned anywhere in the new tests — the
  exact self-inflicted bug `ri-06` caught in its own PR).

## Non-goals (out of scope for this item)

- Attributing real disagreements over a full sprint of production autopilot
  runs.
- Promoting the judged outcome to the acting one, or changing `transition()`.
- A coordinator-side lookup of a handoff record by `handoff_id`.
- Fabricating `worktree diff stat` / `test-output tail` when the underlying
  artifact is missing.
- Unifying `phase_agent._expected_outcomes_for_phase` with
  `autopilot.TRANSITIONS`.
