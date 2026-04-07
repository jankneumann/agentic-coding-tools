# Session Log — replace-beads-with-builtin-tracker

---

## Phase: Plan (2026-04-06)

**Agent**: claude-opus-4-6 | **Session**: plan-feature

### Decisions
1. **Coordinator-only (no offline fallback)** — Offline issue tracking is a subset of what OpenSpec tasks.md already provides. The coordinator is always running during meaningful work.
2. **Full beads replacement** — Remove all bd CLI references, hooks, skills, and .beads/ directory.
3. **Extend work_queue (Approach A)** — Add labels, parent_id, issue_type, assignee, comments to existing table rather than creating a separate issues table.
4. **IssueService as separate class (D1)** — Delegates to DB directly, not through WorkQueueService, to avoid inheriting agent-coordination semantics (policy checks, guardrails) inappropriate for issue CRUD.
5. **task_type='issue' discrimination (D5)** — Issues set task_type='issue' so get_work won't accidentally claim them.

### Alternatives Considered
- **Offline fallback (git-native JSONL)**: rejected because coordination features require the server, and tasks.md covers offline needs
- **Separate issues table (Approach C)**: rejected because user preferred extending work_queue, and it duplicates dependency/priority/status concepts
- **Service layer wrapper (Approach B)**: viable but adds indirection for ultimately the same table operations

### Trade-offs
- Accepted work_queue column bloat over data model purity — simplicity of one table outweighs cosmetic concern
- Accepted coordinator dependency (no offline) over universal portability — all repos already use the coordinator

### Open Questions
- [ ] Should issue_search use PostgreSQL full-text search (tsvector) or simple ILIKE? (Implementation decision)
- [ ] Should the beads plugin skills be removed immediately or kept as deprecated aliases?

### Context
Planning session to replace the beads (bd CLI) issue tracker with built-in coordinator functionality. The coordinator's work_queue already provided ~70% of beads features. By extending it with labels, epics, comments, and hierarchy, we get a fully integrated issue tracker that works across all repos using the coordinator, without requiring a separate Go binary installation.
