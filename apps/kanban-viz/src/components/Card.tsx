import type { Issue } from "../lib/coordinator-types";

interface Props {
  issue: Issue;
}

/** Format a relative timestamp from an ISO string. */
function relativeTime(isoStr: string | null): string {
  if (!isoStr) return "";
  const now = Date.now();
  const ts = new Date(isoStr).getTime();
  const diffMs = now - ts;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return `${Math.floor(diffH / 24)}d ago`;
}

export function Card({ issue }: Props) {
  const assignee = issue.claimed_by ?? issue.assignee;
  const ts = issue.claimed_at ?? issue.created_at;

  return (
    <div
      data-testid="kanban-card"
      data-issue-id={issue.id}
      data-status={issue.status}
      style={{
        border: "1px solid #ccc",
        borderRadius: 4,
        padding: "8px 12px",
        marginBottom: 8,
        background: "#fff",
      }}
    >
      <div data-testid="card-title" style={{ fontWeight: 600, marginBottom: 4 }}>
        {issue.title}
      </div>
      {issue.change_id && (
        <div
          data-testid="card-change-id"
          style={{ fontSize: 11, color: "#888", marginBottom: 2 }}
        >
          {issue.change_id}
        </div>
      )}
      {assignee && (
        <div
          data-testid="card-assignee"
          style={{ fontSize: 12, color: "#555", marginBottom: 2 }}
        >
          {assignee}
        </div>
      )}
      {ts && (
        <div
          data-testid="card-timestamp"
          title={ts}
          style={{ fontSize: 11, color: "#aaa" }}
        >
          {relativeTime(ts)}
        </div>
      )}
    </div>
  );
}
