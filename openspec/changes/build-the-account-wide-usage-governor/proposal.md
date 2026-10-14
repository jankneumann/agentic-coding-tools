# Build the account-wide usage governor

> Parent roadmap: `operator-front-door`
> Change ID: `build-the-account-wide-usage-governor`
> Effort: L
> Priority: 2

## Summary

A single view and routing policy over Claude Max, Codex, Gemini AI Pro, Grok, OpenRouter, and GX10 local models that, before each dispatch, picks the source for the archetype from a configurable routing table and checks headroom, queueing or raising a decision card instead of silently downgrading.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A single governor query returns the current headroom estimate and observed consumption for each of the six capacity sources.
- A dispatch whose preferred source lacks headroom is queued or raises a decision card, and a test proves no dispatch executes on a lower tier or different vendor without a recorded decision.
- OpenRouter spend stops at the operator-set budget; a dispatch that would exceed it is refused with a card and not executed.
- Changing an archetype's primary implementer from Claude to Codex in the routing configuration changes routing with no code change.
- The governor reports usage under a single Claude account and has no configuration path for pooling multiple seats of one vendor.
- When always-on-agent-automation ri-10 signals are absent the governor reports its own estimate and names the missing signal source; when present they are used without a governor code change.

## Rationale

Capacity across six sources is currently spent by accident; this makes it deliberate and visible and enforces the no-silent-downgrade and OpenRouter-budget constraints. Builds on the model usage ledger, multi-model usage stats, coordinator LLM gateway, and always-on-agent-automation ri-10 rate-limit accounting rather than a parallel ledger; can proceed in parallel with the queue. Operator decision: no hard dependency on always-on-agent-automation ri-10; the governor keeps its own headroom estimate and consumes ri-10's cost/quota signals when they exist, behind a source interface so ri-10 plugs in without a governor change.
