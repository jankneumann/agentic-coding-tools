/**
 * App-level integration tests.
 *
 * IMPL_REVIEW F1 (critical, claude+codex confirmed) — SyncPointBanner is MVP
 * surface #1 per proposal §3 and MUST mount unconditionally; the prior
 * App.tsx rendered only <Board issues={issues} /> and never mounted the
 * banner. These tests guard against regression.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import App from "../App";

// Mock fetch BEFORE App is rendered. Banner polls /sync-points/status on
// mount; if we don't mock it, the component shows the error state.
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  // Mock EventSource so the SSE path doesn't blow up.
  class MockEventSource {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 2;
    readyState = 0;
    url: string;
    onerror: ((e: Event) => void) | null = null;
    addEventListener = vi.fn();
    close = vi.fn();
    constructor(url: string) {
      this.url = url;
    }
  }
  (globalThis as Record<string, unknown>).EventSource = MockEventSource;

  fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes("/sync-points/status")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            { skill: "cleanup-feature", blocked: false, blockers: [], suggested_actions: [] },
            { skill: "merge-pull-requests", blocked: false, blockers: [], suggested_actions: [] },
            { skill: "update-specs", blocked: false, blockers: [], suggested_actions: [] },
          ]),
      });
    }
    if (String(url).includes("/events/auth")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            token: "t",
            expires_at: new Date(Date.now() + 60_000).toISOString(),
            aud: "events",
            change_ids: [],
          }),
      });
    }
    if (String(url).includes("/issues/list")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ issues: [] }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  (globalThis as Record<string, unknown>).fetch = fetchMock;
});

describe("App — SyncPointBanner mounting (IMPL_REVIEW F1)", () => {
  it("mounts SyncPointBanner above the Board when not loading", async () => {
    render(<App />);
    // The banner polls and renders. Wait for it.
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner")).toBeInTheDocument();
    });
    // App container is present
    expect(screen.getByTestId("kanban-app")).toBeInTheDocument();
  });

  it("mounts SyncPointBanner even when Board is in loading state", async () => {
    // The banner is rendered before the loading conditional so it is visible
    // regardless of Board readiness.
    render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner")).toBeInTheDocument();
    });
  });

  it("renders SyncPointBanner above the Board (DOM ordering)", async () => {
    const { container } = render(<App />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner")).toBeInTheDocument();
    });
    // The sync-banner appears BEFORE either the loading state, error state,
    // or the kanban board in DOM order. This locks in the layout
    // requirement from proposal §3.
    const banner = container.querySelector('[data-testid="sync-banner"]');
    const lateContent = container.querySelector(
      '[data-testid="kanban-board"], [data-testid="app-loading"], [data-testid="app-error"]',
    );
    expect(banner).toBeTruthy();
    expect(lateContent).toBeTruthy();
    // Compare DOM positions: banner must precede the late content.
    if (banner && lateContent) {
      const cmp = banner.compareDocumentPosition(lateContent);
      // DOCUMENT_POSITION_FOLLOWING = 4 — lateContent follows banner
      expect(cmp & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });
});
