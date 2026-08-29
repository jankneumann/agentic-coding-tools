# Seal the archive benchmark corpus into development and holdout partitions

> Parent roadmap: `skill-rightsizing`
> Change ID: `seal-archive-benchmark-corpus-split`
> Effort: S
> Priority: 1

## Summary

Partition the 92 archived OpenSpec changes into a 60-change development split and a 32-change sealed holdout, recorded in a committed manifest with a checksum, and biased so the holdout draws from the most recent changes.

## Dependencies

- None

## Acceptance Outcomes

- A committed manifest assigns all 92 archived changes to exactly one partition.
- The manifest records a checksum that detects post-hoc reassignment.
- Tooling refuses to run holdout tasks unless explicitly invoked with a decision-run flag.
- The holdout partition is drawn predominantly from changes archived after 2026-05-01.

## Rationale

If skills are authored while looking at benchmark tasks, the benchmark measures memorization. Sealing costs nothing today and is impossible to reconstruct later.
