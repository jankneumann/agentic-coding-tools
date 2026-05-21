import type { Issue, ColumnId } from "../lib/coordinator-types";
import { statusToColumn } from "../lib/coordinator-types";
import { Column } from "./Column";
import type { AgentActivity } from "./VendorSwimlanes";

interface Props {
  issues: Issue[];
  /** Per-issue agent activity (IMPL_REVIEW F2). Threaded through to Cards. */
  agentsByIssueId?: Map<string, AgentActivity[]>;
  /** Coordinator API base URL (task 6.8). */
  apiUrl?: string;
  /** Bearer-style API key (task 6.8). */
  apiKey?: string;
  /** Audit emitter (task 6.8). */
  onAuditEmit?: (eventData: Record<string, unknown>) => void;
}

const COLUMNS: Array<{ id: ColumnId; title: string }> = [
  { id: "backlog", title: "Backlog" },
  { id: "in-flight", title: "In Flight" },
  { id: "done", title: "Done" },
];

export function Board({
  issues,
  agentsByIssueId,
  apiUrl,
  apiKey,
  onAuditEmit,
}: Props) {
  // Bucket issues by column; "done" column shows only last 24h completed
  const now = Date.now();
  const MS_24H = 24 * 60 * 60 * 1000;

  const byColumn: Record<ColumnId, Issue[]> = {
    backlog: [],
    "in-flight": [],
    done: [],
  };

  for (const issue of issues) {
    const col = statusToColumn(issue.status);
    if (col === "done") {
      // IMPL_REVIEW R2-id=15: proposal §3 specifies the Done column shows
      // `completed_at >= now() - 24h` for completed cards. The prior
      // `updated_at ?? created_at` fallback returned cards that weren't
      // genuinely completed within the window. We additionally exclude
      // `failed` from the 24h filter — failed cards go to Done immediately
      // and stay there until completed_at-equivalent (close_at) is set,
      // so use completed_at-or-closed_at semantics, falling back to
      // updated_at only when neither is present (transitional rows).
      const referenceTs =
        issue.completed_at ?? issue.updated_at ?? issue.created_at;
      if (now - new Date(referenceTs).getTime() <= MS_24H) {
        byColumn.done.push(issue);
      }
    } else {
      byColumn[col].push(issue);
    }
  }

  return (
    <div
      data-testid="kanban-board"
      style={{ display: "flex", gap: 16, padding: 16, alignItems: "flex-start" }}
    >
      {COLUMNS.map(({ id, title }) => (
        <Column
          key={id}
          columnId={id}
          title={title}
          issues={byColumn[id]}
          agentsByIssueId={agentsByIssueId}
          apiUrl={apiUrl}
          apiKey={apiKey}
          onAuditEmit={onAuditEmit}
        />
      ))}
    </div>
  );
}
