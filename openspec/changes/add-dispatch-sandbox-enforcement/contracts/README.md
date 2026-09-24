# dg-07 contracts

- `dispatch-execution-context.schema.json` binds enforcement to the exact routed or fallback
  decision consumed at launch.
- `network-policy-export.schema.json` is the coordinator-to-renderer default-deny snapshot.
- `sandbox-execution-event.schema.json` records requested versus applied enforcement without
  prompt or secret material.
- `openapi.yaml` exposes only the exact-agent policy read and narrow durable event write.

The schemas use dg-05's landed `none | worktree | sandbox` vocabulary. They deliberately do not
adopt the downstream, unlanded `container` proposal.
