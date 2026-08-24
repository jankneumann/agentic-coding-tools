# Deferred Tasks — add-merge-plan-orchestration

The approved change implements Phase 1 only. These Phase-2 tasks remain intentionally
deferred to a follow-on OpenSpec change because they require coordinator persistence,
event, cross-host isolation, and authorization contracts beyond the file-tier delivery.

- [ ] P2.1 Coordinator system-of-record: model plan nodes as `work_queue`
  (`task_type=pr_merge`, `blockedBy`) plus `merge_queue` serialisation (D3, D5).
- [ ] P2.2 Event-driven re-validation over `event_bus` LISTEN/NOTIFY (D4).
- [ ] P2.3 Cross-host dispatch of per-PR executors with worktree isolation (D5).
- [ ] P2.4 Auth scoping for cloud-SDK plan endpoints (D10).
- [ ] P2.5 Automated comment-addressing via worktree-isolated sub-agents (D8).
