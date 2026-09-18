# Judge cross-vendor finding matching in consensus_synthesizer

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `judge-cross-vendor-finding-matching-in-consensus-synthesizer`
> Effort: L
> Priority: 1

## Summary

Add a judged path to consensus_synthesizer.match_score: for candidate pairs sharing axis and file, ask one Noul("Findings A and B describe the same underlying defect") per pair, batched as N questions over one shared per-file state, keeping the line-overlap and snippet bands as fast paths and the Jaccard bands as the fallback. A match established only by the judged path records match_basis "judged", and _consensus_evidence_class returns "judgment" for any consensus finding whose match basis is judged regardless of its contributors' classes, so a probabilistic match can never raise the blocking count; its output feeds adjudication and disagreement routing. Move MATCH_THRESHOLD into config.

## Dependencies

- `ri-03`
- `ri-04`

## Acceptance Outcomes

- Replaying openspec/changes/add-orchestrator-adjudication-review-gate/fixtures/pr484-consensus.json pairs the two real defects across vendors and routes them to adjudication rather than leaving them unconfirmed.
- A consensus finding whose match basis is judged carries evidence_class "judgment" even when both contributing findings are deterministic, and blocking_count is unchanged by judged matches, asserted by a unit test on two deterministic scanner findings.
- Routing precision on the seeded-defect set from measure-validator-recall-seeded-defects does not drop relative to the recorded band-only baseline, with both numbers in the change artifacts.
- Pairs resolved by the line-overlap or identical-snippet fast paths issue no call, asserted by a call-count test.
- MATCH_THRESHOLD is read from config by both consensus_synthesizer.py and review_ledger.py; no threshold float literal remains in the scoring path.

## Rationale

Pilot step 2 and the highest-value Group A site. The hand-tuned Jaccard bands produced match_score 0.0 on all 23 findings of PR #484 including two real defects phrased differently by two vendors. A calibrated same-defect probability is also the signal rescope-review-convergence-disagreement-routing needs to tell genuine disagreement from re-phrasing. Because _consensus_evidence_class today makes a consensus finding deterministic when any contributor is deterministic, the judged path must be kept out of the blocking count explicitly or it would let a probability block a merge.
