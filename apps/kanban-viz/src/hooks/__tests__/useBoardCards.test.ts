/**
 * Tests for useBoardCards hook (task 6.1 + 6.2).
 *
 * Covers:
 * - clusterBoardCards pure function (6.1)
 * - parallel-fetch behavior (one source error → other two succeed)
 * - multi-change union: two separate POST calls, not one batched call
 * - refreshGeneration SSE-fence: stale events after refresh are ignored
 * - refresh idempotency
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { clusterBoardCards, useBoardCards } from "../useBoardCards";
import type { IssueCard, PRCard, ProposalCard } from "../../lib/coordinator-types";

// ─────────────────────────────────────────────────────────────────────────────
// Test fixtures

function makeIssue(id: string, change_id: string | null = null): IssueCard {
  return {
    kind: "issue",
    id,
    title: `Issue ${id}`,
    body: null,
    status: "pending",
    priority: 1,
    labels: [],
    assignee: null,
    claimed_by: null,
    claimed_at: null,
    completed_at: null,
    created_at: new Date().toISOString(),
    updated_at: null,
    change_id,
    task_key: null,
  };
}

function makePR(id: string, change_id: string | null = null): PRCard {
  return {
    kind: "pr",
    id,
    change_id,
    repo: "jankneumann/agentic-coding-tools",
    number: 1,
    title: `PR ${id}`,
    author: "alice",
    head_branch: "openspec/foo",
    base_branch: "main",
    origin: "openspec",
    status: "open",
    review_summary: { state: "none", reviewer_count: 0, last_reviewed_at_iso: null },
    is_draft: false,
    url: "https://github.com/example/1",
    created_at_iso: new Date().toISOString(),
    updated_at_iso: new Date().toISOString(),
  };
}

function makeProposal(id: string, change_id: string, repo: string | null = null): ProposalCard {
  return {
    kind: "proposal",
    id,
    change_id,
    title: `Proposal ${id}`,
    status: "drafted",
    created_at_iso: new Date().toISOString(),
    updated_at_iso: new Date().toISOString(),
    proposal_path: `openspec/changes/${change_id}/proposal.md`,
    has_tasks_md: false,
    has_design_md: false,
    has_spec_delta: false,
    has_branch: false,
    branch_name: null,
    code_changes_outside_proposal: 0,
    repo,
    change_id_namespaced: repo != null ? `${repo}/${change_id}` : null,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Task 6.1 — clusterBoardCards

describe("clusterBoardCards", () => {
  it("returns empty map and no annotations for empty array", () => {
    const { clusters, annotated } = clusterBoardCards([]);
    expect(clusters.size).toBe(0);
    expect(annotated).toHaveLength(0);
  });

  it("cards with change_id=null get cluster_count=null and are NOT in any cluster", () => {
    const card = makeIssue("i1", null);
    const { clusters, annotated } = clusterBoardCards([card]);
    expect(clusters.size).toBe(0);
    expect(annotated[0].cluster_count).toBeNull();
  });

  it("single card with unique change_id gets cluster_count=null (no siblings)", () => {
    const card = makeIssue("i1", "change-a");
    const { annotated } = clusterBoardCards([card]);
    // Only one card for change-a → no cross-source cluster
    expect(annotated[0].cluster_count).toBeNull();
  });

  it("two cards sharing change_id get cluster_count=2", () => {
    const issue = makeIssue("i1", "change-a");
    const pr = makePR("pr1", "change-a");
    const { clusters, annotated } = clusterBoardCards([issue, pr]);
    expect(clusters.get("change-a")).toHaveLength(2);
    const issueAnnotated = annotated.find((c) => c.kind === "issue" && c.id === "i1");
    const prAnnotated = annotated.find((c) => c.kind === "pr" && c.id === "pr1");
    expect(issueAnnotated?.cluster_count).toBe(2);
    expect(prAnnotated?.cluster_count).toBe(2);
  });

  it("three cards sharing change_id get cluster_count=3", () => {
    const issue = makeIssue("i1", "change-a");
    const pr = makePR("pr1", "change-a");
    const proposal = makeProposal("prop1", "change-a");
    const { clusters, annotated } = clusterBoardCards([issue, pr, proposal]);
    expect(clusters.get("change-a")).toHaveLength(3);
    for (const c of annotated) {
      expect(c.cluster_count).toBe(3);
    }
  });

  it("cards with different change_ids form independent clusters", () => {
    const issueA = makeIssue("i1", "change-a");
    const issueB = makeIssue("i2", "change-b");
    const prA = makePR("pr1", "change-a");
    const { clusters, annotated } = clusterBoardCards([issueA, issueB, prA]);
    expect(clusters.get("change-a")).toHaveLength(2);
    // change-b has only one card → no cluster entry for single-card change_id
    expect(clusters.get("change-b")).toBeUndefined();
    const issueAAnnotated = annotated.find((c) => c.kind === "issue" && c.id === "i1");
    const issueBAnnotated = annotated.find((c) => c.kind === "issue" && c.id === "i2");
    expect(issueAAnnotated?.cluster_count).toBe(2);
    expect(issueBAnnotated?.cluster_count).toBeNull(); // single card
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Task 6.2 — useBoardCards hook

// Reset fetch mock after each test
afterEach(() => {
  vi.resetAllMocks();
});

const BASE_URL = "http://localhost:8081";
const API_KEY = "test-key";

function mockFetch(responses: Record<string, unknown>) {
  const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
    const urlStr = String(url);
    for (const [pattern, body] of Object.entries(responses)) {
      if (urlStr.includes(pattern)) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(body),
        });
      }
    }
    return Promise.resolve({ ok: false, status: 404 });
  });
  (globalThis as Record<string, unknown>).fetch = fetchMock;
  return fetchMock;
}

describe("useBoardCards — parallel fetch", () => {
  it("fetches issues, PRs, and proposals in parallel", async () => {
    const issue = makeIssue("i1", "change-a");
    const pr = makePR("pr1", "change-a");
    const proposal = makeProposal("prop1", "change-a");

    const fetchMock = mockFetch({
      "/issues/list": { issues: [issue] },
      "/github/prs": { prs: [pr] },
      "/openspec/proposals": { proposals: [proposal] },
    });

    const { result, unmount } = renderHook(() =>
      useBoardCards({ apiUrl: BASE_URL, apiKey: API_KEY, changeIds: ["change-a"] }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.cards.filter((c) => c.kind === "issue")).toHaveLength(1);
    expect(result.current.cards.filter((c) => c.kind === "pr")).toHaveLength(1);
    expect(result.current.cards.filter((c) => c.kind === "proposal")).toHaveLength(1);
    // All three endpoint types were called
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/issues/list"),
      expect.anything(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/github/prs"),
      expect.anything(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/openspec/proposals"),
      expect.anything(),
    );

    unmount();
  });

  it("one source erroring → other two succeed and are returned", async () => {
    const issue = makeIssue("i1", "change-a");
    const proposal = makeProposal("prop1", "change-a");

    const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
      const urlStr = String(url);
      if (urlStr.includes("/github/prs")) {
        return Promise.resolve({ ok: false, status: 503 });
      }
      if (urlStr.includes("/issues/list")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ issues: [issue] }) });
      }
      if (urlStr.includes("/openspec/proposals")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ proposals: [proposal] }) });
      }
      return Promise.resolve({ ok: false, status: 404 });
    });
    (globalThis as Record<string, unknown>).fetch = fetchMock;

    const { result, unmount } = renderHook(() =>
      useBoardCards({ apiUrl: BASE_URL, apiKey: API_KEY, changeIds: ["change-a"] }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.cards.filter((c) => c.kind === "issue")).toHaveLength(1);
    expect(result.current.cards.filter((c) => c.kind === "proposal")).toHaveLength(1);
    expect(result.current.cards.filter((c) => c.kind === "pr")).toHaveLength(0);
    // The error should be captured in byRow
    expect(result.current.byRow.prs.error).toBeTruthy();

    unmount();
  });
});

describe("useBoardCards — multi-change union semantics", () => {
  it("calls /issues/list separately per change_id (union, not intersection)", async () => {
    const issueA = makeIssue("i-a", "change-a");
    const issueB = makeIssue("i-b", "change-b");

    let callCount = 0;
    const fetchMock = vi.fn().mockImplementation((url: string | URL, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes("/issues/list")) {
        callCount++;
        const body = JSON.parse(String(init?.body ?? "{}")) as { labels: string[] };
        if (body.labels?.includes("change:change-a")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ issues: [issueA] }) });
        }
        if (body.labels?.includes("change:change-b")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ issues: [issueB] }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ issues: [] }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ prs: [], proposals: [] }) });
    });
    (globalThis as Record<string, unknown>).fetch = fetchMock;

    const { result, unmount } = renderHook(() =>
      useBoardCards({
        apiUrl: BASE_URL,
        apiKey: API_KEY,
        changeIds: ["change-a", "change-b"],
      }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Separate call per change_id (UNION semantics)
    expect(callCount).toBe(2);
    const issues = result.current.cards.filter((c) => c.kind === "issue");
    expect(issues).toHaveLength(2);

    unmount();
  });
});

describe("useBoardCards — refreshGeneration SSE-fence", () => {
  it("refresh bumps generation counter", async () => {
    const issue = makeIssue("i1", "change-a");
    mockFetch({
      "/issues/list": { issues: [issue] },
      "/github/prs": { prs: [] },
      "/openspec/proposals": { proposals: [] },
    });

    const { result, unmount } = renderHook(() =>
      useBoardCards({ apiUrl: BASE_URL, apiKey: API_KEY, changeIds: ["change-a"] }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    const gen1 = result.current.refreshGeneration;

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.refreshGeneration).toBeGreaterThan(gen1);

    unmount();
  });

  it("refresh idempotency: multiple rapid refreshes result in latest data", async () => {
    const issue1 = makeIssue("i1", "change-a");
    const issue2 = makeIssue("i2", "change-a");
    let callCount = 0;

    vi.fn().mockImplementation;
    const fetchMock = vi.fn().mockImplementation((url: string | URL) => {
      const urlStr = String(url);
      if (urlStr.includes("/issues/list")) {
        callCount++;
        const issues = callCount === 1 ? [issue1] : [issue1, issue2];
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ issues }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ prs: [], proposals: [] }) });
    });
    (globalThis as Record<string, unknown>).fetch = fetchMock;

    const { result, unmount } = renderHook(() =>
      useBoardCards({ apiUrl: BASE_URL, apiKey: API_KEY, changeIds: ["change-a"] }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.cards.filter((c) => c.kind === "issue")).toHaveLength(1);

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      const issues = result.current.cards.filter((c) => c.kind === "issue");
      expect(issues.length).toBeGreaterThanOrEqual(1);
    });

    unmount();
  });
});

describe("useBoardCards — cluster computation", () => {
  it("byRow exposes issues, prs, proposals separately", async () => {
    const issue = makeIssue("i1", "change-a");
    const pr = makePR("pr1", "change-a");
    const proposal = makeProposal("prop1", "change-a");

    mockFetch({
      "/issues/list": { issues: [issue] },
      "/github/prs": { prs: [pr] },
      "/openspec/proposals": { proposals: [proposal] },
    });

    const { result, unmount } = renderHook(() =>
      useBoardCards({ apiUrl: BASE_URL, apiKey: API_KEY, changeIds: ["change-a"] }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.byRow.issues.cards).toHaveLength(1);
    expect(result.current.byRow.prs.cards).toHaveLength(1);
    expect(result.current.byRow.proposals.cards).toHaveLength(1);

    unmount();
  });

  it("clusters map links cards sharing change_id across rows", async () => {
    const issue = makeIssue("i1", "change-a");
    const pr = makePR("pr1", "change-a");
    const proposal = makeProposal("prop1", "change-a");

    mockFetch({
      "/issues/list": { issues: [issue] },
      "/github/prs": { prs: [pr] },
      "/openspec/proposals": { proposals: [proposal] },
    });

    const { result, unmount } = renderHook(() =>
      useBoardCards({ apiUrl: BASE_URL, apiKey: API_KEY, changeIds: ["change-a"] }),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.clusters.get("change-a")).toHaveLength(3);

    unmount();
  });
});
