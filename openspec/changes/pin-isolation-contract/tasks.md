# Tasks: Pin the isolation contract between router and dispatch

> Change ID: `pin-isolation-contract`
> Plan approval: user approved 2026-09-22; `container` is explicitly deferred.

## 1. Canonical vocabulary and configuration

- [x] 1.1 **S** Write RED tests for canonical values, invalid rung errors,
  source provenance, per-mode fallback, and exact-agent disambiguation.
  **Spec scenarios**: vendor-dispatch.1–.6. **Design decisions**: D1, D2.
- [x] 1.2 **M** Add the pure isolation contract and wire `agents_config` schema,
  `ModeConfig`, parsing, backward-compatible lookup, and dispatch-config output.
  **Dependencies**: 1.1. **Design decisions**: D1, D2, D3.

## 2. Router and fallback parity

- [x] 2.1 **S** Write RED router/fallback parity and static-contract parity tests,
  including a mode override on a repeated agent type.
  **Spec scenarios**: vendor-dispatch.1, .4–.6. **Design decisions**: D1, D3.
- [x] 2.2 **M** Apply the shared helper in registry/resolver and local routing
  fallback; parse the additive field in the review dispatcher.
  **Dependencies**: 1.2, 2.1. **Design decisions**: D1, D3.
- [x] Checkpoint: run targeted coordinator and skills tests, review the diff, and
  verify no dg-06 execution or dg-07 enforcement code entered scope.

## 3. Evidence and validation

- [x] 3.1 **S** Preserve the vendor plan-review manifest and incorporate its
  actionable findings into the design and test matrix.
- [x] 3.2 **S** Run strict OpenSpec, targeted suites, affected lint, and full
  cross-boundary regression; update the roadmap only after green evidence.
