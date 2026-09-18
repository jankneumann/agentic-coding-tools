# Screen fact-check grounds with a first-stage judged pass

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `screen-fact-check-grounds-with-a-first-stage-judged-pass`
> Effort: L
> Priority: 3

## Why

`fact_check.run` (`skills/parallel-infrastructure/scripts/fact_check.py`) sends every non-protected finding through a ~90-line economy-tier LLM prompt on every fact-check pass, even though most findings in a review batch are never contradicted by the diff. Ground B additionally needs a quoted diff line the code verifies literally via `_evidence_line_in_subject_diff` — a requirement a bare probability can't satisfy — so a cheap first-stage screen can narrow the batch without weakening that guarantee.

## What Changes

- **ADDED**: `fact_check.run` gains a first-stage judged screen. One batched `system_one_decisions.decide()` call asks a `Noul` per finding for Ground A ("the code this finding describes is not in the subject file's diff") and a `Noul` per finding as a Ground-B screen ("a line in this diff directly contradicts the finding's central claim").
- A confident Ground-A screen removes a finding directly (no evidence line required, matching Ground A's existing treatment). A confident Ground-B screen earns a finding a seat at stage two, where the existing evidence-line check still gates any removal, unchanged. A finding clearing neither ground is kept without ever reaching stage two — the common case, per the rationale below.
- Protected-subject findings never enter the screen (no verdict from either ground can override that veto) and always reach stage two exactly as before.
- When the screen is unavailable, every finding falls through to stage two exactly as `fact_check.run` behaved before this change — no regression to the existing, already-tested pass.
- Thresholds move to a config sidecar (`fact-check-judgment.json`), mirroring the threshold-loading precedent from every prior judged item in this roadmap.

## Impact

- Affected capability: `parallel-infrastructure` (ADDED requirement: no existing spec previously documented `fact_check.run`'s behavior — see Non-Goals).
- Affected code: `skills/parallel-infrastructure/scripts/fact_check.py` (`run`, plus new `_screen_findings`/`load_ground_screen_confidence_floor`), consumed unchanged by `skills/autopilot/scripts/convergence_loop.py`'s existing `fact_check_module.run(...)` call site.
- No change to `render_prompts`, `parse_verdict`, `_evidence_line_in_subject_diff`, `protected_subject`, or the vendor-CLI caller machinery (`build_default_caller`) — only which findings reach the existing stage-two prompt.

## Non-Goals

- Not writing a full capability-spec requirement for `fact_check.run`'s entire pre-existing behavior — no such requirement exists today (a pre-existing documentation gap this item does not attempt to backfill wholesale). The new requirement is scoped to the screen this item adds.
- Not changing stage two's prompt, parsing, or evidence-verification logic — the screen only narrows which findings reach it.
- Not gating stage one behind stage-two `caller` availability changes: the screen still only runs where `fact_check.run` would otherwise have called the vendor CLI (after the existing `enabled`/`findings`/`caller` guards), so `caller=None` continues to skip the whole pass exactly as today.
- Not installing `system-one-decisions[live]` — not installed anywhere in this repo yet (confirmed by every prior judged item), so this screen takes the unavailable-fallback branch in the standard skills venv today, same as every other judged item.
