# Add the adapter-backed test substitute and dry-run policy

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `add-the-adapter-backed-test-substitute-and-dry-run-policy`
> Effort: S
> Priority: 2

## Summary

Stand up the testing convention for every later site: a reusable `system_one_decisions.testing` module stubs `decide`/`decide_intent`, behavioural wiring tests use `system-one-adapter` (Anthropic provider, `llm_answer_mode="probabilities"`) with test names marking its probabilities uncalibrated, and `decide()` gains an explicit `dry_run` parameter that guarantees no client is ever constructed when set.

## Dependencies

- `ri-02`

## Acceptance Outcomes

- A reusable helper in `system_one_decisions.testing` stubs `decide`/`decide_intent` and is exercised by at least one test that asserts the caller's fallback rule still runs when the stub returns `None`.
- Adapter-backed behavioural tests are skipped unless both `ANTHROPIC_API_KEY` and `SYSTEM_ONE_ADAPTER_TESTS=1` are set, and every such test name contains "uncalibrated".
- `decide(..., dry_run=True)` returns `None` and constructs zero clients, verified by a test that asserts the client-construction seam is never reached — establishing the enforcement point a future call-site migration's own `--dry-run` flag threads into (corrected during `/iterate-on-plan`: no `system_one`-consuming script exists yet to test end-to-end, per `plan-findings.md` #1).

## Rationale

The proposal's integration seam requires a CI substitute because the repo's convention is no network in dry-run and CI. Landing the substitute and the naming rule once keeps every Group A/B/C item from re-inventing it and prevents an adapter's self-reported probabilities from being mistaken for calibrated ones in test output. Grounded against the real `system-one-adapter` PyPI package (v0.2.0, introspected directly): it shares `typesafe_sdk`'s exact `SystemOneResponse`/exception types, so `decide()`'s existing client-handling code needs no changes to accept it as a test substitute.
