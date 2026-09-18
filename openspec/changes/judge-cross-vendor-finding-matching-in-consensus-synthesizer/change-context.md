# Change Context: judge-cross-vendor-finding-matching-in-consensus-synthesizer

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| parallel-infrastructure.1 | specs/parallel-infrastructure/spec.md | Fast-path pairs never call decide() | --- | D1 | skills/parallel-infrastructure/scripts/consensus_synthesizer.py | tests/test_consensus_synthesizer_judged_matching.py::TestJudgedMatchAll::test_fast_path_pair_calls_decide_zero_times | pass |
| parallel-infrastructure.2 | specs/parallel-infrastructure/spec.md | Same-file, same-axis pairs judged in one batched call | --- | D1, D2 | skills/parallel-infrastructure/scripts/consensus_synthesizer.py | tests/test_consensus_synthesizer_judged_matching.py::TestJudgedMatchAll::test_same_file_axis_pairs_judged_in_one_call, ::TestJudgePairs::test_one_call_for_n_pairs | pass |
| parallel-infrastructure.3 | specs/parallel-infrastructure/spec.md | A judged match never raises blocking_count | --- | D4 | skills/parallel-infrastructure/scripts/consensus_synthesizer.py | tests/test_consensus_synthesizer_judged_matching.py::TestJudgedMatchAll::test_judged_match_never_raises_blocking_count | pass |
| parallel-infrastructure.4 | specs/parallel-infrastructure/spec.md | Decision helper unavailable falls back to Jaccard | --- | D3 | skills/parallel-infrastructure/scripts/consensus_synthesizer.py | tests/test_consensus_synthesizer_judged_matching.py::TestJudgedMatchAll::test_unavailable_decide_falls_back_to_jaccard, ::TestJudgePairs::test_unavailable_decide_returns_empty, ::test_missing_module_returns_empty | pass |
| parallel-infrastructure.5 | specs/parallel-infrastructure/spec.md | MATCH_THRESHOLD has no literal in the scoring path | --- | D5 | skills/parallel-infrastructure/scripts/{consensus_synthesizer.py,review_rules.py,review-rules.json}, openspec/schemas/review-rules.json, skills/parallel-infrastructure/install_assets/openspec/schemas/review-rules.json | existing test_review_rules.py, test_consensus_synthesizer.py suites | pass |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 — Judged path beside `match_score`, not inside it | Batching needs visibility across a whole file's candidate pairs, which a pairwise `match_score(a, b)` signature cannot provide; `review_ledger.py`'s own dedup matching must stay unaffected | `_fast_path_score` extracted (byte-identical `match_score` behavior), `_judge_pairs` added as a sibling function called only from `_match_all` | Keeps every existing caller of `match_score` — chiefly `review_ledger.py` — completely unchanged |
| D2 — Judged eligibility and batching shape | "Batched as N questions over one shared per-file state" per the item's own description | One `decide()` call per file, spanning every still-live primary and vendor pair on that file at once, via a merge-based rewrite of `_match_all` (revised after Codex review, PR #590 P1/P2) | Matches the acceptance outcome literally; the merge model also fixed a real order-dependence bug in evidence-class derivation that the first cut's overwritable `basis` field had |
| D3 — Jaccard as the literal fallback | The item's own description: "keeping ... the Jaccard bands as the fallback" | Jaccard only runs when judgment was unavailable, ineligible (no shared file), or returned no usable answer for that candidate | Preserves total matching coverage — nothing that could match before is left unmatched now |
| D4 — `evidence_class` override | A probabilistic match must never promote a consensus finding into the blocking count | `_consensus_evidence_class` checks `match.basis == "judged"` first, unconditionally, before the existing all-contributors check | The one new branch this item's whole safety property rests on |
| D5 — `MATCH_THRESHOLD` from config | Mirrors `_coverage_quorum_threshold()`'s existing exact pattern | `DEFAULT_MATCH_THRESHOLD` in `review_rules.py`, `_default_match_threshold()` in `consensus_synthesizer.py` | Consistency with the one precedent this codebase already established for exactly this problem |

## Coverage Summary

- **Requirements traced**: 5/5.
- **Tests mapped**: all 5 requirements have at least one test; 11 new tests added in `test_consensus_synthesizer_judged_matching.py` (9 initial + 2 added for the Codex-review regressions: multi-primary single-call batching, order-independent evidence class).
- **Evidence collected**: 5/5 requirements have pass evidence. Full `skills/parallel-infrastructure` + `skills/tests/parallel-infrastructure` suite green: 805 passed, 2 skipped. `ruff check` clean.
- **Gaps identified**: none remaining after the Codex-review revision (`_match_all` now batches per file globally and evidence-class derivation is order-independent; see design.md's "Revised after Codex review" note).
- **Deferred items**: seeded-defect-set precision regression measurement (see proposal.md Non-Goals and the roadmap's own refinement history for `ri-05`). `review_ledger.py`'s own matching gains no judged path (Non-Goal). Matching the fixture's singleton second defect (no antigravity counterpart exists).
