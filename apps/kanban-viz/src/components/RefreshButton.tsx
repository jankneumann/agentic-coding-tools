/**
 * RefreshButton — spinner-stateful button that triggers refetch of all three
 * card sources (via useBoardCards.refresh()).
 *
 * Shows last-refreshed timestamp. Surfaces per-row error chips when individual
 * sources fail without blocking others.
 */
import { useState } from "react";

type RefreshState = "idle" | "loading" | "error";

type RowKey = "issues" | "prs" | "proposals";

interface Props {
  /** Called when the button is clicked. Should trigger a parallel refetch. */
  onRefresh: () => Promise<void>;
  /**
   * Optional per-row error strings (from useBoardCards byRow.x.error).
   * Surfaces as small chips below the button.
   */
  rowErrors?: Partial<Record<RowKey, string | null>>;
}

const ROW_LABELS: Record<RowKey, string> = {
  issues: "Issues",
  prs: "PRs",
  proposals: "Proposals",
};

export function RefreshButton({ onRefresh, rowErrors }: Props) {
  const [state, setState] = useState<RefreshState>("idle");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  const handleClick = async () => {
    setState("loading");
    try {
      await onRefresh();
      setState("idle");
      setLastRefreshedAt(new Date());
    } catch {
      setState("error");
    }
  };

  const isLoading = state === "loading";

  const activeRowErrors = rowErrors
    ? (Object.entries(rowErrors) as [RowKey, string | null][]).filter(
        ([, err]) => err != null,
      )
    : [];

  return (
    <div style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button
          type="button"
          data-testid="refresh-button"
          data-state={state}
          disabled={isLoading}
          onClick={() => void handleClick()}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 12px",
            fontSize: 13,
            fontWeight: 600,
            background: state === "error" ? "#de350b" : "#0052cc",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: isLoading ? "wait" : "pointer",
            opacity: isLoading ? 0.7 : 1,
          }}
          aria-label={
            isLoading
              ? "Refreshing…"
              : state === "error"
                ? "Refresh failed — click to retry"
                : "Refresh all sources"
          }
        >
          {isLoading ? (
            <>
              <span aria-hidden style={{ display: "inline-block", animation: "spin 0.8s linear infinite" }}>⟳</span>
              Refreshing…
            </>
          ) : state === "error" ? (
            "Retry Refresh"
          ) : (
            "↻ Refresh"
          )}
        </button>

        {lastRefreshedAt != null && (
          <span
            data-testid="last-refreshed"
            style={{ fontSize: 11, color: "#888" }}
            title={lastRefreshedAt.toISOString()}
          >
            Updated {formatRelative(lastRefreshedAt)}
          </span>
        )}
      </div>

      {/* Per-row error chips */}
      {activeRowErrors.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {activeRowErrors.map(([row, err]) => (
            <span
              key={row}
              data-testid={`row-error-${row}`}
              title={err ?? undefined}
              style={{
                fontSize: 10,
                padding: "2px 6px",
                background: "#fff3cd",
                color: "#856404",
                border: "1px solid #ffc107",
                borderRadius: 10,
                fontWeight: 600,
              }}
            >
              {ROW_LABELS[row]} unavailable
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function formatRelative(date: Date): string {
  const diffMs = Date.now() - date.getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}
