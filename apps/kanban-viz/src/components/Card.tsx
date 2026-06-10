import { useState } from "react";
import type { IssueCard } from "../lib/coordinator-types";
import { classify } from "../lib/reversibility";
import { VendorSwimlanes } from "./VendorSwimlanes";
import type { AgentActivity } from "./VendorSwimlanes";

interface Props {
  issue: IssueCard;
  /**
   * Per-issue agent activity (IMPL_REVIEW F2). Rendered as VendorSwimlanes
   * when the issue is in-flight (status ∈ {claimed, running}) and at least
   * one agent is provided. Defaults to empty (no swimlanes).
   */
  agents?: AgentActivity[];
  /**
   * Coordinator API base URL for the drag-to-Ready PATCH (task 6.8). If
   * omitted, the Ready button is hidden.
   */
  apiUrl?: string;
  /** Bearer-style API key for the Ready PATCH (task 6.8). */
  apiKey?: string;
  /** Schema-valid audit emitter (App.tsx wiring). */
  onAuditEmit?: (eventData: Record<string, unknown>) => void;
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

export function Card({
  issue,
  agents = [],
  apiUrl,
  apiKey,
  onAuditEmit,
}: Props) {
  const assignee = issue.claimed_by ?? issue.assignee;
  const ts = issue.claimed_at ?? issue.created_at;
  const isInFlight = issue.status === "claimed" || issue.status === "running";
  const isCompleted = issue.status === "completed" || issue.status === "failed";
  const alreadyReady = issue.labels.includes("pending-approval");
  // Ready button is shown only for in-flight cards (the typical workflow:
  // "I'm running, mark me for review when I'm done") and only when the
  // coordinator API is reachable. It's hidden once the label is already
  // present (idempotent UX — a second click would be a no-op anyway).
  const canMarkReady =
    Boolean(apiUrl && apiKey) && isInFlight && !alreadyReady;

  const [readyStatus, setReadyStatus] = useState<
    "idle" | "submitting" | "marked" | "error"
  >("idle");

  const handleMarkReady = async () => {
    if (!apiUrl || !apiKey) return;
    setReadyStatus("submitting");
    const klass = classify("drag-to-ready");
    try {
      const res = await fetch(`${apiUrl}/issues/${issue.id}/labels`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({ add: ["pending-approval"], remove: [] }),
      });
      if (!res.ok) {
        throw new Error(`PATCH /issues/${issue.id}/labels: ${res.status}`);
      }
      onAuditEmit?.({
        action: "drag-to-ready",
        class: klass,
        outcome: "confirmed",
        args: { issue_id: issue.id, added_label: "pending-approval" },
      });
      setReadyStatus("marked");
    } catch (e) {
      onAuditEmit?.({
        action: "drag-to-ready",
        class: klass,
        outcome: "failed",
        args: { issue_id: issue.id, failure_reason: String(e) },
      });
      setReadyStatus("error");
    }
  };

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
      {/*
       * IMPL_REVIEW F2 (critical, claude+codex confirmed): render
       * VendorSwimlanes for in-flight cards or a consensus indicator for
       * completed cards. Previously the component existed with tests but was
       * unreachable from the rendered Card — MVP surface #2 per proposal §3.
       */}
      {(isInFlight || isCompleted) && agents.length > 0 && (
        <VendorSwimlanes agents={agents} completed={isCompleted} />
      )}
      {/*
       * Task 6.8 (drag-to-Ready): in-flight cards expose a "Mark Ready"
       * action that adds the `pending-approval` label and emits a
       * reversible-write audit row. Implemented as a button rather than
       * HTML5 drag-and-drop for accessibility + testability; the audit
       * action key remains `drag-to-ready` per the schema enum so the
       * resulting artifacts match the spec.
       */}
      {canMarkReady && (
        <button
          type="button"
          data-testid={`card-ready-${issue.id}`}
          disabled={readyStatus === "submitting"}
          onClick={() => void handleMarkReady()}
          style={{
            marginTop: 6,
            fontSize: 11,
            padding: "2px 8px",
            background: readyStatus === "marked" ? "#22a06b" : "#0052cc",
            color: "#fff",
            border: "none",
            borderRadius: 3,
            cursor: readyStatus === "submitting" ? "wait" : "pointer",
          }}
        >
          {readyStatus === "submitting"
            ? "Marking…"
            : readyStatus === "marked"
              ? "Marked Ready ✓"
              : readyStatus === "error"
                ? "Retry Mark Ready"
                : "Mark Ready"}
        </button>
      )}
      {alreadyReady && (
        <div
          data-testid={`card-ready-badge-${issue.id}`}
          style={{
            marginTop: 6,
            display: "inline-block",
            fontSize: 10,
            padding: "1px 6px",
            background: "#deebff",
            color: "#0747a6",
            borderRadius: 3,
            fontWeight: 600,
          }}
        >
          pending-approval
        </div>
      )}
    </div>
  );
}
