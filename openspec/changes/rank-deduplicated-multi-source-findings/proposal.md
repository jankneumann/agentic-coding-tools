# Rank deduplicated multi-source findings in analyze_failures

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `rank-deduplicated-multi-source-findings`
> Effort: S
> Priority: 2

## Summary

Make analyze_failures.py rank the deduplicated multi-source findings it already computes instead of raw memory entries, call generate_report_multi_source from main(), and make cross-source agreement a filter or ranking input rather than a printed percentage.

## Dependencies

- `ri-05`

## Acceptance Outcomes

- Running analyze_failures.py over a fixture with the same gap reported by two sources yields one ranked finding with source_count 2 rather than two raw entries.
- generate_report_multi_source is invoked from main() and its output section appears in the generated improvement report (asserted by test).
- GitHub issue #494 is closed by the merged change.

## Rationale

Section 6 defect 3, filed as GitHub issue #494. Section 2 notes that cross-source agreement is described as the strongest signal yet never filters; the dedup path is a self-documented dead branch. The gap ledger and corroboration floor in Phase 3 build on this ranking.
