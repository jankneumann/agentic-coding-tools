import { Board } from "./components/Board";
import { useCoordinator } from "./hooks/useCoordinator";

const API_URL = import.meta.env["VITE_COORDINATOR_URL"] ?? "http://localhost:8081";
const API_KEY = import.meta.env["VITE_COORDINATOR_API_KEY"] ?? "";
const CHANGE_IDS = (import.meta.env["VITE_CHANGE_IDS"] ?? "")
  .split(",")
  .map((s: string) => s.trim())
  .filter(Boolean);

export default function App() {
  const { issues, loading, error } = useCoordinator({
    apiUrl: API_URL,
    apiKey: API_KEY,
    changeIds: CHANGE_IDS,
  });

  if (loading) {
    return <div role="status">Loading board…</div>;
  }

  if (error) {
    return <div role="alert">Error: {error}</div>;
  }

  return <Board issues={issues} />;
}
