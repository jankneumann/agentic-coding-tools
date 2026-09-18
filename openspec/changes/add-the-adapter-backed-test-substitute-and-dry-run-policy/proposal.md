# Add the adapter-backed test substitute and dry-run policy

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-the-adapter-backed-test-substitute-and-dry-run-policy`
> Effort: S
> Priority: 2

## Summary

Stand up the testing convention for every later site: unit tests stub decide/decide_intent, behavioural wiring tests use system-one-adapter (Anthropic provider, llm_answer_mode="probabilities") with test names marking its probabilities uncalibrated, and --dry-run paths make no API call.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A reusable pytest fixture stubs decide/decide_intent and is exercised by at least one test that asserts the caller's fallback rule still runs when the stub returns None.
- Adapter-backed behavioural tests are skipped by default, run only when the adapter env is present, and every such test name contains "uncalibrated".
- A test asserts that running any system_one-consuming script with --dry-run performs zero client constructions.

## Rationale

The proposal's integration seam requires a CI substitute because the repo's convention is no network in dry-run and CI. Landing the substitute and the naming rule once keeps every Group A/B/C item from re-inventing it and prevents an adapter's self-reported probabilities from being mistaken for calibrated ones in test output.
