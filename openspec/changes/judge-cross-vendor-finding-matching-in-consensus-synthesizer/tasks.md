# Tasks: Judge cross-vendor finding matching in consensus_synthesizer

> Change ID: `judge-cross-vendor-finding-matching-in-consensus-synthesizer`

## Tasks

### Phase 1 — `MATCH_THRESHOLD` into config (D5)

- [x] 1.1 Add `DEFAULT_MATCH_THRESHOLD = 0.6` to `review_rules.py` and a
  `"match_threshold": 0.6` key to `review-rules.json`'s default layer
  (all three copies: `scripts/`, its `install_assets/` mirror, and the
  deployed `openspec/schemas/` copy -- `install.sh`'s own drift check
  caught the third one).
  **Design decisions**: D5
  **Dependencies**: None
- [x] 1.2 Replace `consensus_synthesizer.py`'s `MATCH_THRESHOLD = 0.6` literal
  with a `_default_match_threshold()` helper mirroring
  `_coverage_quorum_threshold()`'s exact shape.
  **Dependencies**: 1.1
- [x] Checkpoint: ran `review_ledger.py`'s and `consensus_synthesizer.py`'s
  existing test suites (115 passed), confirmed the threshold value is
  unchanged (0.6) and every existing match/no-match assertion still
  passes.

### Phase 2 — Fast-path extraction and judged batching (D1-D4)

- [x] 2.1 Extract `_fast_path_score(a, b)` from `match_score`'s
  location+type/location/snippet bands; `match_score` calls it first, then
  Jaccard, with byte-identical behavior to today (regression test: every
  existing `match_score` test still passes unmodified -- confirmed, 96
  passed).
  **Design decisions**: D1
  **Dependencies**: None
- [x] 2.2 Wrote tests for `_judge_pairs(file_path, pairs)` using a
  call-counting spy over `system_one_decisions.decide` (the real module
  object, per the "import the module, not the name" stubbing rule): one
  call for N pairs on one file; `None` yields an empty result (Jaccard
  fallback); confidences map back to the correct pair index; the module
  itself being unavailable also yields an empty result.
  **Design decisions**: D2, D3
  **Dependencies**: None
- [x] 2.3 Implemented `_judge_pairs`.
  **Dependencies**: 2.2
- [x] 2.4 Rewired `ConsensusSynthesizer._match_all` around a merge model
  (every finding starts as its own live primary; matches merge the loser
  into the winner): fast path first (no call); every same-file, same-axis
  pair still live is judged in exactly one `decide()` call *per file*,
  spanning every primary and vendor on that file at once; Jaccard fallback
  for judged-ineligible or judged-unavailable pairs. `FindingMatch` gained
  `judged_vendors: set[str]` so evidence-class derivation cannot depend on
  vendor iteration order. Revised from a first cut that batched only per
  (primary, other_vendor) and used a single overwritable `basis` field,
  after Codex review on PR #590 caught both as real defects (see design.md's
  "Revised after Codex review" note).
  **Design decisions**: D1, D2, D3
  **Dependencies**: 2.1, 2.3
- [x] 2.5 `_consensus_evidence_class`: `match.basis == "judged"` returns
  `JUDGMENT` unconditionally, checked before the existing all-contributors
  check.
  **Design decisions**: D4
  **Dependencies**: 2.4
- [x] Checkpoint: ran the full `parallel-infrastructure` test suite (803
  passed, 2 skipped), confirmed green; confirmed every pre-existing
  `match_score`/`_match_all` test passes unmodified (D1's byte-identical
  refactor).

### Phase 3 — Fixture replay and regression tests

- [x] 3.1 Wrote `TestPr484FixtureReplay` reconstructing antigravity finding
  id 1 and pi finding id 14 from `fixtures/pr484-consensus.json` as raw
  `Finding` objects (axis, type, description per the fixture, plus the
  shared `build_atlas.py` file_path both descriptions name) and, with a
  stubbed confident judged answer, asserts they now match with
  `evidence_class == JUDGMENT` and one `decide()` call.
  **Spec scenarios**: parallel-infrastructure.Same-file-same-axis-pairs-are-judged-in-one-batched-call
  **Dependencies**: 2.4
- [x] 3.2 Wrote the call-count tests: `test_fast_path_pair_calls_decide_zero_times`
  and `test_same_file_axis_pairs_judged_in_one_call`.
  **Spec scenarios**: parallel-infrastructure.Fast-path-pairs-never-call-decide()
  **Dependencies**: 2.4
- [x] 3.3 Wrote `test_judged_match_never_raises_blocking_count`: two
  deterministic findings matched only via the judged path produce a
  consensus finding with `evidence_class="judgment"`, excluded from
  `blocking_count` (asserted `blocking_count == 0`, `advisory_count == 1`).
  **Spec scenarios**: parallel-infrastructure.A-judged-match-never-raises-blocking_count
  **Dependencies**: 2.5
- [x] Checkpoint: ran the full `parallel-infrastructure` suite (803 passed,
  2 skipped) and `ruff check` (clean). `mypy` is not part of this
  package's existing quality gate (not installed in `skills/.venv`; no
  other file in `skills/parallel-infrastructure/scripts/` is type-checked
  in CI either).

## Non-goals (out of scope for this item)

- `review_ledger.py`'s own `_match_existing` gains no judged path.
- No `event_sink` telemetry wiring.
- Seeded-defect-set precision regression measurement (deferred; see
  proposal.md and the roadmap's own refinement history for `ri-05`).
- Matching the fixture's singleton second defect (pi id 12); no antigravity
  counterpart exists.
