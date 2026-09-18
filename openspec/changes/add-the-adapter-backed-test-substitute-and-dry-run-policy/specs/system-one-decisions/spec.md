## ADDED Requirements

### Requirement: `decide()` accepts a `dry_run` flag that guarantees zero client construction
`decide(state, questions, *, site, event_sink=None, dry_run: bool = False)` SHALL,
when `dry_run` is `True`, return `None` immediately without importing
`typesafe_sdk`, checking `TYPESAFE_API_KEY`, estimating tokens, or calling
`_get_client()`. The default `dry_run=False` SHALL leave every existing
behavior from `wire-the-live-typesafe-client-thresholds-and-telemetry`
unchanged.

#### Scenario: dry_run short-circuits before any unavailability check
WHEN `decide()` is called with `dry_run=True`, a valid `TYPESAFE_API_KEY` set,
and a `_get_client` that raises `AssertionError` if invoked
THEN it SHALL return `None` and SHALL NOT raise, proving `_get_client` was
never called.

#### Scenario: Omitting dry_run preserves existing behavior
WHEN `decide()` is called with `dry_run` omitted (or explicitly `False`) and
all four `ri-02` unavailability branches are absent
THEN it SHALL proceed to call the live client exactly as it did before this
item, unchanged.

### Requirement: `system_one_decisions.testing` provides reusable stubs for `decide`/`decide_intent`
The package SHALL export `system_one_decisions.testing.stub_decide` and
`stub_decide_intent`, each accepting a pytest `monkeypatch` fixture and an
optional `returns` value, patching `decide`/`decide_intent` for the duration
of a test.

#### Scenario: A stubbed decide() lets the caller's own fallback rule run when it returns None
WHEN a caller uses `stub_decide(monkeypatch, returns=None)` and then calls
code built directly on `decide()` that checks for a `None` result and runs
its own fallback in that case
THEN the caller's fallback rule SHALL run, proving the stub requires no real
client, key, or network access.

#### Scenario: A stubbed decide_intent() returns the caller-configured Decision
WHEN a caller uses `stub_decide_intent(monkeypatch, returns=<a specific
Decision>)` and then calls `decide_intent(...)`
THEN it SHALL return exactly that configured `Decision`, deterministically,
without depending on `decide_intent`'s own always-fallback contract.

### Requirement: Adapter-backed behavioural tests are double-gated and named `uncalibrated`
Behavioural tests that exercise `decide()` against a real
`system_one_adapter.SystemOneAdapterClient` (Anthropic provider,
`llm_answer_mode="probabilities"`) SHALL be skipped unless both
`ANTHROPIC_API_KEY` and `SYSTEM_ONE_ADAPTER_TESTS=1` are set in the
environment, and every such test's function name SHALL contain the
substring `uncalibrated`.

#### Scenario: Behavioural adapter tests skip when the opt-in env is absent
WHEN `packages/system-one-decisions/tests` runs with `SYSTEM_ONE_ADAPTER_TESTS`
unset (whether or not `ANTHROPIC_API_KEY` happens to be set)
THEN every adapter-backed behavioural test SHALL be skipped, not run and not
error.

#### Scenario: Every adapter-backed test name signals uncalibrated probabilities
WHEN the test suite is collected
THEN every test function that constructs a real `SystemOneAdapterClient`
SHALL have `uncalibrated` in its function name.
