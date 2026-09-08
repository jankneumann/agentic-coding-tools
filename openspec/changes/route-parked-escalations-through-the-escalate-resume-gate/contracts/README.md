# Contracts

This change adds no closed wire, database, or event contract. The open gate-decision schema gains an optional `lease_generation` integer documenting the parked dispatch generation authorized by `escalate_resume`; it is absent for other gates.

`ExecutionAdapter.apply` retains its exact current Python signature, return shape, and keys. The separate `ExecutionAdapter.route_parked_escalations` returns at most one entry per named-batch attempt:

- every entry contains exactly `dispatch_id`, `outcome`, and `decided_lease_generation`;
- `outcome` is `proceed`, `blocked`, `deferred`, or `already_routed`;
- `proceed` and `already_routed` additionally contain exactly `resumed_lease_generation`;
- `blocked` additionally contains exactly a supervisor-record-normalized `pending_gate`;
- `decided_lease_generation` is the parked generation on the gate record; `resumed_lease_generation` is its post-increment continuation.

For an automatic policy pause, approval request/notification context contains exactly `dispatch_id`, `change_id`, `item_id`, `lease_generation`, `verb`, and `reason`. The first four values come from the validated durable attempt, `verb` is exactly `resume`, and `reason` is exactly `supervised phase retry budget exhausted`. Outputs and request context contain no transcripts, raw approval payloads, child-provided reason, or additional fields.
