# Build agent trajectory scenario harness

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `build-agent-trajectory-scenario-harness`
> Effort: L
> Priority: 3

## Summary

A new packages/agent-scenarios/ harness where scenario YAML defines a task prompt, fixture repo state, skill under test, and goal gates (expected file/branch/PR/artifact outcomes plus prohibited side effects, reusing gen-eval's ExpectBlock/SideEffectsBlock vocabulary); the runner executes headless per vendor, scores goal gates deterministically plus an LLM-judge trajectory review over collect-transcripts output, and emits review-findings.schema.json findings.

## Dependencies

- None

## Acceptance Outcomes

- A scenario YAML with goal gates executes headless against at least 2 vendors and produces deterministic goal-gate scores.
- LLM-judge trajectory review runs over normalized transcripts and contributes to the verdict.
- Failures emit findings conforming to review-findings.schema.json.

## Rationale

The genuinely new attractor-inspired piece — gen-eval validates the system under test, but nothing validates the agents themselves; this enables cross-vendor parity checks before the dispatcher routes real work through changed skills.
