/**
 * Tests for useCoordinator hook.
 * Covers task 3.11: integration test wiring useCoordinator against a mock SSE server.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useCoordinator } from "../hooks/useCoordinator";
import type { SnapshotPayload } from "../lib/coordinator-types";
import { pendingIssue, claimedIssue } from "./fixtures";

// ─────────────────────────────────────────────────────────────────────────────
// Mock globals

const mockAddEventListener = vi.fn();
const mockClose = vi.fn();

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  readyState = MockEventSource.CONNECTING;
  url: string;
  onerror: ((e: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // Expose instance so tests can call callbacks
    (globalThis as Record<string, unknown>).__lastMockEventSource = this;
  }

  addEventListener = mockAddEventListener;
  close = mockClose;

  /** Helper: simulate a snapshot SSE event */
  emitSnapshot(payload: SnapshotPayload) {
    type Call = [string, (e: { data: string }) => void, ...unknown[]];
    const calls = mockAddEventListener.mock.calls as unknown as Call[];
    const handlers = calls
      .filter(([eventName]) => eventName === "snapshot")
      .map(([, handler]) => handler);
    handlers.forEach((h) => h({ data: JSON.stringify(payload) }));
  }
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  mockClose.mockReset();
  mockAddEventListener.mockReset();

  // Mock global EventSource
  (globalThis as Record<string, unknown>).EventSource = MockEventSource;

  // Mock fetch for /events/auth and /issues/list
  fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes("/events/auth")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            token: "mock-jwt-token",
            expires_at: new Date(Date.now() + 300_000).toISOString(),
            aud: "events",
            change_ids: ["abc"],
          }),
      });
    }
    if (String(url).includes("/issues/list")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ issues: [pendingIssue, claimedIssue] }),
      });
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  });
  (globalThis as Record<string, unknown>).fetch = fetchMock;
});

afterEach(() => {
  delete (globalThis as Record<string, unknown>).__lastMockEventSource;
});

describe("useCoordinator — SSE path", () => {
  it("mints an events token before opening SSE", async () => {
    const { unmount } = renderHook(() =>
      useCoordinator({ apiKey: "test-key", changeIds: ["abc"] }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/events/auth"),
        expect.objectContaining({ method: "POST" }),
      );
    });

    unmount();
  });

  it("applies snapshot payload as issues", async () => {
    const snapshot: SnapshotPayload = {
      work_queue: [pendingIssue, claimedIssue],
      active_agents: [],
      subscribed_change_ids: ["abc"],
    };

    const { result, unmount } = renderHook(() =>
      useCoordinator({ apiKey: "test-key", changeIds: ["abc"] }),
    );

    // Wait for EventSource to be created
    await waitFor(() => {
      expect(
        (globalThis as Record<string, unknown>).__lastMockEventSource,
      ).toBeTruthy();
    });

    // Emit snapshot event
    const es = (
      globalThis as Record<string, unknown>
    ).__lastMockEventSource as MockEventSource;
    es.emitSnapshot(snapshot);

    await waitFor(() => {
      expect(result.current.issues).toHaveLength(2);
      expect(result.current.loading).toBe(false);
    });

    unmount();
  });
});

describe("useCoordinator — IMPL_REVIEW F3 multi-change OR semantics", () => {
  it("calls /issues/list once per change_id and merges results (no AND filter)", async () => {
    // IMPL_REVIEW F3 (critical, claude+codex confirmed): multi-change boards
    // require UNION semantics, not the intersection that the prior single
    // call with labels=[change:a, change:b] produced.
    const issueA = { ...pendingIssue, id: "issue-a", labels: ["change:a"] };
    const issueB = { ...pendingIssue, id: "issue-b", labels: ["change:b"] };
    const issueBoth = {
      ...pendingIssue,
      id: "issue-both",
      labels: ["change:a", "change:b"],
    };

    const listCalls: Array<{ labels: string[] }> = [];
    fetchMock.mockReset();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).includes("/events/auth")) {
        return Promise.reject(new Error("force polling"));
      }
      if (String(url).includes("/issues/list")) {
        let body: { labels: string[] } = { labels: [] };
        try {
          body = JSON.parse(String(init?.body ?? "{}")) as {
            labels: string[];
          };
        } catch {
          // ignore — should never happen with our hook
        }
        listCalls.push(body);
        // Simulate backend AND filter (issue_service.py:277-280)
        const requested = new Set(body.labels);
        const pool = [issueA, issueB, issueBoth];
        const filtered = pool.filter((iss) =>
          [...requested].every((lbl) => iss.labels.includes(lbl)),
        );
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ issues: filtered }),
        });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    });

    const { result, unmount } = renderHook(() =>
      // Use a long poll interval so the test doesn't accumulate calls across
      // multiple polls — we want to assert on a single fetchIssues invocation.
      useCoordinator({
        apiKey: "test-key",
        changeIds: ["a", "b"],
        pollIntervalMs: 999_999,
      }),
    );

    await waitFor(() => {
      // Union should contain all three issues (a, b, both).
      expect(result.current.issues).toHaveLength(3);
    });
    const ids = result.current.issues.map((i) => i.id).sort();
    expect(ids).toEqual(["issue-a", "issue-b", "issue-both"]);

    // Each call must carry exactly one label (per-change-id, not combined).
    // After the first poll: 2 list calls (one per change_id).
    expect(listCalls).toHaveLength(2);
    for (const call of listCalls) {
      expect(call.labels).toHaveLength(1);
    }
    const calledLabels = listCalls.map((c) => c.labels[0]).sort();
    expect(calledLabels).toEqual(["change:a", "change:b"]);

    unmount();
  });

  it("returns empty array when changeIds is empty (no fetch)", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/events/auth")) {
        return Promise.reject(new Error("force polling"));
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    });

    const { result, unmount } = renderHook(() =>
      useCoordinator({ apiKey: "test-key", changeIds: [] }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(result.current.issues).toEqual([]);

    unmount();
  });
});

