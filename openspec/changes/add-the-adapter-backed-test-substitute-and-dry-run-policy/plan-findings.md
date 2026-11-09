# Plan Findings: add-the-adapter-backed-test-substitute-and-dry-run-policy

## Iteration 1

Baseline `openspec validate --strict` passed. Findings below come from installing
the real `system-one-adapter` package from PyPI (`system-one-adapter[anthropic]`,
v0.2.0) into a scratch venv and introspecting it directly, and from checking what
actually exists in the repo today, before writing any code.

| # | Type | Criticality | Description | Proposed Fix |
|---|------|-------------|-------------|--------------|
| 1 | feasibility | high | The third acceptance outcome ("a test asserts that running any system_one-consuming script with `--dry-run` performs zero client constructions") presumes a `system_one`-consuming script already exists. None does — call-site migration is explicitly out of scope for every roadmap item so far (`ri-01`'s and `ri-02`'s own non-goals) and doesn't start until `ri-09`. As stated, this outcome cannot be tested today. | Reframe as: `decide()` itself gains a `dry_run: bool = False` keyword parameter (default `False` = today's live behavior, unchanged — Rule 4). When `True`, it returns `None` immediately without importing `typesafe_sdk`, checking the key, or constructing a client. This establishes the enforcement point now; any future consuming script's own `--dry-run` flag just has to thread through to this parameter, which is that script's job, not this item's. |
| 2 | assumptions | medium | The real `system-one-adapter` package (introspected: `SystemOneAdapterClient(*, structured_outputs: bool, llm_answer_mode: AnswerMode, provider: ProviderName \| None, ...)`, `AnswerMode = Literal["probabilities", "discrete"]`, `ProviderName = Literal["openai", "anthropic"]`) is a genuine drop-in for `TypeSafeClient`: same `.system_one(state, questions) -> SystemOneResponse` signature, same `SystemOneResponse`/`Usage`/`ChoiceAnswer`/`NoulAnswer`/`ScoreAnswer` types (literally the same classes, re-exported), and the same `TypeSafeError` hierarchy (`system_one_adapter.providers.base.TypeSafeError is typesafe_sdk.TypeSafeError` confirmed True). This was assumed, not verified, before this iteration. | Confirmed via direct introspection (see design.md's "Real API surface"). `decide()`'s existing `_get_client()`/`except typesafe_sdk.TypeSafeError` already works unchanged with either client — no `_core.py` branching needed for "which client kind." |
| 3 | scope | medium | "A reusable pytest fixture stubs decide/decide_intent" doesn't say where it lives. Putting it in a separate top-level package would duplicate `packages/system-one-decisions`'s own import-boundary work for no reason; putting it only in one consumer's test tree defeats "reusable... at every later site." | `system_one_decisions.testing` submodule, inside the existing package (no new package). Exported as plain importable helpers, not an auto-registered `pytest11` entry point — no existing package in this repo uses that plugin mechanism, and inventing packaging metadata with no precedent is unnecessary for something a one-line `pytest_plugins = [...]` import already solves simply. |
| 4 | testability | medium | "run only when the adapter env is present" doesn't name which env variable. `ANTHROPIC_API_KEY` alone isn't a good gate — CI secret-scanning or an accidentally-set org-wide key could make behavioural tests silently attempt real calls. | Gate on `SYSTEM_ONE_ADAPTER_TESTS=1` (an explicit opt-in this item introduces), checked in addition to `ANTHROPIC_API_KEY` being set — both must be true. Prevents a key merely being present in someone's shell from making a normally-skipped test suite start spending money. |

## Resolution

All four findings are addressed in this iteration's `design.md` (D1-D4) and
`tasks.md`. No findings remain above the `medium` threshold after this pass.
