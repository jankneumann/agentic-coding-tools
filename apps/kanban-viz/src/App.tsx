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

  return (
    <div data-testid="kanban-app">
      {/*
       * IMPL_REVIEW F1 (critical, claude+codex confirmed): SyncPointBanner is
       * MVP surface #1 per proposal §3. Render above the Board so the
       * sync-point gate is always visible (it's not gated on Board loading).
       * Banner is independent of the board's loading/error state.
       */}
      <SyncPointBanner apiUrl={API_URL} apiKey={API_KEY} />
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
