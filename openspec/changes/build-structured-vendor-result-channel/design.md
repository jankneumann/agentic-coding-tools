# Design: structured vendor result channel

## Context

The dispatcher previously treated vendor stdout as an implicit protocol. Async
submission extracted an id with `task_id_pattern`; polling decided completion
with `success_pattern` and `failure_pattern`. A harmless wording change could
therefore strand a task or report the wrong state. Remote work also had no
durable lifecycle record linking submission to its terminal payload.

## Decisions

### D1. One versioned envelope

Async commands consume `VendorResultEnvelope` version 1:

- `state`: `submitted`, `running`, `succeeded`, `failed`, or
  `cancelled`;
- `vendor_task_id`: required for non-terminal states and checked against the
  submitted id while polling;
- `result`: the structured terminal payload on success;
- `error`: structured failure details on failure or cancellation.

Malformed JSON, an unknown version/state, or a mismatched task id is a protocol
error. There is no stdout-regex fallback.

### D2. Ledger-first async lifecycle

Before a remote process starts, the adapter:

1. calls `submit_work` with a unique `vendor-dispatch-<correlation-id>` task
   type and non-secret routing metadata;
2. claims that exact row through the authenticated dispatcher identity so
   existing completion ownership rules remain intact;
3. launches the vendor command only after both operations succeed;
4. persists the terminal envelope through `complete_work`; and
5. consumes findings only after completion is acknowledged.

Submission, claim, polling, parse, timeout, and terminal vendor failures all
fail closed. If the ledger is unreachable before launch, no vendor process is
started. The HTTP queue request identity is optional: a bound API-key principal
is authoritative, while legacy unbound keys retain the existing `cloud-agent`
fallback.

### D3. Regex polling configuration is removed

`PollConfig` contains only the status command, the
`vendor-envelope-v1` protocol marker, interval, and timeout. The
`agents.yaml` schema no longer admits `task_id_pattern`,
`success_pattern`, or `failure_pattern`.

### D4. Unsupported live async lanes are not advertised

The installed Codex Cloud submission/status commands expose no structured JSON
mode, and Claude JSON output is limited to print-mode responses rather than
background task status. Their remote async CLI modes are removed from the live
registry until a vendor release or trusted wrapper emits this envelope. Codex
remote remains available for review through the OpenAI SDK; Claude remote
retains synchronous structured review. The full matrix lives in
`docs/guides/vendor-dispatch-capabilities.md`.

### D5. SDK scope stays review-only

`SdkVendorAdapter` supports only `review`. Both discovery and direct
`dispatch()` reject `alternative`, `quick`, or any unknown mode before
credential resolution or a network call.

### D6. Agent-scoped lock recovery is authenticated and idempotent

`GET /locks?agent_id=` lists an agent's locks and
`POST /locks/release-by-agent` bulk releases them. The service returns a
released count and repeated release is a successful zero-count operation.

## Failure handling

- A ledger open/claim failure prevents launch.
- A malformed vendor payload completes the ledger row as failed.
- A terminal envelope that cannot be persisted is not returned downstream.
- A poll timeout completes the row as failed with the timeout reason.
- A vendor task-id mismatch is treated as protocol corruption.

## Verification

- Parser and async lifecycle tests in
  `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`.
- Queue identity tests in `agent-coordinator/tests/test_coordination_api.py`
  and `skills/coordination-bridge/scripts/tests/test_coordination_bridge.py`.
- Lock recovery tests in `agent-coordinator/tests/test_locks.py`.
- The JSON Schema in `contracts/events/vendor-result-envelope.schema.json`.
