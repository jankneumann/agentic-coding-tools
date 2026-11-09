## ADDED Requirements

### Requirement: Per-round judgment cannot extend max_rounds

The convergence loop MUST treat `max_rounds` as a hard ceiling on review
rounds regardless of any judged answer about whether another round is
likely to help.

#### Scenario: Round-continuation judgment stays favorable throughout

- **WHEN** a round-continuation `Noul` answer stays high (favors another
  round) on every round up to `max_rounds`
- **THEN** the loop still stops at `max_rounds` and returns
  `reason="max_rounds"`

### Requirement: Per-finding disposition routes to existing ledger paths

For each blocking finding in a round, the convergence loop MUST classify a
disposition of `fix_now`, `defer_to_followup`, `reject_out_of_scope`, or
`needs_human`, and MUST route non-`fix_now` dispositions through the
existing `park_item(ledger, item, reason=...)` call rather than any new
ledger mutation path. Only `fix_now` items are included in the batch handed
to `fix_callback`.

#### Scenario: needs_human parks as a disagreement

- **WHEN** a blocking finding is classified `needs_human`
- **THEN** the finding is parked via `park_item(..., reason="disagreement")`
- **AND** `fix_callback` is not invoked for that finding

#### Scenario: defer_to_followup and reject_out_of_scope park without a new mutation surface

- **WHEN** a blocking finding is classified `defer_to_followup` or
  `reject_out_of_scope`
- **THEN** the finding is parked via the same `park_item` call needs_human
  uses, with a disposition-specific `reason`
- **AND** no new ledger schema field is written

#### Scenario: fix_now is dispatched normally

- **WHEN** a blocking finding is classified `fix_now`
- **THEN** the finding's scoped fix payload is included in the batch passed
  to `fix_callback`, unchanged from today's behavior

### Requirement: Classification unavailability defaults to today's behavior

When the classification helper is unavailable (its module cannot be
imported, the underlying decision call returns no answer, or there are no
blocking findings to classify), the convergence loop MUST default every
blocking finding to `fix_now` and MUST leave the stall rule
(`trend[-1] >= trend[-stall_window]`) governing convergence exactly as it
did before this capability existed.

#### Scenario: Helper returns no answers

- **WHEN** the classification call returns no usable answer for a round
- **THEN** every blocking finding in that round defaults to `fix_now`
- **AND** the existing convergence test suite passes unchanged

### Requirement: Dispatch-count replay is fixture-scoped pending persisted trend history

A pure replay function MUST compare the total number of `fix_callback`
dispatches the disposition-aware routing would issue against the total the
prior unconditional "dispatch every blocking item every round" rule would
have issued, for the same sequence of per-round blocking findings and the
same terminal blocking count, over a caller-supplied (fixture) sequence of
rounds. Comparison against real production round-by-round trend history is
out of scope until autopilot persists that history from real runs -- no
such history is recorded anywhere in this codebase today.

#### Scenario: Fewer dispatches for the same terminal blocking count

- **WHEN** the replay is given a fixture sequence of rounds where one
  finding is repeatedly classified `defer_to_followup` or
  `reject_out_of_scope` while remaining in the raw blocking count each round
- **THEN** the disposition-aware dispatch count is strictly lower than the
  unconditional-dispatch count
- **AND** both counts and the terminal blocking count are reported together
