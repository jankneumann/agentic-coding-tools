/**
 * SourceSwimlanes — renders three source rows (Issues / PRs / Proposals),
 * each row having the three standard columns (Backlog / In-Flight / Done).
 *
 * Visual language mirrors VendorSwimlanes but operates at a higher level:
 * rows are card-source categories rather than vendor lanes.
 *
 * Row visibility state can be toggled by the user; the state optionally
 * syncs with the saved-view payload's `hidden_rows` field (D4).
 *
 * This component integrates:
 * - PROriginFilter on the PR row toolbar (client-side filter, no refetch)
 * - PRCardView for PR kind cards (with review-findings projection)
 * - ProposalCardView for proposal kind cards
 * - ClusterBadge on every card with cluster_count > 1
 */
import { useState } from "react";
import type { BoardCard, IssueCard, PRCard, ProposalCard, ColumnId, PROrigin, SourceWarning } from "../lib/coordinator-types";
import {
  issueStatusToColumn,
  prStatusToColumn,
  proposalStatusToColumn,
} from "../lib/coordinator-types";
import { PROriginFilter, ALL_PR_ORIGINS, filterByOrigin } from "./PROriginFilter";
import { PRCardView } from "./PRCardView";
import { ProposalCardView } from "./ProposalCardView";
import { ClusterBadge, ClusterHighlightWrapper } from "./ClusterBadge";
import { HiddenReposToggle } from "./HiddenReposToggle";
import type { AnnotatedCard } from "../hooks/useBoardCards";

type RowKey = "issues" | "prs" | "proposals";

interface Props {
  cards: BoardCard[];
  /** Annotated cards with cluster_count. If provided, enables cluster badges. */
  annotatedCards?: AnnotatedCard[];
  /** Initially hidden rows (synced from saved-view). */
  initialHiddenRows?: RowKey[];
  /** Initially selected PR origins (synced from saved-view pr_origins). */
  initialPrOrigins?: PROrigin[];
  /** Called when the PR origin selection changes (for saved-view sync). */
  onPrOriginsChange?: (origins: PROrigin[]) => void;
  /**
   * Source warnings from GET /openspec/proposals multi-source response
   * (`_warnings` field). When non-empty, the Proposals row renders a
   * partial-result chip (D6 degraded-mode UX).
   */
  proposalsWarnings?: readonly SourceWarning[];
  /** Currently hidden repos (synced from saved-view hidden_repos). */
  hiddenRepos?: readonly string[];
  /** Called when the user toggles repo visibility. */
  onHiddenReposChange?: (hiddenRepos: string[]) => void;
}

const ROW_LABELS: Record<RowKey, string> = {
  issues: "Issues",
  prs: "Pull Requests",
  proposals: "Proposals",
};

const COLUMN_LABELS: Record<ColumnId, string> = {
  backlog: "Backlog",
  "in-flight": "In Flight",
  done: "Done",
};

const COLUMNS: ColumnId[] = ["backlog", "in-flight", "done"];

/** Bucket IssueCards by column. */
function bucketIssues(cards: IssueCard[]): Record<ColumnId, IssueCard[]> {
  const out: Record<ColumnId, IssueCard[]> = { backlog: [], "in-flight": [], done: [] };
  for (const card of cards) {
    out[issueStatusToColumn(card.status)].push(card);
  }
  return out;
}

/** Bucket PRCards by column. */
function bucketPRs(cards: PRCard[]): Record<ColumnId, PRCard[]> {
  const out: Record<ColumnId, PRCard[]> = { backlog: [], "in-flight": [], done: [] };
  for (const card of cards) {
    out[prStatusToColumn(card.status)].push(card);
  }
  return out;
}

