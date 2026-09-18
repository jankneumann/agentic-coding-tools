# Judge decision-tag backfill in explore-feature

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-decision-tag-backfill-in-explore-feature`
> Effort: M
> Priority: 4

## Why

`backfill_decision_tags.classify_decision` (`skills/explore-feature/scripts/backfill_decision_tags.py`) routes each untagged archived Decision to one of seven capability tags using seven hand-maintained keyword lists, then derives a confidence score from keyword-hit margins. That confidence is not calibrated — it is a heuristic dressed as a probability, even though the report already buckets it at 0.5/0.8 as if it were.

## What Changes

- **ADDED**: `propose_tags_for_archive` gains a first-stage judged classification (`_classify_phase_decisions`). One batched `system_one_decisions.decide()` call per session-log phase asks `Choice(capability, the keyword map's tags plus "none")` over every untagged decision's title and rationale in that phase.
- A decision the judgment routes to `"none"` is treated exactly like today's no-keyword-match case: excluded from proposed edits.
- The existing 0.5/0.8 confidence-bucketing code is unchanged — it now buckets `ChoiceAnswer.confidence` instead of a keyword-margin heuristic, but the report format and bucketing arithmetic need no change.
- The keyword map (`classify_decision`) remains the fallback: whenever the judgment is unavailable for a whole phase, or malformed/missing for one decision within an otherwise-answered phase, that decision is classified by the existing heuristic, unchanged.
- The script still only proposes — no markdown file is ever mutated, and the JSON report is written only when the caller supplies an output path (unchanged from today).

## Impact

- Affected capability: `explore-feature` (new capability spec — no requirement previously documented this script's behavior at all; see Non-Goals).
- Affected code: `skills/explore-feature/scripts/backfill_decision_tags.py` (`propose_tags_for_archive`, new `_classify_phase_decisions`/`_answer_field`).
- No change to `classify_decision`, `_extract_untagged_decisions`, `_confidence_bucket`, `ClassificationProposal`/`ClassificationReport`, or the CLI's argument surface.

## Non-Goals

- Not writing a full capability-spec requirement for `explore-feature`'s entire surface — no such capability spec exists today (a pre-existing documentation gap this item does not attempt to backfill wholesale, mirroring `ri-16`'s identical precedent for `agent-coordinator`'s audit triage). The new requirement is scoped to the classification behavior this item adds.
- Not changing the seven capability tags themselves, or `DEFAULT_KEYWORD_MAP`'s keyword lists — the judgment is derived from whatever keyword map a caller passes, keeping the judged and keyword paths on the same category universe.
- Not installing `system-one-decisions[live]` — not installed anywhere in this repo yet (confirmed by every prior judged item), so this classification takes the unavailable-fallback branch in the standard skills venv today, same as every other judged item.
