# Tasks: Judge cross-vendor finding matching in consensus_synthesizer

> Change ID: `judge-cross-vendor-finding-matching-in-consensus-synthesizer`

## Tasks

### Phase 1 — `MATCH_THRESHOLD` into config (D5)

- [ ] 1.1 Add `DEFAULT_MATCH_THRESHOLD = 0.6` to `review_rules.py` and a
  `"match_threshold": 0.6` key to `review-rules.json`'s default layer.
  **Design decisions**: D5
  **Dependencies**: None
- [ ] 1.2 Replace `consensus_synthesizer.py`'s `MATCH_THRESHOLD = 0.6` literal
  with a `_default_match_threshold()` helper mirroring
  `_coverage_quorum_threshold()`'s exact shape.
  **Dependencies**: 1.1
- [ ] Checkpoint: run `review_ledger.py`'s and `consensus_synthesizer.py`'s
  existing test suites, confirm the threshold value is unchanged (0.6) and
  every existing match/no-match assertion still passes.

### Phase 2 — Fast-path extraction and judged batching (D1-D4)

- [ ] 2.1 Extract `_fast_path_score(a, b)` from `match_score`'s
  location+type/location/snippet bands; `match_score` calls it first, then
  Jaccard, with byte-identical behavior to today (regression test: every
  existing `match_score` test still passes unmodified).
  **Design decisions**: D1
  **Dependencies**: None
- [ ] 2.2 Write tests for `_judge_pairs(file_path, pairs, *, site)` using
  `system_one_decisions.testing.stub_decide`: one `decide()` call for N
  pairs on one file; a stub `None` return yields an empty result (Jaccard
  fallback); confidences map back to the correct pair index.
  **Design decisions**: D2, D3
  **Dependencies**: None
- [ ] 2.3 Implement `_judge_pairs`.
  **Dependencies**: 2.2
- [ ] 2.4 Rewire `ConsensusSynthesizer._match_all`: fast path first (no call);
  same-file+axis fast-path misses batched per file through `_judge_pairs`
  when available; Jaccard fallback for judged-ineligible or
  judged-unavailable pairs. Set `FindingMatch.basis = "judged"` for
  judged-path matches.
  **Design decisions**: D1, D2, D3
  **Dependencies**: 2.1, 2.3
- [ ] 2.5 `_consensus_evidence_class`: `match.basis == "judged"` returns
  `JUDGMENT` unconditionally, checked before the existing all-contributors
  check.
  **Design decisions**: D4
  **Dependencies**: 2.4
- [ ] Checkpoint: run the full `consensus_synthesizer.py` test suite plus
  `review_ledger.py`'s, confirm green; confirm every pre-existing
  `match_score`/`_match_all` test passes unmodified (D1's byte-identical
  refactor).

### Phase 3 — Fixture replay and regression tests

- [ ] 3.1 Write a test reconstructing antigravity finding id 1 and pi finding
  id 14 from `fixtures/pr484-consensus.json` as raw `Finding` objects (axis,
  type, description per the fixture, plus the shared `build_atlas.py`
  file_path both descriptions name — the fixture's own schema keeps neither
  finding's real file_path; see design.md's grounding note for why this
  reconstruction is honest rather than literal replay) and, with a stubbed
  confident judged answer, asserts they now match with `basis == "judged"`.
  **Spec scenarios**: parallel-infrastructure.Same-file-same-axis-pairs-are-judged-in-one-batched-call
  **Dependencies**: 2.4
- [ ] 3.2 Write the call-count test: a file with only fast-path-resolved
  pairs triggers zero `decide()` calls; a file with N judgeable pairs
  triggers exactly one.
  **Spec scenarios**: parallel-infrastructure.Fast-path-pairs-never-call-decide()
  **Dependencies**: 2.4
- [ ] 3.3 Write the blocking-count regression test: two deterministic
  findings matched only via the judged path produce a consensus finding
  with `evidence_class="judgment"`, excluded from `blocking_count`.
  **Spec scenarios**: parallel-infrastructure.A-judged-match-never-raises-blocking_count
  **Dependencies**: 2.5
- [ ] Checkpoint: run the full suite; confirm `ruff`/`mypy` clean.

## Non-goals (out of scope for this item)

- `review_ledger.py`'s own `_match_existing` gains no judged path.
- No `event_sink` telemetry wiring.
- Seeded-defect-set precision regression measurement (deferred; see
  proposal.md and the roadmap's own refinement history for `ri-05`).
- Matching the fixture's singleton second defect (pi id 12); no antigravity
  counterpart exists.
