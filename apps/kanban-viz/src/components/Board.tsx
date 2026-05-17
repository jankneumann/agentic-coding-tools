import type { Issue, ColumnId } from "../lib/coordinator-types";
import { statusToColumn } from "../lib/coordinator-types";
import { Column } from "./Column";

interface Props {
  issues: Issue[];
}

const COLUMNS: Array<{ id: ColumnId; title: string }> = [
  { id: "backlog", title: "Backlog" },
  { id: "in-flight", title: "In Flight" },
  { id: "done", title: "Done" },
];

export function Board({ issues }: Props) {
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
      // Only show completed within 24h
      const updatedAt = issue.updated_at ?? issue.created_at;
      if (now - new Date(updatedAt).getTime() <= MS_24H) {
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
        />
      ))}
    </div>
  );
}
