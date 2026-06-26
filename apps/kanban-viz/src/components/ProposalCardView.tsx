/**
 * ProposalCardView — renders a ProposalCard with status chip and branch indicator.
 *
 * Visual treatment:
 * - drafted  → neutral chip (gray)
 * - in-impl  → info chip (blue/indigo) + branch indicator
 */
import type { ProposalCard } from "../lib/coordinator-types";
import { ClusterBadge, ClusterHighlightWrapper } from "./ClusterBadge";
import type { AnnotatedCard } from "../hooks/useBoardCards";
import { RepoBadge } from "./RepoBadge";

interface Props {
  card: ProposalCard & Partial<Pick<AnnotatedCard, "cluster_count">>;
}

const STATUS_STYLES: Record<ProposalCard["status"], { bg: string; color: string; label: string }> = {
  drafted: { bg: "#f4f5f7", color: "#666", label: "Drafted" },
  "in-impl": { bg: "#deebff", color: "#0052cc", label: "In Implementation" },
};

export function ProposalCardView({ card }: Props) {
  const statusStyle = STATUS_STYLES[card.status];
  const clusterCount = card.cluster_count ?? null;

  return (
    <ClusterHighlightWrapper changeId={card.change_id}>
      <div
        data-testid="proposal-card"
        data-proposal-id={card.id}
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
        {/* Header: title + status chip */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 6,
            marginBottom: 4,
          }}
        >
          <span
            data-testid="proposal-card-title"
            style={{ fontWeight: 600, flex: 1, lineHeight: 1.3 }}
          >
            {card.title}
          </span>
          <span
            data-testid="proposal-card-status"
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
            {statusStyle.label}
          </span>
        </div>

        {/* change_id */}
        <div
          data-testid="proposal-card-change-id"
          style={{ color: "#888", fontSize: 11, marginBottom: 3 }}
        >
          {card.change_id}
        </div>

        {/* RepoBadge — shown when repo is non-null */}
        {card.repo != null && (
          <div style={{ marginBottom: 3 }}>
            <RepoBadge repo={card.repo} />
          </div>
        )}

        {/* Branch indicator */}
        {card.has_branch && card.branch_name && (
          <div
            data-testid="proposal-card-branch"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              color: "#0052cc",
              fontSize: 11,
              marginBottom: 3,
            }}
          >
            <span aria-hidden>⎇</span>
            <code style={{ fontSize: 11 }}>{card.branch_name}</code>
            {card.code_changes_outside_proposal > 0 && (
              <span
                data-testid="proposal-card-code-changes"
                style={{
                  fontSize: 10,
                  padding: "1px 4px",
                  background: "#e3fcef",
                  color: "#006644",
                  borderRadius: 6,
                }}
              >
                {card.code_changes_outside_proposal} commit
                {card.code_changes_outside_proposal === 1 ? "" : "s"} outside proposal
              </span>
            )}
          </div>
        )}

        {/* Artifact indicators */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
          {card.has_tasks_md && (
            <span
              style={{
                fontSize: 10,
                padding: "1px 4px",
                background: "#f0f0f0",
                color: "#555",
                borderRadius: 6,
              }}
            >
              tasks
            </span>
          )}
          {card.has_design_md && (
            <span
              style={{
                fontSize: 10,
                padding: "1px 4px",
                background: "#f0f0f0",
                color: "#555",
                borderRadius: 6,
              }}
            >
              design
            </span>
          )}
          {card.has_spec_delta && (
            <span
              style={{
                fontSize: 10,
                padding: "1px 4px",
                background: "#f0f0f0",
                color: "#555",
                borderRadius: 6,
              }}
            >
              spec
            </span>
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
