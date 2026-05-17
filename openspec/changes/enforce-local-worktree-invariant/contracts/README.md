# Contracts

No OpenAPI, database, event, or generated type contracts apply to this change.

The implementation modifies local skill/runtime behavior and documentation. The
coordination boundary is the Python helper API plus SKILL.md invariant tests:

- `skills/shared/checkout_policy.py`
  - `classify_checkout(...) -> CheckoutPolicy`
  - `require_mutation_allowed(...) -> CheckoutPolicy`
  - CLI: `python -m shared.checkout_policy require-mutation [--sync-point] [--json]`
- SKILL.md text invariants under `skills/tests/`

These are covered by the spec deltas and work-package verification commands.
