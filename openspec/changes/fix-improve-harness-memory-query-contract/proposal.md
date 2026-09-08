# Fix improve-harness memory query payload and capability_gap tag matching

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `fix-improve-harness-memory-query-contract`
> Effort: M
> Priority: 1

## Summary

Make analyze_failures.py send the fields MemoryQueryRequest declares (including agent_id, dropping time_window_days) and match capability_gap:* tags by prefix instead of the bare capability_gap tag, either by expanding tags client-side or by adding a prefix predicate to the coordinator memory query; apply the same fix to skills/agent-metrics/scripts/query_metrics.py. Add a test against a fake or live coordinator.

## Dependencies

- None

## Acceptance Outcomes

- POST /memory/query issued by analyze_failures.py passes MemoryQueryRequest validation (test asserts a 200 from a fake coordinator with the exact payload).
- A memory entry tagged capability_gap:missing-retry is returned by the improve-harness query and by query_metrics.py; a test seeds such an entry and asserts it appears.
- GitHub issue #493 is closed by the merged change.

## Rationale

Section 6 defects 1 and 2, filed as GitHub issue #493. The consumer of the four-source capability-gap pipeline cannot currently read from the coordinator at all: the request fails validation and even a valid request would never match stored tags because the SQL predicate is exact array overlap. Nothing downstream in Phase 3 or 4 is testable until this works.
