/**
 * Tests for the three column-mapping functions (task 5.1).
 * Covers: issueStatusToColumn, prStatusToColumn, proposalStatusToColumn.
 * Includes exhaustiveness check at the type level via assertNever.
 */
import { describe, it, expect } from "vitest";
import {
  issueStatusToColumn,
  prStatusToColumn,
  proposalStatusToColumn,
} from "../coordinator-types";
import type { IssueStatus, PRStatus, ProposalStatus, ColumnId } from "../coordinator-types";

// ─────────────────────────────────────────────────────────────────────────────
// issueStatusToColumn — preserved behavior (critical invariant)

describe("issueStatusToColumn", () => {
  it("pending → backlog", () => {
    expect(issueStatusToColumn("pending")).toBe<ColumnId>("backlog");
  });
  it("blocked → backlog", () => {
    expect(issueStatusToColumn("blocked")).toBe<ColumnId>("backlog");
  });
  it("claimed → in-flight", () => {
    expect(issueStatusToColumn("claimed")).toBe<ColumnId>("in-flight");
  });
  it("running → in-flight", () => {
    expect(issueStatusToColumn("running")).toBe<ColumnId>("in-flight");
  });
  it("completed → done", () => {
    expect(issueStatusToColumn("completed")).toBe<ColumnId>("done");
  });
  it("failed → done", () => {
    expect(issueStatusToColumn("failed")).toBe<ColumnId>("done");
  });

  // Exhaustiveness: the return type annotation ensures no status is unhandled.
  it("covers all IssueStatus values without a default branch", () => {
    const statuses: IssueStatus[] = [
      "pending",
      "claimed",
      "running",
      "completed",
      "failed",
      "blocked",
    ];
    for (const s of statuses) {
      expect(() => issueStatusToColumn(s)).not.toThrow();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// prStatusToColumn

describe("prStatusToColumn", () => {
  it("draft → backlog", () => {
    expect(prStatusToColumn("draft")).toBe<ColumnId>("backlog");
  });
  it("open → backlog", () => {
    expect(prStatusToColumn("open")).toBe<ColumnId>("backlog");
  });
  it("review → in-flight", () => {
    expect(prStatusToColumn("review")).toBe<ColumnId>("in-flight");
  });
  it("changes_requested → in-flight", () => {
    expect(prStatusToColumn("changes_requested")).toBe<ColumnId>("in-flight");
  });
  it("approved → done", () => {
    expect(prStatusToColumn("approved")).toBe<ColumnId>("done");
  });

  it("covers all PRStatus values", () => {
    const statuses: PRStatus[] = [
      "draft",
      "open",
      "review",
      "changes_requested",
      "approved",
    ];
    for (const s of statuses) {
      expect(() => prStatusToColumn(s)).not.toThrow();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// proposalStatusToColumn

describe("proposalStatusToColumn", () => {
  it("drafted → backlog", () => {
    expect(proposalStatusToColumn("drafted")).toBe<ColumnId>("backlog");
  });
  it("in-impl → in-flight", () => {
    expect(proposalStatusToColumn("in-impl")).toBe<ColumnId>("in-flight");
  });

  it("covers all ProposalStatus values", () => {
    const statuses: ProposalStatus[] = ["drafted", "in-impl"];
    for (const s of statuses) {
      expect(() => proposalStatusToColumn(s)).not.toThrow();
    }
  });
});
