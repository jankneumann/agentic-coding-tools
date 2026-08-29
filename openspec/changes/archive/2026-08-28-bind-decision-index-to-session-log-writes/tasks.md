# Tasks — bind-decision-index-to-session-log-writes

One phase. Test tasks precede the implementation they verify (TDD RED → GREEN).

Capability short name: `sw` = `skill-workflow`.

---

## Phase 1 — wp-persistence: the fourth step

- [x] 1.1 Test: `write_both()` leaves the decision index matching a fresh regeneration, and a
      second regeneration produces no further change — **S**
      **Spec scenarios**: sw *Regeneration leaves the decision index current*
      **Design decisions**: D1
      **Dependencies**: None

- [x] 1.2 Test: a regeneration that raises or exits non-zero leaves the appended markdown on
      disk, still reports `markdown_path` and the handoff outcome, adds a warning, and does
      not raise — **S**
      **Spec scenarios**: sw *Regeneration failure does not lose the session log*
      **Design decisions**: D3
      **Dependencies**: None

- [x] 1.3 Test: a checkout where the generator cannot be resolved completes the first three
      steps and warns by name — **S**
      **Spec scenarios**: sw *Regeneration is skipped when the generator is absent*
      **Design decisions**: D3
      **Dependencies**: None

- [x] Checkpoint: run the session-log suite, confirm the three new tests fail for the right
      reason, and confirm the four pre-existing pipeline scenarios still pass untouched

- [x] 1.4 Implement step four in `write_both()` — resolve the generator lazily, run it after
      the coordinator step, catch broadly, warn to stderr, append to `warnings` — **S**
      **Spec scenarios**: all three *Regeneration* scenarios
      **Design decisions**: D1, D2, D3
      **Dependencies**: 1.1, 1.2, 1.3

- [x] 1.5 Update the `write_both()` docstring from "3-step" to "4-step" and name the fourth
      step, so the docstring that already describes this coupling stops describing a pipeline
      that does not perform it — **XS**
      **Design decisions**: D1
      **Dependencies**: 1.4

- [x] Checkpoint: session-log suite green, review the diff, confirm only `phase_record.py`
      and its tests changed

- [x] 1.6 Test: no work-package worker path invokes `write_both()`; every call site belongs to
      an orchestrator phase-boundary step — **S**
      **Spec scenarios**: sw *No worker call site invokes the persistence pipeline*
      **Design decisions**: D4
      **Dependencies**: None
      Assert structurally over the skill payload rather than by grepping prose, so a future
      worker prompt that adds a call is caught.
      **Found an eighth call site the plan missed:** `autopilot/scripts/phase_agent.py:631`
      (`_write_phase_failed_record`), an orchestrator escalation boundary, allowlisted with
      its reason. The AST walk over heredoc-lifted Python found it; a prose grep would not.

- [x] 1.7 Test: a hand-edited session log still reports `decisions.timeline` drift and still
      contributes to the blocking exit code — **S**
      **Spec scenarios**: sw *A hand-edited session log still reports drift*
      **Design decisions**: D5
      **Dependencies**: None
      This is the guard against the change quietly becoming a way to stop checking.

- [x] 1.8 Verify the acceptance criterion end to end: a branch whose only change is a
      session-log write through `write_both()` runs `make context-drift-gate` and does not see
      `decisions.timeline` in `blocking_drift` — **S**
      **Design decisions**: D1, D5
      **Dependencies**: 1.4, 1.7
      Record the measured wall-clock of the added step against the ≤ 250 ms NFR target.
      **Measured 46.5 ms** (best of 3) over 60 session logs / 168 changes / 25 index files;
      full `write_both()` 66.3 ms end to end. Counterfactual in a throwaway clone: the same
      commit with `docs/decisions/` reverted exits 2 with `decisions.timeline` attributed
      `introduced` — the defect, reproduced against the fix.

- [x] Checkpoint: full session-log and project-context-refresh suites, `openspec validate
      --strict`, review the cumulative diff
