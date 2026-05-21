/**
 * Tests for Board, Column, and Card components.
 * Covers tasks 3.4, 3.5, 3.6.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Board } from "../components/Board";
import {
  pendingIssue,
  claimedIssue,
  runningIssue,
  completedRecentIssue,
  completedOldIssue,
  blockedIssue,
} from "./fixtures";

// ─────────────────────────────────────────────────────────────────────────────
// 3.4: Empty board renders three columns with explicit empty-state copy

describe("Board — empty state", () => {
  it("renders three columns even when no issues are provided", () => {
    render(<Board issues={[]} />);
    expect(screen.getByTestId("column-backlog")).toBeInTheDocument();
    expect(screen.getByTestId("column-in-flight")).toBeInTheDocument();
    expect(screen.getByTestId("column-done")).toBeInTheDocument();
  });

  it("each empty column shows explicit empty-state copy", () => {
    render(<Board issues={[]} />);
    expect(screen.getByTestId("column-empty-state-backlog")).toBeInTheDocument();
    expect(screen.getByTestId("column-empty-state-in-flight")).toBeInTheDocument();
    expect(screen.getByTestId("column-empty-state-done")).toBeInTheDocument();
  });

  it("backlog empty state mentions pending work", () => {
    render(<Board issues={[]} />);
    expect(screen.getByTestId("column-empty-state-backlog")).toHaveTextContent(
      /pending/i,
    );
  });

  it("in-flight empty state mentions agents", () => {
    render(<Board issues={[]} />);
    expect(screen.getByTestId("column-empty-state-in-flight")).toHaveTextContent(
      /agent/i,
    );
  });

  it("done empty state mentions completed/tasks", () => {
    render(<Board issues={[]} />);
    expect(screen.getByTestId("column-empty-state-done")).toHaveTextContent(
      /completed|task/i,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3.5: Card renders with title, change-id, assignee, relative timestamp

describe("Card fields", () => {
  it("renders card title", () => {
    render(<Board issues={[claimedIssue]} />);
    expect(screen.getByTestId("card-title")).toHaveTextContent(claimedIssue.title);
  });

  it("renders change-id when present", () => {
    render(<Board issues={[claimedIssue]} />);
    expect(screen.getByTestId("card-change-id")).toHaveTextContent(
      claimedIssue.change_id!,
    );
  });

  it("renders assignee (claimed_by takes precedence)", () => {
    render(<Board issues={[claimedIssue]} />);
    expect(screen.getByTestId("card-assignee")).toHaveTextContent(
      claimedIssue.claimed_by!,
    );
  });

  it("renders relative timestamp from claimed_at", () => {
    render(<Board issues={[claimedIssue]} />);
    const el = screen.getByTestId("card-timestamp");
    // Should show a relative string (min, h, d) or "just now"
    expect(el).toBeInTheDocument();
    expect(el.textContent).toMatch(/just now|m ago|h ago|d ago/i);
  });

  it("falls back to assignee field when claimed_by is null", () => {
    render(<Board issues={[{ ...claimedIssue, claimed_by: null }]} />);
    expect(screen.getByTestId("card-assignee")).toHaveTextContent(
      claimedIssue.assignee!,
    );
  });

  it("does not render assignee row when both claimed_by and assignee are null", () => {
    render(<Board issues={[pendingIssue]} />);
    expect(screen.queryByTestId("card-assignee")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3.6: Status-to-column mapping

describe("Board — column bucketing", () => {
  const allIssues = [
    pendingIssue,       // pending → backlog
    blockedIssue,       // blocked → backlog
    claimedIssue,       // claimed → in-flight
    runningIssue,       // running → in-flight
    completedRecentIssue, // completed (< 24h) → done
    completedOldIssue,  // completed (> 24h) → NOT shown
  ];

  it("pending issues go to backlog", () => {
    render(<Board issues={allIssues} />);
    const backlog = screen.getByTestId("column-backlog");
    expect(backlog).toHaveTextContent(pendingIssue.title);
  });

  it("blocked issues go to backlog", () => {
    render(<Board issues={allIssues} />);
    const backlog = screen.getByTestId("column-backlog");
    expect(backlog).toHaveTextContent(blockedIssue.title);
  });

  it("claimed issues go to in-flight", () => {
    render(<Board issues={allIssues} />);
    const inFlight = screen.getByTestId("column-in-flight");
    expect(inFlight).toHaveTextContent(claimedIssue.title);
  });

  it("running issues go to in-flight", () => {
    render(<Board issues={allIssues} />);
    const inFlight = screen.getByTestId("column-in-flight");
    expect(inFlight).toHaveTextContent(runningIssue.title);
  });

  it("completed-within-24h issues go to done", () => {
    render(<Board issues={allIssues} />);
    const done = screen.getByTestId("column-done");
    expect(done).toHaveTextContent(completedRecentIssue.title);
  });

  it("completed-older-than-24h issues are NOT shown in done", () => {
    render(<Board issues={allIssues} />);
    const done = screen.getByTestId("column-done");
    expect(done).not.toHaveTextContent(completedOldIssue.title);
  });

  it("backlog does NOT contain in-flight issues", () => {
    render(<Board issues={allIssues} />);
    const backlog = screen.getByTestId("column-backlog");
    expect(backlog).not.toHaveTextContent(claimedIssue.title);
  });

  it("in-flight does NOT contain pending issues", () => {
    render(<Board issues={allIssues} />);
    const inFlight = screen.getByTestId("column-in-flight");
    expect(inFlight).not.toHaveTextContent(pendingIssue.title);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// IMPL_REVIEW F2 — Card renders VendorSwimlanes when in-flight; consensus when completed

describe("Card — VendorSwimlanes integration (IMPL_REVIEW F2)", () => {
  const inFlightAgents = new Map([
    [
      claimedIssue.id,
      [
        {
          agent_id: "wp-backend--claude",
          last_event_at: new Date(Date.now() - 30_000).toISOString(),
          outcome: null,
        },
      ],
    ],
  ]);

  it("renders vendor-swimlanes for claimed (in-flight) cards when agents present", () => {
    render(<Board issues={[claimedIssue]} agentsByIssueId={inFlightAgents} />);
    expect(screen.getByTestId("vendor-swimlanes")).toBeInTheDocument();
    expect(screen.getByTestId("swimlane-claude")).toBeInTheDocument();
  });

  it("does NOT render swimlanes when no agents are provided for the issue", () => {
    render(<Board issues={[claimedIssue]} />);
    expect(screen.queryByTestId("vendor-swimlanes")).not.toBeInTheDocument();
  });

  it("does NOT render swimlanes for non-in-flight, non-completed statuses", () => {
    // Map has agents for pendingIssue, but pending is not in-flight.
    const agentsMap = new Map([
      [
        pendingIssue.id,
        [
          {
            agent_id: "wp-backend--claude",
            last_event_at: new Date().toISOString(),
            outcome: null,
          },
        ],
      ],
    ]);
    render(<Board issues={[pendingIssue]} agentsByIssueId={agentsMap} />);
    expect(screen.queryByTestId("vendor-swimlanes")).not.toBeInTheDocument();
  });

  it("renders Mark Ready button for in-flight cards when apiUrl/apiKey supplied", () => {
    // Task 6.8: in-flight cards expose a Mark Ready action that adds the
    // pending-approval label and emits a reversible-write audit row.
    render(
      <Board
        issues={[claimedIssue]}
        apiUrl="http://localhost:8081"
        apiKey="test"
      />,
    );
    expect(
      screen.getByTestId(`card-ready-${claimedIssue.id}`),
    ).toBeInTheDocument();
  });

  it("does NOT render Mark Ready button when apiUrl/apiKey are absent", () => {
    render(<Board issues={[claimedIssue]} />);
    expect(
      screen.queryByTestId(`card-ready-${claimedIssue.id}`),
    ).not.toBeInTheDocument();
  });

  it("does NOT render Mark Ready button for non-in-flight cards", () => {
    render(
      <Board
        issues={[pendingIssue, completedRecentIssue]}
        apiUrl="http://localhost:8081"
        apiKey="test"
      />,
    );
    expect(
      screen.queryByTestId(`card-ready-${pendingIssue.id}`),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId(`card-ready-${completedRecentIssue.id}`),
    ).not.toBeInTheDocument();
  });

  it("Mark Ready click PATCHes labels and emits drag-to-ready audit", async () => {
    // Task 6.8: clicking Mark Ready issues PATCH /issues/{id}/labels with
    // add=["pending-approval"] and emits a schema-valid audit row
    // (action=drag-to-ready, class=reversible-write, outcome=confirmed).
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ updated: true }),
    });
    (globalThis as Record<string, unknown>).fetch = fetchMock;

    const audits: Record<string, unknown>[] = [];
    render(
      <Board
        issues={[claimedIssue]}
        apiUrl="http://localhost:8081"
        apiKey="test"
        onAuditEmit={(e) => audits.push(e)}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId(`card-ready-${claimedIssue.id}`));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain(`/issues/${claimedIssue.id}/labels`);
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(String(init.body ?? "{}")) as {
      add: string[];
      remove: string[];
    };
    expect(body.add).toContain("pending-approval");
    expect(body.remove).toEqual([]);

    await waitFor(() => {
      expect(audits.length).toBeGreaterThan(0);
    });
    expect(audits[0]).toMatchObject({
      action: "drag-to-ready",
      class: "reversible-write",
      outcome: "confirmed",
    });
    const args = audits[0].args as Record<string, unknown>;
    expect(args.issue_id).toBe(claimedIssue.id);
    expect(args.added_label).toBe("pending-approval");
  });

  it("Mark Ready emits outcome=failed when PATCH returns !ok", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });
    (globalThis as Record<string, unknown>).fetch = fetchMock;

    const audits: Record<string, unknown>[] = [];
    render(
      <Board
        issues={[claimedIssue]}
        apiUrl="http://localhost:8081"
        apiKey="test"
        onAuditEmit={(e) => audits.push(e)}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId(`card-ready-${claimedIssue.id}`));

    await waitFor(() => {
      expect(audits.length).toBeGreaterThan(0);
    });
    expect(audits[0]).toMatchObject({
      action: "drag-to-ready",
      class: "reversible-write",
      outcome: "failed",
    });
    const args = audits[0].args as Record<string, unknown>;
    expect(args.failure_reason).toBeTruthy();
  });

  it("hides Mark Ready and shows pending-approval badge when label is already set", () => {
    const readyIssue = {
      ...claimedIssue,
      id: "iss-ready",
      labels: [...claimedIssue.labels, "pending-approval"],
    };
    render(
      <Board
        issues={[readyIssue]}
        apiUrl="http://localhost:8081"
        apiKey="test"
      />,
    );
    expect(screen.queryByTestId(`card-ready-${readyIssue.id}`)).not.toBeInTheDocument();
    expect(screen.getByTestId(`card-ready-badge-${readyIssue.id}`)).toBeInTheDocument();
  });

  it("renders consensus indicator (not swimlanes) for completed cards with agents", () => {
    const completedAgents = new Map([
      [
        completedRecentIssue.id,
        [
          {
            agent_id: "wp-backend--claude",
            last_event_at: new Date().toISOString(),
            outcome: "success" as const,
          },
          {
            agent_id: "wp-backend--codex",
            last_event_at: new Date().toISOString(),
            outcome: "success" as const,
          },
        ],
      ],
    ]);
    render(
      <Board issues={[completedRecentIssue]} agentsByIssueId={completedAgents} />,
    );
    expect(screen.getByTestId("consensus-indicator")).toBeInTheDocument();
    expect(screen.getByTestId("consensus-indicator")).toHaveAttribute(
      "data-consensus",
      "pass",
    );
  });
});
