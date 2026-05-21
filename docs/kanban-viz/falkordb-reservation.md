# FalkorDB Schema Reservation — Kanban Visualization

This document reserves FalkorDB node labels and edge types for the Kanban
visualization feature. No FalkorDB implementation is included in this change
(`add-coordinator-kanban-viz`). These reservations let codeviz Phase 0
ingestion adopt the labels without a rename pass.

See `openspec/changes/add-coordinator-kanban-viz/contracts/README.md` for the
full reservation table and rationale (design decision D6).

## Reserved Node Labels

| Label | Source row | Codeviz Phase 0 ownership |
|---|---|---|
| `WorkPackage` | `work_queue` | codeviz |
| `Agent` | `agent_profiles` | codeviz |
| `Vendor` | enum {claude, codex, gemini, chatgpt-pro} | codeviz |
| `Worktree` | `.git-worktrees/.registry.json` | codeviz |
| `Lock` | `file_locks` | codeviz |
| `SyncPoint` | enum {cleanup-feature, merge-pull-requests, update-specs} | codeviz |
| `AuditEvent` | `audit_log` | codeviz |

## Reserved Edge Types

| Edge | Source | Codeviz Phase 0 ownership |
|---|---|---|
| `CLAIMED_BY` | WorkPackage → Agent | codeviz |
| `BLOCKED_ON` | WorkPackage → WorkPackage | codeviz |
| `LOCKS_FILE` | Agent → File (codeviz File node) | codeviz |
| `WORKING_IN` | Agent → Worktree | codeviz |
| `RAN_BY` | AuditEvent → Agent | codeviz |
| `BLOCKS_SYNCPOINT` | Agent → SyncPoint | codeviz |
| `IMPLEMENTS_TASK` | WorkPackage → Symbol (codeviz Symbol node) | codeviz |

## Notes

- `agent_profiles` in the table above refers to the profile template rows, not
  per-agent rows. Per-agent identity lives in `agent_sessions`.
- The Kanban does not write to FalkorDB in v1; it reads from Postgres only.
- When codeviz Phase 0 lands FalkorDB ingestion, it should adopt these labels
  without changes to the Kanban code.
