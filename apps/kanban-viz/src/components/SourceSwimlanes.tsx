/**
 * SourceSwimlanes — renders three source rows (Issues / PRs / Proposals),
 * each row having the three standard columns (Backlog / In-Flight / Done).
 *
 * Visual language mirrors VendorSwimlanes but operates at a higher level:
 * rows are card-source categories rather than vendor lanes.
 *
 * Row visibility state can be toggled by the user; the state optionally
 * syncs with the saved-view payload's `hidden_rows` field (D4).
 */
import { useState } from "react";
import type { BoardCard, IssueCard, PRCard, ProposalCard, ColumnId } from "../lib/coordinator-types";
import {
  issueStatusToColumn,
  prStatusToColumn,
  proposalStatusToColumn,
} from "../lib/coordinator-types";

type RowKey = "issues" | "prs" | "proposals";

interface Props {
  cards: BoardCard[];
  /** Initially hidden rows (synced from saved-view). */
  initialHiddenRows?: RowKey[];
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

interface RowProps {
  rowKey: RowKey;
  label: string;
  bucketed: Record<ColumnId, { title: string; id: string }[]>;
  visible: boolean;
  onToggle: () => void;
}

function SourceRow({ rowKey, label, bucketed, visible, onToggle }: RowProps) {
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
      {/* Row header */}
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
        {/* Column count badges */}
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
            {bucketed[col].length}
          </span>
        ))}
        {/* Toggle chip */}
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

      {/* Row body */}
      {visible && (
        <div
          data-testid={`source-row-body-${rowKey}`}
          style={{ display: "flex", gap: 0 }}
        >
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
              {bucketed[col].map((card) => (
                <div
                  key={card.id}
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
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SourceSwimlanes({ cards, initialHiddenRows = [] }: Props) {
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

  // Partition cards by kind
  const issueCards = cards.filter((c): c is IssueCard => c.kind === "issue");
  const prCards = cards.filter((c): c is PRCard => c.kind === "pr");
  const proposalCards = cards.filter((c): c is ProposalCard => c.kind === "proposal");

  const issueBucketed = bucketIssues(issueCards);
  const prBucketed = bucketPRs(prCards);
  const proposalBucketed = bucketProposals(proposalCards);

  // Map bucketed cards to minimal display shape
  function toDisplay<T extends { id: string; title: string }>(
    b: Record<ColumnId, T[]>,
  ): Record<ColumnId, { id: string; title: string }[]> {
    return {
      backlog: b.backlog.map((c) => ({ id: c.id, title: c.title })),
      "in-flight": b["in-flight"].map((c) => ({ id: c.id, title: c.title })),
      done: b.done.map((c) => ({ id: c.id, title: c.title })),
    };
  }

  return (
    <div data-testid="source-swimlanes">
      <SourceRow
        rowKey="issues"
        label={ROW_LABELS.issues}
        bucketed={toDisplay(issueBucketed)}
        visible={!hiddenRows.has("issues")}
        onToggle={() => { toggleRow("issues"); }}
      />
      <SourceRow
        rowKey="prs"
        label={ROW_LABELS.prs}
        bucketed={toDisplay(prBucketed)}
        visible={!hiddenRows.has("prs")}
        onToggle={() => { toggleRow("prs"); }}
      />
      <SourceRow
        rowKey="proposals"
        label={ROW_LABELS.proposals}
        bucketed={toDisplay(proposalBucketed)}
        visible={!hiddenRows.has("proposals")}
        onToggle={() => { toggleRow("proposals"); }}
      />
    </div>
  );
}
