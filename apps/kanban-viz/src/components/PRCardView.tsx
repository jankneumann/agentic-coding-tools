/**
 * PRCardView — renders a PRCard with review-findings projection.
 *
 * Review summary visual treatment:
 * - changes_requested → warning chrome (orange/amber)
 * - approved          → success chrome (green)
 * - commented / none  → neutral chrome (gray)
 *
 * Uses existing color tokens. No new design tokens introduced.
 */
import type { PRCard } from "../lib/coordinator-types";
import { ClusterBadge, ClusterHighlightWrapper } from "./ClusterBadge";
import type { AnnotatedCard } from "../hooks/useBoardCards";
import { RepoBadge } from "./RepoBadge";

interface Props {
  card: PRCard & Partial<Pick<AnnotatedCard, "cluster_count">>;
}

/** Relative time from ISO string. */
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

// Color tokens for review states (using existing design system palette)
const REVIEW_STATE_STYLES = {
  changes_requested: {
    background: "#fff3cd",
    color: "#856404",
    borderColor: "#ffc107",
    icon: "⚠",
    label: "Changes requested",
  },
  approved: {
    background: "#d4edda",
    color: "#155724",
    borderColor: "#28a745",
    icon: "✓",
    label: "Approved",
  },
  commented: {
    background: "#f8f9fa",
    color: "#6c757d",
    borderColor: "#dee2e6",
    icon: "○",
    label: "Commented",
  },
  none: {
    background: "#f8f9fa",
    color: "#6c757d",
    borderColor: "#dee2e6",
    icon: "·",
    label: "No review",
  },
} as const;

// PR status badge colors
const STATUS_STYLES: Record<PRCard["status"], { bg: string; color: string }> = {
  draft: { bg: "#f4f5f7", color: "#666" },
  open: { bg: "#deebff", color: "#0052cc" },
  review: { bg: "#e3fcef", color: "#006644" },
  changes_requested: { bg: "#fff3cd", color: "#856404" },
  approved: { bg: "#d4edda", color: "#155724" },
};

export function PRCardView({ card }: Props) {
  const reviewStyle = REVIEW_STATE_STYLES[card.review_summary.state];
  const statusStyle = STATUS_STYLES[card.status];
  const clusterCount = card.cluster_count ?? null;

  return (
    <ClusterHighlightWrapper changeId={card.change_id}>
      <div
        data-testid="pr-card"
        data-pr-id={card.id}
        data-status={card.status}
        style={{
          border: "1px solid #ccc",
          borderRadius: 4,
          padding: "8px 12px",
          marginBottom: 8,
          background: "#fff",
          fontSize: 12,
        }}
      >
        {/* Header row: title + status badge */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 6,
            marginBottom: 4,
          }}
        >
          <span
            data-testid="pr-card-title"
            style={{ fontWeight: 600, flex: 1, lineHeight: 1.3 }}
          >
            {card.title}
          </span>
          <span
            data-testid="pr-card-status"
            style={{
              fontSize: 10,
              fontWeight: 700,
              padding: "1px 5px",
              borderRadius: 8,
              background: statusStyle.bg,
              color: statusStyle.color,
              whiteSpace: "nowrap",
            }}
          >
            {card.status.replace("_", " ")}
          </span>
        </div>

        {/* RepoBadge — always rendered since PRCard.repo is always non-null */}
        <div style={{ marginBottom: 3 }}>
          <RepoBadge repo={card.repo} />
        </div>

        {/* Repo + number */}
        <div style={{ color: "#888", marginBottom: 3 }}>
          <a
            href={card.url}
            target="_blank"
            rel="noreferrer"
            style={{ color: "#0052cc", textDecoration: "none" }}
          >
            {card.repo}#{card.number}
          </a>
          {" · "}
          <span data-testid="pr-card-author">{card.author}</span>
        </div>

        {/* change_id if present */}
        {card.change_id && (
          <div
            data-testid="pr-card-change-id"
            style={{ color: "#888", fontSize: 11, marginBottom: 3 }}
          >
            {card.change_id}
          </div>
        )}

        {/* Origin badge */}
        <div style={{ marginBottom: 4 }}>
          <span
            data-testid="pr-card-origin"
            style={{
              fontSize: 10,
              padding: "1px 5px",
              background: "#f0f0f0",
              color: "#555",
              borderRadius: 8,
            }}
          >
            {card.origin}
          </span>
        </div>

        {/* Review summary */}
        <div
          data-testid="pr-card-review-summary"
          data-state={card.review_summary.state}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            padding: "3px 6px",
            borderRadius: 4,
            background: reviewStyle.background,
            color: reviewStyle.color,
            border: `1px solid ${reviewStyle.borderColor}`,
            fontSize: 11,
            marginTop: 4,
          }}
        >
          <span aria-hidden>{reviewStyle.icon}</span>
          <span style={{ fontWeight: 600 }}>{reviewStyle.label}</span>
          {card.review_summary.reviewer_count > 0 && (
            <>
              {" · "}
              <span data-testid="pr-card-reviewer-count">
                {card.review_summary.reviewer_count}{" "}
                {card.review_summary.reviewer_count === 1
                  ? "reviewer"
                  : "reviewers"}
              </span>
            </>
          )}
          {card.review_summary.last_reviewed_at_iso && (
            <>
              {" · "}
              <span
                data-testid="pr-card-last-reviewed"
                title={card.review_summary.last_reviewed_at_iso}
              >
                {relativeTime(card.review_summary.last_reviewed_at_iso)}
              </span>
            </>
          )}
        </div>

        {/* Cluster badge */}
        {clusterCount != null && clusterCount > 1 && (
          <div style={{ marginTop: 4 }}>
            <ClusterBadge
              changeId={card.change_id}
              clusterCount={clusterCount}
            />
          </div>
        )}
      </div>
    </ClusterHighlightWrapper>
  );
}
