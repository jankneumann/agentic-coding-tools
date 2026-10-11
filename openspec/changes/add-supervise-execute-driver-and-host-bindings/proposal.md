# Commit a supervise execute driver core with per-harness host bindings

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `add-supervise-execute-driver-and-host-bindings`
> Effort: M
> Priority: 2

## Summary

Add a committed, harness-neutral driver for /supervise execute that owns the ExecutionAdapter call order (prepare, child-start, acknowledge, enter, collect, apply, route escalations, reconcile) and a per-harness host binding interface for the four injected seams (launch, handle, liveness, entry), keyed by a stable harness identity. A harness with no committed binding runs with an ephemeral binding, records a host_binding_ephemeral degradation, and files the binding as candidate work rather than self-committing it. Bindings may be part code and part procedure where liveness is only observable by the host session (Claude Code task notifications).

## Dependencies

- None

## Acceptance Outcomes

- A committed execute driver core drives ExecutionAdapter end to end with no harness-specific code in it.
- A binding is accepted only when the supervised-dispatch and dispatch-contract e2e suites pass against it in place of their fakes.
- The supervisor deterministically detects a missing binding for its harness identity, runs with an ephemeral binding, records a host_binding_ephemeral degradation, and emits a candidate-work stub for the binding.
- A local Claude Code binding (GX10) is committed and used by a subsequent /supervise execute run without regenerating driver code.

## Rationale

Makes delegated roadmap execution repeatable across harnesses, keeps the risky sequencing logic in one tested place, and gives the ri-08 dispatcher daemon a binding slot instead of a parallel implementation.
