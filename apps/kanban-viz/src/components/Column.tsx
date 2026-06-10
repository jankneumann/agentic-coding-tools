import type { IssueCard, ColumnId } from "../lib/coordinator-types";
import { Card } from "./Card";
import type { AgentActivity } from "./VendorSwimlanes";

interface Props {
  columnId: ColumnId;
  title: string;
  issues: IssueCard[];
  /** Per-issue agent activity (IMPL_REVIEW F2). Passed through to each Card. */
  agentsByIssueId?: Map<string, AgentActivity[]>;
  /** Coordinator API base URL (task 6.8 — Mark Ready button on cards). */
  apiUrl?: string;
  /** Bearer-style API key (task 6.8). */
  apiKey?: string;
  /** Audit emitter (task 6.8). */
  onAuditEmit?: (eventData: Record<string, unknown>) => void;
}

const EMPTY_STATE_COPY: Record<ColumnId, string> = {
  backlog: "No pending work.",
  "in-flight": "No agents are working right now.",
  done: "No completed tasks in the last 24 hours.",
};

export function Column({
  columnId,
  title,
  issues,
  agentsByIssueId,
  apiUrl,
  apiKey,
  onAuditEmit,
}: Props) {
  return (
    <div
      data-testid={`column-${columnId}`}
      style={{
        flex: "1 1 0",
        minWidth: 220,
        padding: "0 8px",
      }}
    >
      <h2
        data-testid={`column-title-${columnId}`}
        style={{ fontSize: 14, textTransform: "uppercase", marginBottom: 12 }}
      >
        {title}
      </h2>
      {issues.length === 0 ? (
        <div
          data-testid={`column-empty-state-${columnId}`}
          style={{ color: "#999", fontStyle: "italic", fontSize: 13 }}
        >
          {EMPTY_STATE_COPY[columnId]}
        </div>
      ) : (
        issues.map((issue) => (
          <Card
            key={issue.id}
            issue={issue}
            agents={agentsByIssueId?.get(issue.id) ?? []}
            apiUrl={apiUrl}
            apiKey={apiKey}
            onAuditEmit={onAuditEmit}
          />
        ))
      )}
    </div>
  );
}
