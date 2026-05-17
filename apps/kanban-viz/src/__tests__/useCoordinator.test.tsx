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
