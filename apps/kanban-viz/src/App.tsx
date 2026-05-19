import { useCallback } from "react";
import { Board } from "./components/Board";
import { SyncPointBanner } from "./components/SyncPointBanner";
import { useCoordinator } from "./hooks/useCoordinator";

const API_URL = import.meta.env["VITE_COORDINATOR_URL"] ?? "http://localhost:8081";
const API_KEY = import.meta.env["VITE_COORDINATOR_API_KEY"] ?? "";
const CHANGE_IDS = (import.meta.env["VITE_CHANGE_IDS"] ?? "")
  .split(",")
  .map((s: string) => s.trim())
  .filter(Boolean);

export default function App() {
  const { issues, loading, error, agentsByIssueId } = useCoordinator({
    apiUrl: API_URL,
    apiKey: API_KEY,
    changeIds: CHANGE_IDS,
  });

  // IMPL_REVIEW R2-id=16 (high observability): App.tsx mounts the banner but
  // the prior commit didn't thread onAuditEmit, so kick actions emitted audit
  // events to nowhere. Wire to POST /kanban-viz/audit so destructive-write
  // kicks land on disk per the proposal §3 audit contract.
  const emitAudit = useCallback(
    (eventData: Record<string, unknown>) => {
      const runId =
        eventData["run_id"] ??
        `kick-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      void fetch(`${API_URL}/kanban-viz/audit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${API_KEY}`,
        },
        body: JSON.stringify({ run_id: runId, event: eventData }),
      }).catch(() => {
        // Audit-emission failure is non-blocking — the operator's primary
        // signal is the kick result itself. Log to console for visibility.
        // eslint-disable-next-line no-console
        console.warn("Failed to persist kick audit event", eventData);
      });
    },
    [],
  );

  return (
    <div data-testid="kanban-app">
      {/*
       * IMPL_REVIEW F1 (critical, claude+codex confirmed): SyncPointBanner is
       * MVP surface #1 per proposal §3. Render above the Board so the
       * sync-point gate is always visible (it's not gated on Board loading).
       * Banner is independent of the board's loading/error state.
       */}
      <SyncPointBanner
        apiUrl={API_URL}
        apiKey={API_KEY}
        onAuditEmit={emitAudit}
      />
      {loading ? (
        <div role="status" data-testid="app-loading">
          Loading board…
        </div>
      ) : error ? (
        <div role="alert" data-testid="app-error">
          Error: {error}
        </div>
      ) : (
        <Board issues={issues} agentsByIssueId={agentsByIssueId} />
      )}
    </div>
  );
}
