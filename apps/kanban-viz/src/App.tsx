import { useCallback, useState } from "react";
import { SaveViewButton } from "./components/SaveViewButton";
import { SourceSwimlanes } from "./components/SourceSwimlanes";
import { SyncPointBanner } from "./components/SyncPointBanner";
import { useBoardCards } from "./hooks/useBoardCards";

const API_URL = import.meta.env["VITE_COORDINATOR_URL"] ?? "http://localhost:8081";
const API_KEY = import.meta.env["VITE_COORDINATOR_API_KEY"] ?? "";
const CHANGE_IDS = (import.meta.env["VITE_CHANGE_IDS"] ?? "")
  .split(",")
  .map((s: string) => s.trim())
  .filter(Boolean);

export default function App() {
  // R1-104 fix: hiddenRepos state lives at App level so it can be threaded
  // into BOTH useBoardCards (for filtering BEFORE clustering) AND
  // SourceSwimlanes (for the HiddenReposToggle UI gating). Local state
  // only for v1; saved-view persistence is a follow-up.
  const [hiddenRepos, setHiddenRepos] = useState<readonly string[]>([]);

  // Three-source board (PR #211 + multi-repo extension): Issues, PRs, Proposals
  // fetched in parallel via useBoardCards. SourceSwimlanes renders the
  // three-row layout with cluster badges, repo badges, and the partial-result
  // chip when /openspec/proposals returns _warnings.
  const { cards, annotated, loading, proposalsWarnings } = useBoardCards({
    apiUrl: API_URL,
    apiKey: API_KEY,
    changeIds: CHANGE_IDS,
    hiddenRepos,
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
       * MVP surface #1 per proposal §3. Render above the board so the
       * sync-point gate is always visible (it's not gated on board loading).
       * Banner is independent of the board's loading/error state.
       */}
      <SyncPointBanner
        apiUrl={API_URL}
        apiKey={API_KEY}
        onAuditEmit={emitAudit}
      />
      {/* Toolbar — task 6.7 SaveViewButton (reduced scope: save-only). */}
      <div
        data-testid="app-toolbar"
        style={{
          display: "flex",
          justifyContent: "flex-end",
          padding: "6px 16px",
          borderBottom: "1px solid #eee",
          background: "#fafbfc",
        }}
      >
        <SaveViewButton
          apiUrl={API_URL}
          apiKey={API_KEY}
          currentFilters={{ change_ids: CHANGE_IDS }}
          onAuditEmit={emitAudit}
        />
      </div>
      {loading ? (
        <div role="status" data-testid="app-loading">
          Loading board…
        </div>
      ) : (
        // Wrapper preserves the data-testid="kanban-board" anchor that
        // App.test.tsx DOM-ordering assertions reference. SourceSwimlanes
        // is the new three-row layout from PR #211 + multi-repo extension.
        <div data-testid="kanban-board">
          <SourceSwimlanes
            cards={cards}
            annotatedCards={annotated}
            proposalsWarnings={proposalsWarnings}
            hiddenRepos={hiddenRepos}
            onHiddenReposChange={setHiddenRepos}
          />
        </div>
      )}
    </div>
  );
}
