# Supervised dispatch contracts

This change adds no HTTP API, database schema, or event bus event. Its coordination boundary is the host-assisted callback between the roadmap orchestrator and a background Autopilot agent:

- `schemas/bounded-dispatch-context.schema.json` is the shared four-level, case-insensitive secret-key-rejecting context contract.
- `schemas/supervised-dispatch-request.schema.json` fixes identity, scope, isolation, and references that bounded context.
- `schemas/supervised-dispatch-result.schema.json` extends the existing dispatch outcome vocabulary with a bounded `parked` state while deliberately excluding transcript content.
- `schemas/delegated-dispatch-attempt.schema.json` defines the additive durable checkpoint entry used for crash-safe correlation.

Success and parked results carry attempt, lease generation, worktree, branch, and loop-state evidence; apply performs exact prepared-attempt matching plus realpath containment. The attempt schema encodes the acknowledgement/go barrier, claimed/launched/quarantined separation, bounded launch history, gate-only parked continuation, and mutually consistent state/outcome pairs. Request context is sanitized before persistence and bounded to 16 KiB canonical JSON, four levels, and 32 top-level keys.

The Python callback remains the in-process interface. These JSON Schemas provide fixtures and cross-harness validation without adding a network transport or direct model call.
