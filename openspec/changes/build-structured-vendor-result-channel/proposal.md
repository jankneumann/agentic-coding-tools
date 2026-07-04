# Build structured vendor result channel

> Parent roadmap: `repo-improvement`
> Change ID: `build-structured-vendor-result-channel`
> Effort: M
> Priority: 1

## Summary

Switch every CLI adapter to its vendor's structured JSON output mode with typed envelopes, replace stdout-regex completion polling with a coordinator completion ledger (submit_work/complete_work as the single source of dispatch state), add GET /locks?agent_id= plus bulk release to fix the cloud lock leak, and extend or explicitly document SdkVendorAdapter coverage beyond review-only.

## Dependencies

- None

## Acceptance Outcomes

- No task_id_pattern or success_pattern regex remains on the primary result path for any vendor.
- A vendor CLI output-format change degrades to a loud structured error rather than a silent hang.
- Killed cloud sessions release their locks via the new list-and-release-by-agent HTTP endpoints instead of waiting out the 120-minute TTL.

## Rationale

Regex-scraping vendor CLI stdout is the most fragile link in the whole chain (weakness W3); structured results are a required input for the router, the orchestrator's ledger-verified switching, native fan-out, and the cloud lane.
