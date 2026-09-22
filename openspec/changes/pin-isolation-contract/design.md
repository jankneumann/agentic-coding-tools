# Design: Pin the isolation contract between router and dispatch

## Decision D1 — One pure module serves both runtime paths

`agent-coordinator/src/isolation_contract.py` is the one definition of
`none`, `worktree`, and `sandbox`. It is stdlib-only and exports the static
type, allowed values, `IsolationContractError`, validation, an
`IsolationResolution(value, source)` result, and a pure per-mode helper.

The coordinator imports it normally. The coordinator-unreachable fallback
loads the same file through its checkout-root import shim. Published dg-04
schemas retain serialized enums, but parity tests derive expected values from
D1 rather than hand-maintained runtime definitions.

## Decision D2 — Resolution records absence, invalid values, and provenance

The ladder is: a reachable router's present valid value (`source=router`); the
matching configured agent's mode override then entry default
(`source=agents_yaml`); and `none` (`source=default`). Absent values fall
through. A present invalid value raises `IsolationContractError` naming the
rung; empty values are never silently coerced with `or "none"`.

`get_agent_isolation(agent_type, dispatch_mode=None, *, agent_id=None)` stays
source-compatible. Router and fallback call sites that know identity supply it,
preventing local/remote entries of the same type from depending on YAML order.

## Decision D3 — Mode overrides apply before assignments are emitted

`ModeConfig` gains optional `isolation`. `vendor_registry` exposes mode-aware
information and the resolver computes assignment isolation after dispatch mode
is known. The fallback uses the same helper before filtering or sorting a lane.
Dispatch-config projection and the skills review dispatcher parse the additive
field. dg-06 execution wiring and dg-07 enforcement remain excluded.

## Decision D4 — Widening requires an explicit amendment

`container` is not valid in this change. `add-sandboxed-harness-execution` must
