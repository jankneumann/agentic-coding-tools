# Events — extend-kanban-viz-multi-repo-proposals

**This change introduces no new event-bus channels or SSE event types.**

Same posture as PR #211: the refresh model is on-demand pull with caching
(now hybrid: local at boot, github lazy with 60s TTL). No NOTIFY/LISTEN
wiring for proposal-source events in v1.

The existing `/events/work` SSE stream continues to carry `transition` and
`audit` events for `work_queue` rows only, unchanged by this change.

## Future events (out of scope)

- **`source_warning` SSE channel** — could push `_warnings` entries to the
  SPA in real time so a github-source 404 surfaces without waiting for the
  next refresh. Deferred until operators complain about discovery latency
  on partial failures.
- **`proposal_branch_changed` channel** — could invalidate the github source
  cache for a specific repo when a `openspec/<change-id>` branch is created
  or pushed to. Would require GitHub webhook ingestion, which is explicitly
  out of scope for this proposal.
