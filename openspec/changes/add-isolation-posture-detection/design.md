# Design: Isolation posture detection

## Context

The detector collapses filesystem workspace isolation and network restriction into one
boolean. dg-07 needs those facts independently while current callers depend on
`isolation_provided`.

## Decisions

### D1 — Nested factual booleans

`IsolationPosture.filesystem` means the harness supplies a per-session workspace.
`IsolationPosture.network` means it enforces restricted egress. Neither claims a
containment strength.

### D2 — Read and construction compatibility

`EnvironmentProfile.isolation_provided` derives from `posture.filesystem`. The legacy
constructor maps its boolean to filesystem and defaults network false. Supplying both
forms is an error.

### D3 — Signals prove only their own dimension

Precedence is applied independently per dimension across explicit env, coordinator,
heuristic, and default layers. Exact Claude/Codex cloud markers prove filesystem;
`CODEX_SANDBOX_NETWORK_DISABLED` proves network. A higher filesystem result does not
prevent a lower layer from resolving network, while a structured coordinator network
value blocks a lower network heuristic. The canonical coordinator field is
`isolation_posture`; malformed canonical data rejects that layer and never falls back
to a simultaneously supplied legacy boolean.

### D4 — Migrate only worktree decision points

Worktree and merge entrypoints read `posture.filesystem`; other callers retain the
compatibility property. Fallback imports expose the same surface and output is unchanged.

## Failure and verification

Unknown explicit values fall through. Malformed coordinator values do not coerce.
Tests first pin the model and truth table, then subprocess behavior. Focused/full tests,
Ruff, strict OpenSpec validation, and multi-vendor review gate landing.
