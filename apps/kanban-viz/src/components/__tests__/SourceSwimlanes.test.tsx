/**
 * Tests for SourceSwimlanes component (task 7.1).
 *
 * Covers:
 * - Three rows render in order Issues → PRs → Proposals
 * - Each row's header shows correct backlog/in-flight/done totals
 * - Toggling a row chip hides that row's cards
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SourceSwimlanes } from "../SourceSwimlanes";
import type { BoardCard, IssueCard, PRCard, ProposalCard } from "../../lib/coordinator-types";

function makeIssue(id: string, status: IssueCard["status"] = "pending"): IssueCard {
  return {
    kind: "issue",
    id,
    title: `Issue ${id}`,
    body: null,
    status,
    priority: 1,
    labels: [],
    assignee: null,
    claimed_by: null,
    claimed_at: null,
    completed_at: status === "completed" ? new Date().toISOString() : null,
    created_at: new Date().toISOString(),
    updated_at: null,
    change_id: null,
    task_key: null,
  };
}

function makePR(id: string, status: PRCard["status"] = "open"): PRCard {
  return {
    kind: "pr",
    id,
    change_id: null,
    repo: "jankneumann/agentic-coding-tools",
    number: 1,
    title: `PR ${id}`,
    author: "alice",
    head_branch: "openspec/foo",
    base_branch: "main",
    origin: "openspec",
    status,
    review_summary: { state: "none", reviewer_count: 0, last_reviewed_at_iso: null },
    is_draft: false,
    url: "https://github.com/example/1",
    created_at_iso: new Date().toISOString(),
    updated_at_iso: new Date().toISOString(),
  };
}

function makeProposal(id: string, status: ProposalCard["status"] = "drafted"): ProposalCard {
  return {
    kind: "proposal",
    id,
    change_id: id,
    title: `Proposal ${id}`,
    status,
    created_at_iso: new Date().toISOString(),
    updated_at_iso: new Date().toISOString(),
    proposal_path: `openspec/changes/${id}/proposal.md`,
    has_tasks_md: false,
    has_design_md: false,
    has_spec_delta: false,
    has_branch: false,
    branch_name: null,
    code_changes_outside_proposal: 0,
    repo: null,
    change_id_namespaced: null,
  };
}

const mixedCards: BoardCard[] = [
  makeIssue("i1", "pending"),     // backlog
  makeIssue("i2", "running"),     // in-flight
  makeIssue("i3", "completed"),   // done
  makePR("pr1", "draft"),         // backlog
  makePR("pr2", "review"),        // in-flight
  makeProposal("prop1", "drafted"),   // backlog
  makeProposal("prop2", "in-impl"),   // in-flight
];

describe("SourceSwimlanes — three-row layout", () => {
  it("renders Issues, PRs, Proposals rows in order", () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    expect(screen.getByTestId("source-row-issues")).toBeInTheDocument();
    expect(screen.getByTestId("source-row-prs")).toBeInTheDocument();
    expect(screen.getByTestId("source-row-proposals")).toBeInTheDocument();
    // Check order using the DOM
    const swimlanes = screen.getByTestId("source-swimlanes");
    const children = Array.from(swimlanes.children).map((el) =>
      el.getAttribute("data-testid"),
    );
    expect(children).toEqual([
      "source-row-issues",
      "source-row-prs",
      "source-row-proposals",
    ]);
  });

  it("renders all three columns within each row", () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    // Each row has backlog, in-flight, done columns
    expect(screen.getAllByTestId(/column-issues-backlog|column-prs-backlog|column-proposals-backlog/)).toHaveLength(3);
    expect(screen.getAllByTestId(/column-issues-in-flight|column-prs-in-flight|column-proposals-in-flight/)).toHaveLength(3);
    expect(screen.getAllByTestId(/column-issues-done|column-prs-done|column-proposals-done/)).toHaveLength(3);
  });
});

describe("SourceSwimlanes — row totals", () => {
  it("issues row shows correct counts per column", () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    // backlog: 1 pending, in-flight: 1 running, done: 1 completed
    expect(screen.getByTestId("count-issues-backlog")).toHaveTextContent("1");
    expect(screen.getByTestId("count-issues-in-flight")).toHaveTextContent("1");
    expect(screen.getByTestId("count-issues-done")).toHaveTextContent("1");
  });

  it("PRs row shows correct counts per column", () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    // backlog: 1 draft, in-flight: 1 review, done: 0
    expect(screen.getByTestId("count-prs-backlog")).toHaveTextContent("1");
    expect(screen.getByTestId("count-prs-in-flight")).toHaveTextContent("1");
    expect(screen.getByTestId("count-prs-done")).toHaveTextContent("0");
  });

  it("Proposals row shows correct counts per column", () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    // backlog: 1 drafted, in-flight: 1 in-impl, done: 0
    expect(screen.getByTestId("count-proposals-backlog")).toHaveTextContent("1");
    expect(screen.getByTestId("count-proposals-in-flight")).toHaveTextContent("1");
    expect(screen.getByTestId("count-proposals-done")).toHaveTextContent("0");
  });
});

describe("SourceSwimlanes — row visibility toggle", () => {
  it("all rows are visible by default", () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    expect(screen.getByTestId("source-row-issues")).toBeVisible();
    expect(screen.getByTestId("source-row-prs")).toBeVisible();
    expect(screen.getByTestId("source-row-proposals")).toBeVisible();
  });

  it("clicking hide-row chip hides that row's cards", async () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    const user = userEvent.setup();
    const hideIssuesChip = screen.getByTestId("hide-row-issues");
    await user.click(hideIssuesChip);
    expect(screen.queryByTestId("source-row-body-issues")).not.toBeInTheDocument();
  });

  it("clicking hide chip again re-shows the row", async () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    const user = userEvent.setup();
    const chip = screen.getByTestId("hide-row-issues");
    await user.click(chip);
    await user.click(chip);
    expect(screen.getByTestId("source-row-body-issues")).toBeInTheDocument();
  });

  it("hiding one row does not hide others", async () => {
    render(<SourceSwimlanes cards={mixedCards} />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("hide-row-issues"));
    expect(screen.queryByTestId("source-row-body-issues")).not.toBeInTheDocument();
    expect(screen.getByTestId("source-row-body-prs")).toBeInTheDocument();
    expect(screen.getByTestId("source-row-body-proposals")).toBeInTheDocument();
  });
});

describe("SourceSwimlanes — empty state", () => {
  it("renders with empty card array without crashing", () => {
    render(<SourceSwimlanes cards={[]} />);
    expect(screen.getByTestId("source-row-issues")).toBeInTheDocument();
    expect(screen.getByTestId("source-row-prs")).toBeInTheDocument();
    expect(screen.getByTestId("source-row-proposals")).toBeInTheDocument();
  });
});
