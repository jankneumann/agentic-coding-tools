# Design: Screen fact-check grounds with a first-stage judged pass

## Context

`fact_check.run` sends every non-protected finding through a fixed economy-tier LLM prompt on every pass. This item inserts a cheap first-stage judged screen ahead of it, per `docs/proposals/jev-system-one-integration-assessment.md` A-item on fact-check, narrowing the batch stage two actually has to process.

## Decisions

### D1: The screen sits inside `run()`, between the existing guards and the existing prompt/caller step

`enabled`, `findings` (empty), and `caller is None` all keep their exact current early-return behavior and ordering (verified against the existing `test_no_caller_available_skips`, `test_disabled_keeps_everything_without_calling`, `test_no_findings_short_circuits`, all passing unchanged). The screen only ever narrows the batch that would otherwise have gone, unmodified, into `render_prompts`/`caller`. This keeps the two-stage pattern an optimization of an already-happening pass rather than a new standalone entry point — simplest change that satisfies the acceptance outcomes, and it costs nothing: a call site (`convergence_loop.py`) that never reaches `caller is not None` never pays for a screen it wouldn't otherwise have benefited from either.

### D2: Protected-subject findings never enter the screen, but keep going to stage two unchanged

The scaffolded acceptance outcome read "protected-subject vetoes are applied in code before any call... a protected subject is never sent." Read literally as "never sent to the stage-two prompt either," this breaks the existing `test_protected_subject_survives_a_wrong_verdict` test, which deliberately sends a single protected finding to `caller` and asserts `status == "ran"` with a post-hoc veto — with a pre-filter, that single-protected-finding batch would go to `caller=None`... no, to an empty stage-two batch, changing `status` and breaking the test. Verified by running the test suite after implementing the literal reading: it failed exactly as predicted. Corrected interpretation, confirmed by re-running the full suite (34 pre-existing tests unchanged, 19 new tests passing): "any call" means the *new* screen's calibrated-decision call, since no ground's verdict can override the veto regardless — there is no point spending a screen call on a foregone conclusion. Protected findings continue straight to stage two exactly as before this item, where the existing post-verdict veto protects them unchanged.

### D3: A stage-two failure discards stage-one's tentative work too

`fact_check.py`'s own module docstring guarantee is "any failure to call the model, parse its response, or match a finding id removes nothing." Stage one is now also a model call. A stage-two `caller` failure or unparsable response therefore resets the *whole* batch to "everything kept" — including a finding the screen had already confidently resolved via Ground A in the same pass — rather than letting a partial, unverified result survive a failure elsewhere in the same invocation. Covered by `test_stage_two_failure_discards_stage_one_removal_too`.

### D4: The "agreement rate" acceptance outcome is a wiring test, not a live-calibration claim

No `[live]` extra is installed anywhere in this repo (confirmed by every prior judged item in this roadmap: `ri-09`, `ri-10`, `ri-11`), so a genuine live-model agreement figure against the recorded fixture batch cannot be produced in CI. What CI *can* prove — and what `TestGroundAAgreementAgainstRecordedBatch` does prove — is that the screen's wiring, given a stage-one answer set that agrees with the fixture's own recorded Ground-A verdicts (`skills/tests/parallel-infrastructure/fixtures/review-fixtures/fact-check-transcript.json`), reproduces exactly those verdicts through `run()`'s full pipeline, and prints the resulting rate for visibility. A genuine live-model figure is deferred to a future validation-phase run, exactly as `test_fact_check_fixture.py`'s own header comment already documents for stage two's existing accuracy figures ("The live-model figure is a separate validation-phase step recorded in validation-report.md").

## Non-goals

- Changing stage two's prompt, `parse_verdict`, or `_evidence_line_in_subject_diff` — only which findings reach them.
- A live TypeSafe SDK installation (see D4 and the parent proposal's Non-Goals).
