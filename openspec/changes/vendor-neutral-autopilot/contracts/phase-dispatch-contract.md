# Phase Dispatch Contract

## Payload

A lifecycle phase dispatch payload MUST contain:

- `schema_version`: integer, currently `1`
- `change_id`: OpenSpec change identifier
- `phase`: autopilot or lifecycle phase name
- `provider`: provider identifier (`claude_code`, `codex`, `gemini`)
- `archetype`: logical archetype name
- `model`: provider-specific model identifier
- `prompt`: final prompt text
- `system_prompt`: optional system prompt, included for observability
- `isolation`: `shared`, `worktree`, `sandbox`, or `none`
- `expected_outcomes`: list of allowed outcome strings

## Result

A lifecycle phase dispatch result MUST contain:

- `schema_version`: integer, currently `1`
- `outcome`: normalized outcome string
- `handoff_id`: handoff identifier, or local fallback identifier
- `provider`: provider identifier used for dispatch
- `model_used`: provider-specific model identifier actually attempted
- `dispatch_tier`: `harness`, `cli`, `sdk`, `dry_run`, or `fallback`
- `warnings`: list of non-blocking warning strings

## Error Handling

Provider adapters MUST return a structured failed result for recoverable runtime failures rather than leaking provider-specific output directly into `loop-state.json`.

Provider adapters MUST NOT pass Claude model aliases to non-Claude providers unless the provider mapping explicitly declares those aliases valid.

