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
`stub_decide_intent`, each accepting a pytest `monkeypatch` fixture and a
`returns` value, patching the target's `decide`/`decide_intent` for the
duration of a test.

#### Scenario: A stubbed decide_intent still runs the caller's fallback rule
WHEN a caller uses `stub_decide_intent(monkeypatch, returns=None)` and then
invokes its own fallback-routing logic exactly as it would with a real
unavailable `decide_intent`
THEN the caller's fallback rule SHALL run and produce the same result as an
unpatched call under `ri-01`'s always-fallback contract.

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