/** Bucket ProposalCards by column. */
function bucketProposals(cards: ProposalCard[]): Record<ColumnId, ProposalCard[]> {
  const out: Record<ColumnId, ProposalCard[]> = { backlog: [], "in-flight": [], done: [] };
  for (const card of cards) {
    out[proposalStatusToColumn(card.status)].push(card);
  }
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// Issue row

interface IssueRowProps {
  rowKey: "issues";
  label: string;
  bucketed: Record<ColumnId, IssueCard[]>;
  annotatedByKey: Map<string, AnnotatedCard>;
  visible: boolean;
  onToggle: () => void;
}

function IssueSourceRow({ rowKey, label, bucketed, annotatedByKey, visible, onToggle }: IssueRowProps) {
  const countBucketed: Record<ColumnId, { title: string; id: string }[]> = {
    backlog: bucketed.backlog.map((c) => ({ id: c.id, title: c.title })),
    "in-flight": bucketed["in-flight"].map((c) => ({ id: c.id, title: c.title })),
    done: bucketed.done.map((c) => ({ id: c.id, title: c.title })),
  };

  return (
    <div
      data-testid={`source-row-${rowKey}`}
      style={{
        marginBottom: 16,
        border: "1px solid #e8e8e8",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "8px 12px",
          background: "#fafafa",
          borderBottom: visible ? "1px solid #e8e8e8" : "none",
          gap: 8,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{label}</span>
        {COLUMNS.map((col) => (
          <span
            key={col}
            data-testid={`count-${rowKey}-${col}`}
            style={{
              fontSize: 11,
              color: "#666",
              background: "#f0f0f0",
              borderRadius: 10,
              padding: "1px 7px",
              marginRight: 2,
            }}
          >
            {countBucketed[col].length}
          </span>
        ))}
        <button
          type="button"
          data-testid={`hide-row-${rowKey}`}
          onClick={onToggle}
          style={{
            fontSize: 11,
            padding: "2px 8px",
            background: visible ? "#deebff" : "#f4f5f7",
            color: visible ? "#0052cc" : "#666",
            border: "none",
            borderRadius: 10,
            cursor: "pointer",
            fontWeight: 600,
          }}
          aria-label={visible ? `Hide ${label} row` : `Show ${label} row`}
          aria-expanded={visible}
        >
          {visible ? "hide" : "show"}
        </button>
      </div>

      {visible && (
        <div data-testid={`source-row-body-${rowKey}`} style={{ display: "flex", gap: 0 }}>
          {COLUMNS.map((col) => (
            <div
              key={col}
              data-testid={`column-${rowKey}-${col}`}
              style={{
                flex: "1 1 0",
                padding: "8px 12px",
                borderRight: col !== "done" ? "1px solid #e8e8e8" : "none",
                minHeight: 60,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: "uppercase",
                  color: "#888",
                  marginBottom: 8,
                }}
              >
                {COLUMN_LABELS[col]}
              </div>
              {bucketed[col].map((card) => {
                const annotated = annotatedByKey.get(card.id);
                const clusterCount = annotated?.cluster_count ?? null;
                return (
                  <ClusterHighlightWrapper key={card.id} changeId={card.change_id}>
                    <div
                      data-testid={`card-${rowKey}-${card.id}`}
                      style={{
                        fontSize: 12,
                        padding: "4px 6px",
                        marginBottom: 4,
                        background: "#fff",
                        border: "1px solid #e8e8e8",
                        borderRadius: 3,
                      }}
                    >
                      {card.title}
                      {clusterCount != null && clusterCount > 1 && (
                        <span style={{ marginLeft: 4 }}>
                          <ClusterBadge changeId={card.change_id} clusterCount={clusterCount} />
                        </span>
                      )}
                    </div>
                  </ClusterHighlightWrapper>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PR row

interface PRRowProps {
  rowKey: "prs";
  label: string;
  allPrCards: PRCard[];
  annotatedByKey: Map<string, AnnotatedCard>;
  visible: boolean;
  onToggle: () => void;
  initialOrigins?: PROrigin[];
  onOriginsChange?: (origins: PROrigin[]) => void;
}

function PRSourceRow({
  rowKey,
  label,
  allPrCards,
  annotatedByKey,
  visible,
  onToggle,
  initialOrigins,
  onOriginsChange,
}: PRRowProps) {
  const [selectedOrigins, setSelectedOrigins] = useState<PROrigin[]>(
    initialOrigins ?? [...ALL_PR_ORIGINS],
  );

  const handleOriginsChange = (origins: PROrigin[]) => {
    setSelectedOrigins(origins);
    onOriginsChange?.(origins);
  };

  const filteredPRs = filterByOrigin(allPrCards, selectedOrigins);
  const bucketed = bucketPRs(filteredPRs);
  const countBucketed: Record<ColumnId, { title: string; id: string }[]> = {
    backlog: bucketed.backlog.map((c) => ({ id: c.id, title: c.title })),
    "in-flight": bucketed["in-flight"].map((c) => ({ id: c.id, title: c.title })),
    done: bucketed.done.map((c) => ({ id: c.id, title: c.title })),
  };

  return (
    <div
      data-testid={`source-row-${rowKey}`}
      style={{
        marginBottom: 16,
        border: "1px solid #e8e8e8",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "8px 12px",
          background: "#fafafa",
          borderBottom: visible ? "1px solid #e8e8e8" : "none",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13 }}>{label}</span>
        {/* PR Origin Filter on the PR row toolbar */}
        <div style={{ flex: 1 }}>
          <PROriginFilter
            value={selectedOrigins}
            onSelectionChange={handleOriginsChange}
          />
        </div>
        {COLUMNS.map((col) => (
          <span
            key={col}
            data-testid={`count-${rowKey}-${col}`}
            style={{
              fontSize: 11,
              color: "#666",
              background: "#f0f0f0",
              borderRadius: 10,
              padding: "1px 7px",
              marginRight: 2,
            }}
          >
            {countBucketed[col].length}
          </span>
        ))}
        <button
          type="button"
          data-testid={`hide-row-${rowKey}`}
          onClick={onToggle}
          style={{
            fontSize: 11,
            padding: "2px 8px",
            background: visible ? "#deebff" : "#f4f5f7",
            color: visible ? "#0052cc" : "#666",
            border: "none",
            borderRadius: 10,
            cursor: "pointer",
            fontWeight: 600,
          }}
          aria-label={visible ? `Hide ${label} row` : `Show ${label} row`}
          aria-expanded={visible}
        >
          {visible ? "hide" : "show"}
        </button>
      </div>

      {visible && (
        <div data-testid={`source-row-body-${rowKey}`} style={{ display: "flex", gap: 0 }}>
          {COLUMNS.map((col) => (
            <div
              key={col}
              data-testid={`column-${rowKey}-${col}`}
              style={{
                flex: "1 1 0",
                padding: "8px 12px",
                borderRight: col !== "done" ? "1px solid #e8e8e8" : "none",
                minHeight: 60,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: "uppercase",
                  color: "#888",
                  marginBottom: 8,
                }}
              >
                {COLUMN_LABELS[col]}
              </div>
              {bucketed[col].map((card) => {
                const annotated = annotatedByKey.get(card.id);
                const clusterCount = annotated?.cluster_count ?? null;
                return (
                  <div key={card.id} data-testid={`card-${rowKey}-${card.id}`}>
                    <PRCardView card={{ ...card, cluster_count: clusterCount }} />
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Proposal row

interface ProposalRowProps {
  rowKey: "proposals";
  label: string;
  bucketed: Record<ColumnId, ProposalCard[]>;
  annotatedByKey: Map<string, AnnotatedCard>;
  visible: boolean;
  onToggle: () => void;
  warnings?: readonly SourceWarning[];
}

/** Inline partial-result chip for the Proposals row (D6 degraded mode). */
function PartialResultChip({ warnings }: { warnings: readonly SourceWarning[] }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
      <button
        type="button"
        data-testid="proposals-partial-result-chip"
        onClick={() => { setExpanded((v) => !v); }}
        aria-expanded={expanded}
        style={{
          fontSize: 11,
          fontWeight: 600,
          padding: "2px 8px",
          borderRadius: 10,
          border: "1px solid #ff8b00",
          background: "#fffae6",
          color: "#974f0c",
          cursor: "pointer",
          whiteSpace: "nowrap",
        }}
      >
        ⚠ Partial results ({warnings.length} source{warnings.length !== 1 ? "s" : ""} failed)
      </button>
      {expanded && (
        <div
          data-testid="proposals-warnings-detail"
          style={{
            fontSize: 11,
            background: "#fffae6",
            border: "1px solid #ff8b00",
            borderRadius: 4,
            padding: "4px 8px",
            maxWidth: 320,
            wordBreak: "break-all",
          }}
        >
          {warnings.map((w, i) => (
            <div key={i} style={{ marginBottom: i < warnings.length - 1 ? 2 : 0 }}>
              <strong>{w.source}</strong>: {w.error}
              {w.message ? ` — ${w.message}` : ""}
            </div>
          ))}
        </div>
      )}
    </span>
  );
}

function ProposalSourceRow({ rowKey, label, bucketed, annotatedByKey, visible, onToggle, warnings }: ProposalRowProps) {
  const countBucketed: Record<ColumnId, { title: string; id: string }[]> = {
    backlog: bucketed.backlog.map((c) => ({ id: c.id, title: c.title })),
    "in-flight": bucketed["in-flight"].map((c) => ({ id: c.id, title: c.title })),
    done: bucketed.done.map((c) => ({ id: c.id, title: c.title })),
  };

  return (
    <div
      data-testid={`source-row-${rowKey}`}
      style={{
        marginBottom: 16,
        border: "1px solid #e8e8e8",
        borderRadius: 6,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "8px 12px",
          background: "#fafafa",
          borderBottom: visible ? "1px solid #e8e8e8" : "none",
          gap: 8,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{label}</span>
        {warnings && warnings.length > 0 && (
          <PartialResultChip warnings={warnings} />
        )}
        {COLUMNS.map((col) => (
          <span
            key={col}
            data-testid={`count-${rowKey}-${col}`}
            style={{
              fontSize: 11,
              color: "#666",
              background: "#f0f0f0",
              borderRadius: 10,
              padding: "1px 7px",
              marginRight: 2,
            }}
          >
            {countBucketed[col].length}
          </span>
        ))}
        <button
          type="button"
          data-testid={`hide-row-${rowKey}`}
          onClick={onToggle}
          style={{
            fontSize: 11,
            padding: "2px 8px",
            background: visible ? "#deebff" : "#f4f5f7",
            color: visible ? "#0052cc" : "#666",
            border: "none",
            borderRadius: 10,
            cursor: "pointer",
            fontWeight: 600,
          }}
          aria-label={visible ? `Hide ${label} row` : `Show ${label} row`}
          aria-expanded={visible}
        >
          {visible ? "hide" : "show"}
        </button>
      </div>

      {visible && (
        <div data-testid={`source-row-body-${rowKey}`} style={{ display: "flex", gap: 0 }}>
          {COLUMNS.map((col) => (
            <div
              key={col}
              data-testid={`column-${rowKey}-${col}`}
              style={{
                flex: "1 1 0",
                padding: "8px 12px",
                borderRight: col !== "done" ? "1px solid #e8e8e8" : "none",
                minHeight: 60,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: "uppercase",
                  color: "#888",
                  marginBottom: 8,
                }}
              >
                {COLUMN_LABELS[col]}
              </div>
              {bucketed[col].map((card) => {
                const annotated = annotatedByKey.get(card.id);
                const clusterCount = annotated?.cluster_count ?? null;
                return (
                  <div key={card.id} data-testid={`card-${rowKey}-${card.id}`}>
                    <ProposalCardView card={{ ...card, cluster_count: clusterCount }} />
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main SourceSwimlanes export

export function SourceSwimlanes({
  cards,
  annotatedCards,
  initialHiddenRows = [],
  initialPrOrigins,
  onPrOriginsChange,
  proposalsWarnings,
  hiddenRepos = [],
  onHiddenReposChange,
}: Props) {
  const [hiddenRows, setHiddenRows] = useState<Set<RowKey>>(
    new Set(initialHiddenRows),
  );

  const toggleRow = (key: RowKey) => {
    setHiddenRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Build annotated lookup by card id
  const annotatedByKey = new Map<string, AnnotatedCard>();
  if (annotatedCards) {
    for (const a of annotatedCards) {
      annotatedByKey.set(a.id, a);
    }
  }

  // Partition cards by kind
  const issueCards = cards.filter((c): c is IssueCard => c.kind === "issue");
  const prCards = cards.filter((c): c is PRCard => c.kind === "pr");
  const proposalCards = cards.filter((c): c is ProposalCard => c.kind === "proposal");

  const issueBucketed = bucketIssues(issueCards);
  const proposalBucketed = bucketProposals(proposalCards);

  // Derive unique repos across all cards for HiddenReposToggle
  const allRepos = Array.from(
    new Set(
      cards
        .map((c) => c.repo ?? null)
        .filter((r): r is string => r != null),
    ),
  ).sort();

  return (
    <div data-testid="source-swimlanes">
      {allRepos.length > 0 && onHiddenReposChange && (
        <div style={{ padding: "4px 0 8px 0" }}>
          <HiddenReposToggle
            repos={allRepos}
            hiddenRepos={hiddenRepos}
            onHiddenReposChange={onHiddenReposChange}
          />
        </div>
      )}
      <IssueSourceRow
        rowKey="issues"
        label={ROW_LABELS.issues}
        bucketed={issueBucketed}
        annotatedByKey={annotatedByKey}
        visible={!hiddenRows.has("issues")}
        onToggle={() => { toggleRow("issues"); }}
      />
      <PRSourceRow
        rowKey="prs"
        label={ROW_LABELS.prs}
        allPrCards={prCards}
        annotatedByKey={annotatedByKey}
        visible={!hiddenRows.has("prs")}
        onToggle={() => { toggleRow("prs"); }}
        initialOrigins={initialPrOrigins}
        onOriginsChange={onPrOriginsChange}
      />
      <ProposalSourceRow
        rowKey="proposals"
        label={ROW_LABELS.proposals}
        bucketed={proposalBucketed}
        annotatedByKey={annotatedByKey}
        visible={!hiddenRows.has("proposals")}
        onToggle={() => { toggleRow("proposals"); }}
        warnings={proposalsWarnings}
      />
    </div>
  );
}
