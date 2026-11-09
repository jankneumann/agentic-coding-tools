# Tasks: Judge transcript struggle triage in collect-transcripts

> Change ID: `judge-transcript-struggle-triage-in-collect-transcripts`

## Status

- [x] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

- [ ] Add `_compact_transcript()` to `triage.py`: filter `NormalizedEvent`s to
      user/assistant/tool text content (excluding `tool_use` payloads),
      truncate to a char budget from the end.
- [ ] Add `_classify_session()` to `triage.py`: guarded `system_one_decisions`
      import, one `decide()` call per session carrying `struggle_level`
      (Choice), `deep_analysis`/`user_redirected`/`out_of_scope` (Noul),
      degrades to `{}` on any unavailability.
- [ ] Extend `TriageScore` with `redirected_by_user: bool | None` and
      `out_of_scope_work: bool | None`, defaulting to `None`.
- [ ] Wire `_classify_session()` into `triage_session()`: judged
      `struggle_level`/`composite_score`/`flagged_for_deep_analysis` when
      available, falling back to `_classify_struggle`'s existing rule and
      `composite_score >= threshold` exactly when not.
- [ ] Unit tests: compaction excludes tool payloads and respects the char
      budget; classify degrades to `{}` on each unavailability branch; full
      `triage_session()` integration test with a stubbed judged answer.
- [ ] Confirm `skills/collect-transcripts/tests/test_triage.py` passes
      unchanged (no stubbing needed -- `TYPESAFE_API_KEY` unset in CI).
- [ ] Update the `harness-engineering` capability spec's "Session Transcript
      Mining" requirement (MODIFIED, not ADDED) to describe the judged
      classification and its deterministic fallback, closing the drift
      between that spec's existing "resolve its model via the archetype
      system" language and the pre-this-change pure-arithmetic reality.
- [ ] Roadmap completion bookkeeping (learning entry, checkpoint advance) in
      the same PR.
- [ ] Review and merge.
