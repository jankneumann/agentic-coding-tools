import type { IssueCard } from "../lib/coordinator-types";

/** @deprecated Use IssueCard. Kept as alias to avoid renaming every import. */
export type Issue = IssueCard;

export const pendingIssue: IssueCard = {
  kind: "issue",
  id: "00000000-0000-0000-0000-000000000001",
  title: "Implement login",
  body: null,
  status: "pending",
  priority: 1,
  labels: ["change:abc"],
  assignee: null,
  claimed_by: null,
  claimed_at: null,
  completed_at: null,
  created_at: new Date(Date.now() - 3600 * 1000).toISOString(),
  updated_at: null,
  change_id: "abc",
  task_key: "1.1",
};

export const claimedIssue: IssueCard = {
  kind: "issue",
  id: "00000000-0000-0000-0000-000000000002",
  title: "Add database migrations",
  body: null,
  status: "claimed",
  priority: 2,
  labels: ["change:abc"],
  assignee: "agent-claude",
  claimed_by: "agent-claude",
  claimed_at: new Date(Date.now() - 1800 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date(Date.now() - 7200 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 1800 * 1000).toISOString(),
  change_id: "abc",
  task_key: "1.2",
};

export const runningIssue: IssueCard = {
  kind: "issue",
  id: "00000000-0000-0000-0000-000000000003",
  title: "Write unit tests",
  body: null,
  status: "running",
  priority: 3,
  labels: ["change:abc"],
  assignee: "agent-codex",
  claimed_by: "agent-codex",
  claimed_at: new Date(Date.now() - 900 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date(Date.now() - 3600 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 900 * 1000).toISOString(),
  change_id: "abc",
  task_key: "2.1",
};

export const completedRecentIssue: IssueCard = {
  kind: "issue",
  id: "00000000-0000-0000-0000-000000000004",
  title: "Deploy to staging",
  body: null,
  status: "completed",
  priority: 1,
  labels: ["change:abc"],
  assignee: null,
  claimed_by: null,
  claimed_at: null,
  // IMPL_REVIEW R2-id=15: Done column 24h filter must use completed_at.
  completed_at: new Date(Date.now() - 600 * 1000).toISOString(),
  created_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 600 * 1000).toISOString(),
  change_id: "abc",
  task_key: "1.3",
};

export const completedOldIssue: IssueCard = {
  kind: "issue",
  id: "00000000-0000-0000-0000-000000000005",
  title: "Old deployment",
  body: null,
  status: "completed",
  priority: 1,
  labels: ["change:old"],
  assignee: null,
  claimed_by: null,
  claimed_at: null,
  // Older than 24h — should NOT appear in Done column.
  completed_at: new Date(Date.now() - 25 * 3600 * 1000).toISOString(),
  created_at: new Date(Date.now() - 48 * 3600 * 1000).toISOString(),
  updated_at: new Date(Date.now() - 25 * 3600 * 1000).toISOString(),
  change_id: "old",
  task_key: "9.1",
};

export const blockedIssue: IssueCard = {
  kind: "issue",
  id: "00000000-0000-0000-0000-000000000006",
  title: "Blocked task",
  body: null,
  status: "blocked",
  priority: 4,
  labels: ["change:abc"],
  assignee: null,
  claimed_by: null,
  claimed_at: null,
  completed_at: null,
  created_at: new Date(Date.now() - 5000 * 1000).toISOString(),
  updated_at: null,
  change_id: "abc",
  task_key: "3.1",
};
