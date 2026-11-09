# Design: Add the adapter-backed test substitute and dry-run policy

> Change ID: `add-the-adapter-backed-test-substitute-and-dry-run-policy`
> Roadmap item: `ri-03` of `roadmap-jev-system-one-integration-assessment`

## Context

Every later Group A/B/C item that migrates a call site to `decide_intent()` will
need the same three things: a way to unit-test its fallback path without a real
client, a way to run *behavioural* tests of the wiring in CI without a real
`TYPESAFE_API_KEY`, and a way to guarantee `--dry-run` paths make no network call.
This item builds all three once, inside `packages/system-one-decisions`, so no
later item re-invents them.

## Real API surface (grounding, not aspiration)

`system-one-adapter` is a real, published PyPI package (confirmed via
`https://pypi.org/pypi/system-one-adapter/json`: latest `0.2.0`, "Drop-in
TypeSafeClient replacement backed by LLM APIs", extras `anthropic`/`openai`).
Installed (`system-one-adapter[anthropic]`) into a scratch venv and introspected
directly:

- `SystemOneAdapterClient(*, structured_outputs: bool, llm_answer_mode: AnswerMode,
  normalize_probabilities: bool = False, n_retry_malformed_structure: int = 0,
  retry: RetryPolicy | None = None, provider: ProviderName | None = None,
  model: str | ProviderT | None = None)`, where
  `AnswerMode = Literal["probabilities", "discrete"]` and
  `ProviderName = Literal["openai", "anthropic"]` (both confirmed by reading the
  installed package's source directly, not guessed).
- `.system_one(state, questions, *, provider=None, model=None, retry=None) ->
  SystemOneResponse` — **the same method name and the same `SystemOneResponse`
  type** `typesafe_sdk.TypeSafeClient.system_one` returns.
  `system_one_adapter.SystemOneResponse`, `.Usage`, `.ChoiceAnswer`, `.NoulAnswer`,
  `.ScoreAnswer` are the literal same classes re-exported from `typesafe_sdk`
  (confirmed: `system_one_adapter.providers.base.TypeSafeError is
  typesafe_sdk.TypeSafeError` → `True`).
- The `anthropic` provider reads `ANTHROPIC_API_KEY` implicitly via
  `anthropic.Anthropic(max_retries=0)` — no key is ever passed by this package.

Because the response and exception types are literally shared with
`typesafe_sdk`, `decide()`'s existing `_get_client()` / `except
typesafe_sdk.TypeSafeError` handling in `_core.py` (from `ri-02`) needs **no
branching** to accept a `SystemOneAdapterClient` in place of a `TypeSafeClient` —
whichever object `_get_client()` returns just needs a `.system_one(...)` method
with this shape, which is exactly Python's duck typing at work.

## Decisions

### D1 — `decide()` gains an explicit `dry_run` parameter

`decide(state, questions, *, site, event_sink=None, dry_run: bool = False)`.
When `dry_run=True`, `decide()` returns `None` immediately — before the
`typesafe_sdk` import, the key check, the token estimate, and before
`_get_client()` is ever called. Default `False` (today's live behavior,
unchanged — Rule 4: safe defaults). This resolves plan-findings.md #1: no
`system_one`-consuming script exists yet to test end-to-end, but the
enforcement point this item is responsible for building — "does `decide()`
ever construct a client when told not to" — is fully testable now. A future
call-site migration item threads its own `--dry-run` CLI flag into this
parameter; that wiring is that item's job, not this one's.

### D2 — `system_one_decisions.testing`: a stubbing helper, not a new package

A new submodule, `system_one_decisions/testing.py`, exports
`stub_decide(monkeypatch, *, returns)` and
`stub_decide_intent(monkeypatch, *, returns)` — thin wrappers around
`monkeypatch.setattr` that patch the target module's `decide`/`decide_intent`
name for the duration of a test and return the patch handle. Not a new
top-level package (that would duplicate this package's own import-boundary
work for no reason — plan-findings.md #3) and not an auto-registered
`pytest11` plugin (no existing package in this repo uses that mechanism;
inventing one here has no precedent and isn't needed — a one-line
`from system_one_decisions.testing import stub_decide_intent` already gives
every future consumer the reusable behavior the acceptance outcome asks for).
Exported from the package's default install (no extra required) since it has
no dependency beyond `pytest` itself, which every consumer already has as a
dev dependency.

### D3 — Behavioural adapter tests: explicit double opt-in, uncalibrated naming

Adds a `test-adapter` optional extra (`system-one-adapter[anthropic]`) to
`packages/system-one-decisions/pyproject.toml`, separate from `live`
(the real vendor SDK) and `dev` (this package's own unit tests) — the adapter
is neither. Behavioural tests that exercise `decide()` end-to-end against a
real `SystemOneAdapterClient` call:

1. Are skipped unless **both** `ANTHROPIC_API_KEY` is set **and**
   `SYSTEM_ONE_ADAPTER_TESTS=1` is set (plan-findings.md #4 — a key merely
   being present in the environment must not be enough to start spending
   money on a normally-skipped suite).
2. Have `uncalibrated` in every such test's function name, so a test-output
   grep or a reviewer scanning `pytest -v` output can never mistake an LLM's
   self-reported confidence for `ri-01`'s calibrated-probability contract.

No CI job runs these by default — CI never sets `SYSTEM_ONE_ADAPTER_TESTS`,
matching the repo's no-network-in-CI convention this item exists to formalize.

### D4 — Unit tests stub; behavioural tests use the adapter; nothing changes in `_core.py`'s branch logic

`decide()`'s four unavailability branches from `ri-02` are unchanged. The
adapter is a client *implementation* swapped in only by a test explicitly
constructing a `SystemOneAdapterClient` and monkeypatching `_get_client` to
return it (the same seam `ri-02`'s own tests already use for a fake client) —
`decide()` itself has no "which kind of client" branch to add, because the
adapter satisfies the exact same duck-typed interface. This is the payoff of
the grounding above: the "adapter-backed test substitute" the acceptance
outcome asks for requires zero production code changes beyond D1's
`dry_run` flag — it is entirely a test-fixture-and-convention item.

## Non-goals (out of scope for this item)

- No migration of any existing call site (same non-goal as `ri-01`/`ri-02`).
- No `openai` provider wiring — `anthropic` only, matching the proposal's
  stated choice.
- `decide_intent()`'s acquisition step remains fallback-only; `dry_run` is
  added to `decide()` only, since `decide_intent()` never constructs a client
  in the first place (unchanged from `ri-01`/`ri-02`).
- No CI job enables `SYSTEM_ONE_ADAPTER_TESTS` — that stays a local,
  developer-opt-in suite by design (D3).

## Risks

- **`system-one-adapter` version drift**: pin loosely (`>=0.2,<1`), same
  posture as `ri-02`'s `typesafe-sdk` pin.
- **No live credential in this environment**: same situation as `ri-01`/`ri-02` —
  the behavioural adapter tests cannot be run end-to-end in this session (no
  `ANTHROPIC_API_KEY`). This is not a gap in this item's own verification:
  the acceptance outcomes ask for the tests to *exist* and to *skip correctly*
  when the env is absent, both of which are directly verifiable without a key.
