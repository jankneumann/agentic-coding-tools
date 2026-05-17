/**
 * Tests for SyncPointBanner and ConsentPrompt components.
 * Covers tasks 5.1, 5.2, 5.3, 5.4.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SyncPointBanner } from "../components/SyncPointBanner";
import type { SyncPointStatus } from "../lib/coordinator-types";

const clearStatuses: SyncPointStatus[] = [
  { skill: "cleanup-feature", blocked: false, blockers: [], suggested_actions: [] },
  { skill: "merge-pull-requests", blocked: false, blockers: [], suggested_actions: [] },
  { skill: "update-specs", blocked: false, blockers: [], suggested_actions: [] },
];

const blockedStatuses: SyncPointStatus[] = [
  {
    skill: "cleanup-feature",
    blocked: true,
    blockers: [
      {
        agent_id: "agent-42",
        last_heartbeat_iso: new Date(Date.now() - 5 * 60_000).toISOString(),
      },
    ],
    suggested_actions: ["wait", "kick:agent-42"],
  },
  { skill: "merge-pull-requests", blocked: false, blockers: [], suggested_actions: [] },
  { skill: "update-specs", blocked: false, blockers: [], suggested_actions: [] },
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock = vi.fn().mockImplementation((url: string) => {
    if (String(url).includes("/sync-points/status")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(clearStatuses),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  (globalThis as Record<string, unknown>).fetch = fetchMock;
});

// ─────────────────────────────────────────────────────────────────────────────
// 5.1: All clear → single-line green status

describe("SyncPointBanner — all clear", () => {
  it("renders a clear indicator when all sync-points are unblocked", async () => {
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-clear")).toBeInTheDocument();
    });
    expect(screen.getByTestId("sync-banner-clear")).toHaveTextContent(
      "All sync-points clear",
    );
  });

  it("sets data-blocked=false when all clear", async () => {
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner")).toHaveAttribute(
        "data-blocked",
        "false",
      );
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5.2: Blocked sync-point → row with skill, blocker count, heartbeat age

describe("SyncPointBanner — blocked", () => {
  beforeEach(() => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/sync-points/status")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(blockedStatuses),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it("shows blocked skill name", async () => {
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-skill-cleanup-feature")).toBeInTheDocument();
    });
    expect(screen.getByTestId("sync-banner-skill-cleanup-feature")).toHaveTextContent(
      "cleanup-feature",
    );
  });

  it("shows blocker count", async () => {
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("sync-banner-blocker-count-cleanup-feature"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("sync-banner-blocker-count-cleanup-feature"),
    ).toHaveTextContent("1 blocker");
  });

  it("shows heartbeat age for each blocker", async () => {
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-heartbeat-agent-42")).toBeInTheDocument();
    });
    expect(screen.getByTestId("sync-banner-heartbeat-agent-42")).toHaveTextContent(
      /ago/i,
    );
  });

  it("shows Kick button for each blocker", async () => {
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-kick-agent-42")).toBeInTheDocument();
    });
    expect(screen.getByTestId("sync-banner-kick-agent-42")).toHaveTextContent(
      /kick/i,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5.3: Kick click → consent prompt → confirm fires kick API

describe("SyncPointBanner — kick with consent", () => {
  beforeEach(() => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/sync-points/status")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(blockedStatuses),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it("shows consent prompt after clicking Kick", async () => {
    const user = userEvent.setup();
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-kick-agent-42")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("sync-banner-kick-agent-42"));
    expect(screen.getByTestId("consent-prompt")).toBeInTheDocument();
  });

  it("fires kick API only after clicking Confirm", async () => {
    const user = userEvent.setup();
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-kick-agent-42")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("sync-banner-kick-agent-42"));
    // Kick API not called yet
    type FetchCall = [string, ...unknown[]];
    const kickCallsBefore = (fetchMock.mock.calls as unknown as FetchCall[]).filter(
      ([url]) => String(url).includes("/agents/"),
    ).length;
    expect(kickCallsBefore).toBe(0);

    await user.click(screen.getByTestId("consent-confirm"));
    // Kick API called after confirm
    await waitFor(() => {
      const kickCalls = (fetchMock.mock.calls as unknown as FetchCall[]).filter(
        ([url]) => String(url).includes("/agents/agent-42/kick"),
      );
      expect(kickCalls.length).toBeGreaterThan(0);
    });
  });

  it("does NOT fire kick API when clicking Cancel (decline)", async () => {
    const user = userEvent.setup();
    render(<SyncPointBanner apiKey="test" />);
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-kick-agent-42")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("sync-banner-kick-agent-42"));
    await user.click(screen.getByTestId("consent-decline"));

    // No kick API calls
    type FetchCall2 = [string, ...unknown[]];
    const kickCalls = (fetchMock.mock.calls as unknown as FetchCall2[]).filter(
      ([url]) => String(url).includes("/agents/"),
    );
    expect(kickCalls.length).toBe(0);

    // Consent prompt dismissed
    expect(screen.queryByTestId("consent-prompt")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5.4: Audit emitted regardless of confirm/decline

describe("SyncPointBanner — audit emission", () => {
  beforeEach(() => {
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes("/sync-points/status")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(blockedStatuses),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
  });

  it("emits audit event when Kick is clicked (before consent)", async () => {
    const user = userEvent.setup();
    const auditEvents: Record<string, unknown>[] = [];
    render(
      <SyncPointBanner
        apiKey="test"
        onAuditEmit={(e) => auditEvents.push(e)}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-kick-agent-42")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("sync-banner-kick-agent-42"));
    expect(auditEvents.length).toBeGreaterThan(0);
    expect(auditEvents[0]).toMatchObject({
      action: expect.stringContaining("kick"),
      agent_id: "agent-42",
    });
  });

  it("emits audit event on decline", async () => {
    const user = userEvent.setup();
    const auditEvents: Record<string, unknown>[] = [];
    render(
      <SyncPointBanner
        apiKey="test"
        onAuditEmit={(e) => auditEvents.push(e)}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("sync-banner-kick-agent-42")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("sync-banner-kick-agent-42"));
    auditEvents.length = 0; // clear initiation event
    await user.click(screen.getByTestId("consent-decline"));

    expect(auditEvents.length).toBeGreaterThan(0);
    expect(auditEvents[0]).toMatchObject({
      outcome: "cancelled",
    });
  });
});
