# Contracts

This change has no closed HTTP, database, or event contract. It changes two in-process durable contracts.

## Checkpoint transaction

The checkpoint ledger is the execution authority. A shared per-workspace transaction loads current checkpoint state under the common process-safe lock and writes one atomic payload containing all state and `gate_decisions`. A caller may evaluate an approval outside that transaction, but must recheck its exact dispatch, parked kind, and lease generation inside it before appending a decision or creating a continuation. Mirror and handoff are derived, repairable projections.

## Escalate resume

New `escalate_resume` decision records carry optional positive integer `lease_generation`; generationless legacy records remain readable and reusable for the current parked generation. A `gate-decision:<decision_id>` proceed reference authorizes the same dispatch and parked generation only.

Automatic and manual policy-pause context contains exactly:
`dispatch_id`, `change_id`, `item_id`, `lease_generation`, `verb: "resume"`, and `reason: "supervised phase retry budget exhausted"`.

`route_parked_escalations` returns at most one bounded entry per batch attempt:
- all entries: `dispatch_id`, `outcome`, `decided_lease_generation`;
- `proceed` or `already_routed`: additionally `resumed_lease_generation`;
- `blocked`: additionally one supervisor-normalized `pending_gate`.

No route input, durable record, or result may contain child transcript, raw approval data, child-provided reason, or additional context keys.

## Delegated apply cohort

For a named batch, apply requires results exactly for attempts whose current application-journal state is not `effects_applied`. All submitted results still require the current dispatch identity, lease generation, isolation, evidence, and journal digest. Already-applied peers are omitted and rejected if submitted.
