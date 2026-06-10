/**
 * PROriginFilter — chip multi-select for filtering PR cards by origin.
 *
 * Six origins matching the contract PROrigin enum:
 *   openspec / codex / jules / dependabot / renovate / manual
 *
 * Default: all selected.
 * Selection state persists via:
 *   1. localStorage["kanban-viz:pr-origins"] (default view, no active saved view)
 *   2. saved-view pr_origins field (via onSelectionChange callback)
 *
 * Filtering is client-side — no network request on chip click.
 */
import { useEffect, useState } from "react";
import type { PROrigin } from "../lib/coordinator-types";

export const ALL_PR_ORIGINS: PROrigin[] = [
  "openspec",
  "codex",
  "jules",
  "dependabot",
  "renovate",
  "manual",
];

const STORAGE_KEY = "kanban-viz:pr-origins";

function loadFromStorage(): PROrigin[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (
      Array.isArray(parsed) &&
      parsed.every((v) => ALL_PR_ORIGINS.includes(v as PROrigin))
    ) {
      return parsed as PROrigin[];
    }
  } catch {
    // ignore
  }
  return null;
}

function saveToStorage(origins: PROrigin[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(origins));
  } catch {
    // ignore
  }
}

interface Props {
  /** Current selection (controlled). If not provided, component is self-managed. */
  value?: PROrigin[];
  /** Called when the selection changes. */
  onSelectionChange?: (selected: PROrigin[]) => void;
}

const ORIGIN_LABELS: Record<PROrigin, string> = {
  openspec: "OpenSpec",
  codex: "Codex",
  jules: "Jules",
  dependabot: "Dependabot",
  renovate: "Renovate",
  manual: "Manual",
};

export function PROriginFilter({ value, onSelectionChange }: Props) {
  const [internalSelected, setInternalSelected] = useState<PROrigin[]>(() => {
    // If value provided, use it; else load from localStorage or default to all
    if (value !== undefined) return value;
    return loadFromStorage() ?? [...ALL_PR_ORIGINS];
  });

  // Sync external value prop changes to internal state
  useEffect(() => {
    if (value !== undefined) {
      setInternalSelected(value);
    }
  }, [value]);

  const selected = value !== undefined ? value : internalSelected;

  const toggle = (origin: PROrigin) => {
    const next = selected.includes(origin)
      ? selected.filter((o) => o !== origin)
      : [...selected, origin];

    if (value === undefined) {
      setInternalSelected(next);
      saveToStorage(next);
    }
    onSelectionChange?.(next);
  };

  return (
    <div
      data-testid="pr-origin-filter"
      role="group"
      aria-label="Filter pull requests by origin"
      style={{ display: "flex", gap: 4, flexWrap: "wrap", padding: "4px 0" }}
    >
      {ALL_PR_ORIGINS.map((origin) => {
        const isSelected = selected.includes(origin);
        return (
          <button
            key={origin}
            type="button"
            data-testid={`origin-chip-${origin}`}
            aria-pressed={isSelected}
            onClick={() => { toggle(origin); }}
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: 10,
              border: "1px solid",
              cursor: "pointer",
              background: isSelected ? "#deebff" : "#f4f5f7",
              color: isSelected ? "#0052cc" : "#666",
              borderColor: isSelected ? "#4c9aff" : "#e0e0e0",
            }}
          >
            {ORIGIN_LABELS[origin]}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Filter a PRCard array to only include cards whose origin is in selectedOrigins.
 * Pure function — no side effects.
 */
export function filterByOrigin<T extends { origin: PROrigin }>(
  cards: T[],
  selectedOrigins: PROrigin[],
): T[] {
  const originSet = new Set(selectedOrigins);
  return cards.filter((card) => originSet.has(card.origin));
}
