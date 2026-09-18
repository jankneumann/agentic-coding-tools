# Judge transcript struggle triage in collect-transcripts

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-transcript-struggle-triage-in-collect-transcripts`
> Effort: M
> Priority: 3

## Summary

Keep the four event-stream counters in triage.py as facts but replace the weighted sum and its 5/10 buckets with Choice(struggle_level, {none, low, medium, high}) plus Nouls for human redirection, out-of-scope work and whether the session warrants deep analysis, over a compacted transcript from normalize.py plus the counters.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- flagged_for_deep_analysis is set from the corresponding Noul with a config-held threshold; the weighted sum and its 5/10 buckets remain as the fallback and are exercised by a test.
- State sent for triage contains only assistant/user/tool-result text from normalize.py's compact event form, with a test asserting tool payloads are excluded and the state stays under the token budget.
- The four counters are still computed deterministically and appear unchanged in the triage output schema.
- Existing collect-transcripts triage tests pass with the helper stubbed to None.

## Rationale

Pilot step 4. The weighted sum, the six-substring scope test and the "any user message after a tool error is a correction" rule are judgments dressed as arithmetic, and the sibling prompts/triage_v1.md shows the intent was always a judged call. deep_analyze stays an LLM because capability_gap is prose.
