/**
 * ClusterBadge — renders a cross-row cluster indicator on cards that share
 * a change_id with other cards.
 *
 * Design:
 * - Non-collapsing: cards remain in their rows. The badge surfaces cluster size.
 * - Click highlights all sibling cards (same change_id) for ≥ 1.5s.
 * - Cards with change_id=null do NOT render a badge.
 * - aria-label describes the cluster for screen readers.
 *
 * Usage: render inside a card that has cluster_count > 1.
 * The parent must call onHighlight(change_id) when the badge is clicked —
 * or pass the highlight state in via highlightedChangeId.
 */
import { useEffect, useRef, useState } from "react";

// Global highlight state shared across all ClusterBadge instances.
// A simple event-emitter pattern so we don't need React context for this.
type HighlightListener = (changeId: string | null) => void;
const highlightListeners = new Set<HighlightListener>();

function emitHighlight(changeId: string | null): void {
  for (const listener of highlightListeners) {
    listener(changeId);
  }
}

/**
 * Hook: returns whether the given change_id is currently highlighted.
 * Registers the badge as a listener so it re-renders when global highlight changes.
 */
function useHighlightState(changeId: string | null): boolean {
  const [highlighted, setHighlighted] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const listener: HighlightListener = (activeChangeId) => {
      if (changeId == null) return;
      if (activeChangeId === changeId) {
        setHighlighted(true);
        if (timerRef.current !== null) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
          setHighlighted(false);
          timerRef.current = null;
        }, 1500);
      } else {
        setHighlighted(false);
        if (timerRef.current !== null) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
      }
    };

    highlightListeners.add(listener);
    return () => {
      highlightListeners.delete(listener);
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, [changeId]);

  return highlighted;
}

interface Props {
  /** The change_id this card belongs to. Null → badge not rendered. */
  changeId: string | null;
  /** Number of cards sharing this change_id (including this card). */
  clusterCount: number | null;
}

export function ClusterBadge({ changeId, clusterCount }: Props) {
  // Don't render if no cluster
  if (changeId == null || clusterCount == null || clusterCount <= 1) {
    return null;
  }

  return <ClusterBadgeInner changeId={changeId} clusterCount={clusterCount} />;
}

function ClusterBadgeInner({
  changeId,
  clusterCount,
}: {
  changeId: string;
  clusterCount: number;
}) {
  const highlighted = useHighlightState(changeId);

  const handleClick = () => {
    emitHighlight(changeId);
  };

  const ariaLabel = `Part of cluster ${changeId}; ${clusterCount} related cards across rows`;

  return (
    <button
      type="button"
      data-testid={`cluster-badge-${changeId}`}
      aria-label={ariaLabel}
      title={`${changeId} — ${clusterCount} related cards`}
      onClick={handleClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        fontSize: 10,
        fontWeight: 700,
        padding: "1px 6px",
        borderRadius: 10,
        border: highlighted ? "2px solid #ff7043" : "1px solid #6554c0",
        background: highlighted ? "#fff3e0" : "#f3f0ff",
        color: highlighted ? "#bf360c" : "#6554c0",
        cursor: "pointer",
        outline: highlighted ? "2px solid #ff7043" : "none",
        outlineOffset: 1,
        transition: "border-color 0.15s, background 0.15s",
      }}
    >
      <span aria-hidden>⬡</span>
      {clusterCount}
    </button>
  );
}

/**
 * Exported for use in card containers: wraps children with highlight border.
 * When a ClusterBadge is clicked for the same change_id, this border lights up.
 */
export function ClusterHighlightWrapper({
  changeId,
  children,
}: {
  changeId: string | null;
  children: React.ReactNode;
}) {
  const highlighted = useHighlightState(changeId);

  return (
    <div
      data-testid={changeId ? `cluster-highlight-${changeId}` : undefined}
      style={{
        outline: highlighted ? "2px solid #ff7043" : "none",
        outlineOffset: 1,
        borderRadius: 4,
        transition: "outline-color 0.15s",
      }}
    >
      {children}
    </div>
  );
}

/**
 * Trigger highlight programmatically (for testing / external control).
 */
export { emitHighlight };
