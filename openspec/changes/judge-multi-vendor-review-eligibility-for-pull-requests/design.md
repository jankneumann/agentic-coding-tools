# Design: Judge multi-vendor review eligibility for pull requests

## Context

`vendor_review.check_review_eligibility` gates whether a PR gets dispatched
to multi-vendor review. Today the gate is a size threshold
(`SMALL_PR_MAX_CHANGED_LINES` / `SMALL_PR_MAX_FILES`) evaluated after the
deterministic draft-PR and `SKIP_ORIGINS` checks. This item replaces the size
gate with a calibrated judgment, per
`docs/proposals/jev-system-one-integration-assessment.md` A4, keeping size as
the degraded fallback.

## Decisions

### D1: Judgment sits where the size check was, not before the deterministic skips

`is_draft` and `SKIP_ORIGINS` (origin provenance — dependabot, renovate,
Jules subtypes) run first and return before `_classify_pr_risk` is ever
called. These are facts, not judgments, per the parent proposal's own
framing ("Provenance-based skips are facts and stay deterministic"). A
call-count test (`fake_module.decide.assert_not_called()`) proves this.

### D2: The judgment does not bypass the existing-reviews check

`check_review_eligibility`'s existing `has_approval` / `changes_requested`
check is orthogonal to risk — it exists to avoid re-reviewing a PR a human
(or a prior vendor round) already acted on, regardless of how risky the
change is. The judged-eligible branch therefore still falls through into
that check before returning `eligible: True`, exactly as the original
size-eligible branch did. Verified by
`test_existing_approval_still_short_circuits_a_judged_eligible_pr`.

### D3: `Score`'s wire contract, since this is the first call site to use it

No prior judged item in this roadmap used the `Score` primitive (all used
`Choice` or `Noul`). Per
`docs/proposals/jev-system-one-integration-assessment.md` line 43:
`Score(instructions, criteria=[level0, level1, ...]) → ScoreAnswer(score:
float, confidence, probabilities: dict[int, float], legend)`. This item
reads `score` and `confidence` off the answer (via the established
`_answer_field` dict/getattr shim) and records them verbatim as
`risk_score` / `risk_probability` in the eligibility record — informational
only, never used to gate the eligibility decision itself, which is decided
by the `Noul`'s `warrants_review.noul` probability against a config-held
floor (mirroring `triage.py`'s `p >= floor` convention for a bare Noul,
which per the same doc has "no separate confidence").

### D4: State excludes the diff itself

Per the parent proposal, state is title, body (truncated to 2000 chars),
file list, and additions/deletions — never the diff body. This keeps the
eligibility check cheap (well under the 32K-token budget
`system_one_decisions.decide()` already enforces) and avoids paying for a
full-diff judgment on every PR just to decide whether a *further*, more
expensive multi-vendor review is warranted.

## Non-goals

- Changing the review prompt, dispatch, or consensus synthesis machinery
  (`build_review_prompt`, `dispatch_vendor_reviews`) — only the eligibility
  gate ahead of them.
- A live TypeSafe SDK installation — `system_one_decisions[live]` is not
  installed anywhere in this repo yet (confirmed during `ri-09`/`ri-10`), so
  this judged path takes the `None`-fallback branch in the standard skills
  venv today, same as every other judged item in this roadmap.
