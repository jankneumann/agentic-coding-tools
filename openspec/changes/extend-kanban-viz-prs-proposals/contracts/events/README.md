# Events — extend-kanban-viz-prs-proposals

**This change introduces no new event-bus channels or SSE event types.**

Per design D2, the refresh model is on-demand pull with a 60s cache. We
explicitly do not wire NOTIFY/LISTEN for PR or proposal updates in v1.

The existing `/events/work` SSE stream continues to carry `transition`
and `audit` events for `work_queue` rows only, unchanged by this change.

## Future events (out of scope for v1)

If/when `/merge-pull-requests` wires a NOTIFY on PR merges (so the
coordinator can invalidate the `/github/prs` cache), the event surface
would land here as e.g. `pr_merged` on a new `coordinator_github`
channel. That belongs to a follow-up change.
