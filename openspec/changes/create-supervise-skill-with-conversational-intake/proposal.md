# Create supervise skill with conversational intake

> Parent roadmap: `roadmap-supervisor-orchestration`
> Change ID: `create-supervise-skill-with-conversational-intake`
> Effort: M
> Priority: 1

## Summary

Scaffold `skills/supervise/` as the single conversational entry point the human talks to, playing the supervisor archetype from the host harness session. Implement the intake verb, which turns a natural-language request into an OpenSpec change or proposal and slots it via `/plan-roadmap`.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- Invoking /supervise with a natural-language feature request produces an OpenSpec change or proposal stub slotted through /plan-roadmap without the human invoking plan-roadmap directly.
- The skill makes no direct LLM API calls, honoring the host-assisted invariant in skills/autopilot-roadmap/SKILL.md.
- The supervisor session never edits implementation files itself, verified by an audit check over the session's file writes.

## Rationale

Establishes the missing layer above the orchestration stack, the persistent conversational counterpart (Mayor / First Mate role), so the human no longer invokes each skill by hand.
