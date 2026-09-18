# Judge cross-vendor finding matching in consensus_synthesizer

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Roadmap item: `ri-05`
> Change ID: `judge-cross-vendor-finding-matching-in-consensus-synthesizer`
> Effort: M
> Priority: 1

## Summary

Add a judged path to `consensus_synthesizer`'s cross-vendor matching: for
candidate pairs sharing axis and file that the existing fast paths
(line-overlap, identical-snippet) don't resolve, ask one calibrated `Noul`
question per pair, batched as N questions over one shared per-file
`decide()` call, before falling back to the existing Jaccard
token-similarity bands. A match established only by the judged path records
`match_basis="judged"`, and a consensus finding whose match basis is judged
carries `evidence_class="judgment"` regardless of its contributors' own
classes — a probabilistic match can never raise the blocking count.
`MATCH_THRESHOLD` moves into `review-rules.json`, read by both
`consensus_synthesizer.py` and `review_ledger.py`.

## Dependencies

- `ri-01`

## Non-Goals

- Changing `review_ledger.py`'s own `_match_existing` dedup matching to use
  the judged path. That call site keeps calling the existing, unmodified
  `match_score()` — only `consensus_synthesizer`'s cross-vendor `_match_all`
  gains judgment. `review_ledger.py` only picks up the config-sourced
  `MATCH_THRESHOLD` (see Acceptance Outcomes).
- Measuring routing-precision regression against a 40-defect seeded set.
  `measure-validator-recall-seeded-defects` (a different, blocked roadmap's
  unimplemented scaffold) has no manifest, harness, or recorded baseline —
  deferred, same precedent as `ri-04`'s deferred kappa measurement.
- Matching the fixture's second named real defect ("nodes that export
  returns", pi finding id 12). Reading all 23 entries of
  `add-orchestrator-adjudication-review-gate/fixtures/pr484-consensus.json`
  found no antigravity counterpart for it anywhere — a genuine single-vendor
  finding, which is what that other change's adjudication path (a different
  roadmap item) exists to handle, not cross-vendor matching.

## Acceptance Outcomes

- Reconstructing the two real per-vendor findings for the footer/percent-format
  defect from `fixtures/pr484-consensus.json` (antigravity id 1, pi id 14) and
  replaying them through the judged path scores them as a match (today 0.0),
  moving that pair from unconfirmed to confirmed or disagreement.
- A consensus finding whose match basis is judged carries `evidence_class`
  `"judgment"` even when both contributing findings are deterministic, and
  `blocking_count` is unchanged by judged matches, asserted by a unit test on
  two deterministic scanner findings.
- Routing-precision regression measurement against the seeded-defect set is
  deferred (see Non-Goals); tracked as a follow-up.
- Pairs resolved by the line-overlap or identical-snippet fast paths issue no
  `decide()` call, asserted by a call-count test.
- `MATCH_THRESHOLD` is read from `review-rules.json` (alongside the existing
  `coverage_quorum_threshold`) by both `consensus_synthesizer.py` and
  `review_ledger.py`; no threshold float literal remains in the scoring path.

## Rationale

Pilot step 2: cross-vendor finding matching is exactly the kind of
paraphrase-tolerant judgment a calibrated Noul is suited for, where
token-overlap heuristics systematically fail — PR #484's 23 findings scored
`match_score: 0.0` across the board despite at least one genuine cross-vendor
duplicate among them.