describe("useCoordinator — IMPL_REVIEW claude#13 audit event buffer", () => {
  it("buffers audit events into recentAuditEvents (most-recent-first, cap 20)", async () => {
    const { result, unmount } = renderHook(() =>
      useCoordinator({ apiKey: "test-key", changeIds: ["abc"] }),
    );

    await waitFor(() => {
      expect(
        (globalThis as Record<string, unknown>).__lastMockEventSource,
      ).toBeTruthy();
    });

    const es = (
      globalThis as Record<string, unknown>
    ).__lastMockEventSource as MockEventSource;
    type Call = [string, (e: { data: string }) => void, ...unknown[]];
    const calls = mockAddEventListener.mock.calls as unknown as Call[];
    const auditHandlers = calls
      .filter(([name]) => name === "audit")
      .map(([, h]) => h);
    expect(auditHandlers.length).toBeGreaterThan(0);

    // Emit 25 audit events; expect only the latest 20 retained.
    for (let i = 0; i < 25; i++) {
      auditHandlers.forEach((h) =>
        h({
          data: JSON.stringify({
            audit_id: `audit-${i}`,
            agent_id: "agent-x",
            operation: "test_op",
            args_summary: null,
            ts: new Date().toISOString(),
          }),
        }),
      );
    }

    await waitFor(() => {
      expect(result.current.recentAuditEvents).toHaveLength(20);
    });
    // Most-recent first: latest emission was audit-24
    expect(result.current.recentAuditEvents[0].audit_id).toBe("audit-24");
    // Oldest retained: audit-5 (since we kept the 20 latest of 25)
    expect(result.current.recentAuditEvents[19].audit_id).toBe("audit-5");

    // Hint to suppress unused-locals lint on `es`
    expect(es).toBeTruthy();
    unmount();
  });
});

describe("useCoordinator — IMPL_REVIEW claude#4/gemini#1 transition single state update", () => {
  it("applies transition payload to matching issue without nested setIssues", async () => {
    const initialSnapshot: SnapshotPayload = {
      work_queue: [
        { ...pendingIssue, id: "iss-1", status: "pending" },
        { ...pendingIssue, id: "iss-2", status: "pending" },
      ],
      active_agents: [],
      subscribed_change_ids: ["abc"],
    };

    const { result, unmount } = renderHook(() =>
      useCoordinator({ apiKey: "test-key", changeIds: ["abc"] }),
    );

    await waitFor(() => {
      expect(
        (globalThis as Record<string, unknown>).__lastMockEventSource,
      ).toBeTruthy();
    });

    const es = (
      globalThis as Record<string, unknown>
    ).__lastMockEventSource as MockEventSource;
    es.emitSnapshot(initialSnapshot);
    await waitFor(() => {
      expect(result.current.issues).toHaveLength(2);
    });

    // Emit a transition event for iss-1: pending → claimed
    type Call = [string, (e: { data: string }) => void, ...unknown[]];
    const calls = mockAddEventListener.mock.calls as unknown as Call[];
    const transitionHandlers = calls
      .filter(([name]) => name === "transition")
      .map(([, h]) => h);
    transitionHandlers.forEach((h) =>
      h({
        data: JSON.stringify({
          work_queue_id: "iss-1",
          from: "pending",
          to: "claimed",
          agent_id: "agent-x",
          ts: new Date().toISOString(),
        }),
      }),
    );

    await waitFor(() => {
      const iss1 = result.current.issues.find((i) => i.id === "iss-1");
      expect(iss1?.status).toBe("claimed");
    });
    // iss-2 should remain unchanged
    const iss2 = result.current.issues.find((i) => i.id === "iss-2");
    expect(iss2?.status).toBe("pending");

    unmount();
  });
});

describe("useCoordinator — polling fallback", () => {
  it("falls back to polling when SSE token mint fails", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/events/auth")) {
        return Promise.reject(new Error("SSE unavailable"));
      }
      if (String(url).includes("/issues/list")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ issues: [pendingIssue] }),
        });
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
    });

    const { result, unmount } = renderHook(() =>
      useCoordinator({ apiKey: "test-key", changeIds: ["abc"] }),
    );

    await waitFor(() => {
      // Polling fallback should eventually populate issues
      expect(result.current.issues).toHaveLength(1);
      expect(result.current.loading).toBe(false);
    });

    unmount();
  });
});
