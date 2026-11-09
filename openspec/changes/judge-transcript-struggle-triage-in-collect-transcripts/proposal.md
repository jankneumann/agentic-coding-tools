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

- flagged_for_deep_analysis is set from the corresponding Noul with a config-held threshold; the weighted sum and its 5/10 buckets remain as the fallback when the helper is unavailable, and are exercised by a test.
- A new compaction helper -- not an existing one, normalize.py has none today -- filters a session's NormalizedEvents down to only user/assistant/tool-result text content (excluding tool_use's tool_input payload dict), and that filtered state is what is sent for triage; a test asserts tool payloads are excluded and the state stays under the token budget.
- The four counters (_count_retries, _count_tool_errors, _count_scope_violations, _count_user_corrections) are still computed deterministically by the same pure functions and appear unchanged in the triage output schema.
- Existing collect-transcripts triage tests in skills/collect-transcripts/tests/test_triage.py pass unchanged with the helper stubbed to None (module unavailable), since none of them depend on system_one_decisions and TYPESAFE_API_KEY is unset in CI.

## Rationale

Pilot step 4. The weighted sum, the six-substring scope test and the "any user message after a tool error is a correction" rule are judgments dressed as arithmetic, and the sibling prompts/triage_v1.md shows the intent was always a judged call. deep_analyze stays an LLM because capability_gap is prose.

**Grounding correction (2026-09-18):** the scaffolded text above claimed the compacted transcript comes "from normalize.py's compact event form" as if that already existed. It does not -- `normalize.py` defines `NormalizedEvent`/`ContentBlock`/`EventRole`/`ContentType` with no compaction helper anywhere in the module. Building that helper is this item's own work. Everything else checked out against the real `triage.py`: the four counters are untouched pure functions, `_classify_struggle`'s weighted-sum + 5/10 bucket rule is exactly the fallback shape needed, and `test_triage.py` calls `triage_session()` directly with no `system_one_decisions` dependency, so it naturally exercises the fallback path.
