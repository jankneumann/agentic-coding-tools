# Wire the live TypeSafe client, thresholds and telemetry

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `wire-the-live-typesafe-client-thresholds-and-telemetry`
> Effort: M
> Priority: 1

## Summary

Add typesafe-sdk under a "live" optional extra of packages/system-one-decisions, have the package build the live client from TYPESAFE_API_KEY behind a token-budget guard, and give `decide()` an optional caller-supplied `event_sink` (mirroring `decide_intent()`'s existing one) that receives site, latency, usage.input_tokens and the answered probabilities on every completed call — whether that reaches Langfuse is left to the caller, the same boundary `decide_intent()` already draws. Establish the per-site threshold convention: thresholds live in a package-owned data file (`packages/system-one-decisions/config/thresholds.yaml`), loaded by the package itself, never as literals in a scoring module — the same convention `packages/context-eval` already enforces via its own corpus data file, not `architecture.config.yaml` (that file is scoped exclusively to the architecture-report generator and has no threshold concept — corrected during `/iterate-on-plan`, see `plan-findings.md` #1).

## Dependencies

- `ri-01`

## Acceptance Outcomes

- packages/system-one-decisions declares a "live" extra containing typesafe-sdk; the default install of the package and of every consumer still succeeds without it.
- typesafe_sdk is imported inside packages/system-one-decisions and nowhere else in the repository, enforced by a grep-style guard test.
- decide returns None (never raises) when the live extra isn't installed, the key is absent, the network fails, or serialized state plus the longest question exceeds the 32K-token budget, with one test per branch (four branches, not three — see `plan-findings.md` #3).
- Each completed call passes site, latency_ms, usage.input_tokens and the per-label probabilities to `decide()`'s optional `event_sink`, exactly once.
- A guard test asserts no float threshold literal is introduced into the package; `act_floor`/`approve_floor` defaults resolve from `packages/system-one-decisions/config/thresholds.yaml`.

## Rationale

Turns the fallback-only seam into a working integration while honouring the integration-seam constraints: SDK imported in exactly one package, PyPI-only cloud harness network policy respected via an optional extra so the fallback-only install never needs it, no threshold literals in scoring modules per the context_eval convention, and every judgment-derived value carrying its probability. `decide_intent()`'s own acquisition step stays fallback-only in this item — flipping it to use the new live path is `ri-03`'s job, once the adapter-backed test substitute exists to make that switch safe.
