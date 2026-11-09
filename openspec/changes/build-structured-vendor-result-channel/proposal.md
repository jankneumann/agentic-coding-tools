# Build structured vendor result channel

> Parent roadmap: `dispatch-governance` (dg-02)
> Change ID: `build-structured-vendor-result-channel`
> Effort: M
> Priority: 1

## Summary

Switch every CLI adapter to its vendor's structured JSON output mode with typed envelopes, replace stdout-regex completion polling with a coordinator completion ledger (submit_work/complete_work as the single source of dispatch state), add GET /locks?agent_id= plus bulk release to fix the cloud lock leak, and extend or explicitly document SdkVendorAdapter coverage beyond review-only.

## Selected Approach

Use one versioned `VendorResultEnvelope` for every CLI result: synchronous commands return a terminal envelope; asynchronous submission returns a non-terminal envelope with the vendor task id; status commands return a later terminal envelope. The dispatcher validates this contract strictly and records one coordinator work item for the lifecycle, completing it with the terminal envelope. The coordinator exposes the existing filtered lock query and a privileged bulk-release operation through HTTP and the proxy bridge.

## Approaches Considered

1. **Versioned envelope plus completion ledger (selected).** Make vendor protocol differences adapters behind one JSON Schema and make the coordinator work item the durable lifecycle record. This removes regex from both submission and polling and gives router consumers one result shape.
2. **Keep vendor-specific polling parsers.** Replace individual regexes with handwritten JSON readers in each adapter. This is smaller initially but preserves divergent result semantics and provides no durable dispatch lifecycle.
3. **SDK-only dispatch.** Avoid CLI parsing entirely by routing all vendors through SDKs. This is not viable: local CLI remains the preferred, deployed review path and the current SDK adapter is intentionally review-only.

Approach 1 is selected because it preserves configured CLI harnesses while making malformed vendor protocol changes fail loudly and auditable.


## Dependencies

- None

## Acceptance Outcomes

- No task_id_pattern or success_pattern regex remains on the primary result path for any vendor.
- A vendor CLI output-format change degrades to a loud structured error rather than a silent hang.
- Killed cloud sessions release their locks via the new list-and-release-by-agent HTTP endpoints instead of waiting out the 120-minute TTL.

## Rationale

Regex-scraping vendor CLI stdout is the most fragile link in the whole chain (weakness W3); structured results are a required input for the router, the orchestrator's ledger-verified switching, native fan-out, and the cloud lane.

## Non-functional Requirements

| Attribute | Target | Verification |
| --- | --- | --- |
| Protocol safety | malformed or unsupported vendor payload yields a typed error without retrying a regex path | adapter unit tests |
| Observability | each asynchronous lifecycle has one ledger work id and the terminal envelope is persisted in `complete_work` | bridge/dispatcher integration tests |
| Lock recovery | release-by-agent is idempotent and returns a released-count audit result | coordinator API and service tests |
