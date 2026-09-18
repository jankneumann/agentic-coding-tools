# Wire the live TypeSafe client, thresholds and telemetry

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `wire-the-live-typesafe-client-thresholds-and-telemetry`
> Effort: M
> Priority: 1

## Summary

Add typesafe-sdk under a "live" optional extra of packages/system-one-decisions, have the package build the live client from TYPESAFE_API_KEY behind a token-budget guard, and record site, latency, usage.input_tokens and the answered probabilities to the existing Langfuse hook. Establish the per-site threshold convention: thresholds live in architecture.config.yaml or the skill's own config beside the rule they replace, never as literals in a scoring module.

## Dependencies

- `ri-01`

## Acceptance Outcomes

- packages/system-one-decisions declares a "live" extra containing typesafe-sdk; the default install of the package and of every consumer still succeeds without it.
- typesafe_sdk is imported inside packages/system-one-decisions and nowhere else in the repository, enforced by a grep-style guard test.
- decide returns None (never raises) when the key is absent, the network fails, or serialized state plus the longest question exceeds the 32K-token budget, with one test per branch.
- Each completed call emits one Langfuse record carrying site, latency_ms, usage.input_tokens and the per-label probabilities.
- A guard test asserts no float threshold literal is introduced into the package; defaults resolve from architecture.config.yaml.

## Rationale

Turns the fallback-only seam into a working integration while honouring the integration-seam constraints: SDK imported in exactly one package, PyPI-only cloud harness network policy respected via an optional extra so the fallback-only install never needs it, no threshold literals in scoring modules per the context_eval convention, and every judgment-derived value carrying its probability.
