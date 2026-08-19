# Add anomaly-gated semantic failure detection hook

> Parent roadmap: `closed-loop-learning`
> Change ID: `add-anomaly-gated-semantic-failure-detection-hook`
> Effort: L
> Priority: 1

## Summary

Implement a PostToolUse hook (Claude Code adapter first) with two stages, a deterministic anomaly gate (failed tool calls, nonzero exits, error-shaped output) that decides when to classify, and an economy-tier classifier that parses the recent trace and maps its diagnosis to registry signal types with a confidence score. Detection prompts for all active signal types are batched into one windowed call, verdicts are cached per session against a context fingerprint, and cost is attributed and capped.

## Dependencies

- `ri-02`
- `ri-03`

## Acceptance Outcomes

- No classification occurs on clean tool results; the deterministic anomaly gate alone decides when the classifier runs and never decides what matched.
- Each detection event issues exactly one windowed classification call batching all active detection prompts to an economy-tier model, never one call per lesson.
- Verdicts are cached per session against a context fingerprint, and per-session detection cost is attributed in usage accounting and capped.
- No exact string matching exists anywhere on the detection path, and malformed or low-confidence verdicts are discarded with no steering power.
- The hook lands behind the per-harness adapter seam and degrades to a no-op (never a block) when the coordinator or hook surface is unavailable, and no LLM SDK calls appear inside skill scripts/.

## Rationale

This replaces Abacus's fragile exact-string tripwires with semantic detection, the deliberate departure named in the proposal - the same root cause recurs under different wording across vendors, and this repo has been bitten by string matching before. The anomaly gate is purely a cost valve, never a match verdict.
