/**
 * Tests for VendorSwimlanes component.
 * Covers tasks 4.1, 4.2, 4.3, 4.4.
 */
import { render, screen, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { VendorSwimlanes, extractVendor } from "../components/VendorSwimlanes";
import type { AgentActivity } from "../components/VendorSwimlanes";

const claudeAgent: AgentActivity = {
  agent_id: "wp-backend--claude",
  last_event_at: new Date(Date.now() - 30_000).toISOString(),
  outcome: null,
};

const codexAgent: AgentActivity = {
  agent_id: "wp-backend--codex",
  last_event_at: new Date(Date.now() - 60_000).toISOString(),
  outcome: null,
};

const antigravityAgent: AgentActivity = {
  agent_id: "wp-backend--antigravity",
  last_event_at: new Date(Date.now() - 90_000).toISOString(),
  outcome: null,
};

const grokAgent: AgentActivity = {
  agent_id: "wp-backend--grok",
  last_event_at: new Date(Date.now() - 120_000).toISOString(),
  outcome: null,
};

const piAgent: AgentActivity = {
  agent_id: "wp-backend--pi",
  last_event_at: new Date(Date.now() - 150_000).toISOString(),
  outcome: null,
};

// Retired harness kept as a fixture on purpose: the component holds no roster
// allow-list (design D5), so a historical `gemini` agent must still render. This
// is the mechanical evidence for the coordinator-kanban-viz "Historical vendor
// still renders" scenario — do not delete it during the roster migration.
const geminiAgent: AgentActivity = {
  agent_id: "wp-backend--gemini",
  last_event_at: new Date(Date.now() - 90_000).toISOString(),
  outcome: null,
};

// ─────────────────────────────────────────────────────────────────────────────
// 4.1: Single-vendor collapses to one lane

describe("VendorSwimlanes — single vendor", () => {
  it("renders a single lane for one agent vendor", () => {
    render(<VendorSwimlanes agents={[claudeAgent]} />);
    expect(screen.getByTestId("swimlane-claude")).toBeInTheDocument();
  });

  it("shows the vendor label in the lane", () => {
    render(<VendorSwimlanes agents={[claudeAgent]} />);
    expect(screen.getByTestId("swimlane-vendor-label-claude")).toHaveTextContent(
      "claude",
    );
  });

  it("shows relative activity timestamp", () => {
    render(<VendorSwimlanes agents={[claudeAgent]} />);
    expect(screen.getByTestId("swimlane-activity-claude")).toHaveTextContent(
      /ago/i,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4.2: Three vendor-diverse agents → three lanes sorted alphabetically

describe("VendorSwimlanes — three vendor-diverse agents", () => {
  it("renders three lanes", () => {
    render(
      <VendorSwimlanes agents={[antigravityAgent, grokAgent, piAgent]} />,
    );
    expect(screen.getByTestId("swimlane-antigravity")).toBeInTheDocument();
    expect(screen.getByTestId("swimlane-grok")).toBeInTheDocument();
    expect(screen.getByTestId("swimlane-pi")).toBeInTheDocument();
  });

  it("lanes are sorted alphabetically", () => {
    render(
      <VendorSwimlanes agents={[grokAgent, antigravityAgent, piAgent]} />,
    );
    const container = screen.getByTestId("vendor-swimlanes");
    const lanes = container.querySelectorAll("[data-testid^='swimlane-vendor-label-']");
    const vendorNames = Array.from(lanes).map((el) => el.textContent);
    expect(vendorNames).toEqual(["antigravity", "grok", "pi"]);
  });

  it("renders the full five-vendor roster mix", () => {
    render(
      <VendorSwimlanes
        agents={[claudeAgent, codexAgent, antigravityAgent, grokAgent, piAgent]}
      />,
    );
    for (const vendor of ["antigravity", "claude", "codex", "grok", "pi"]) {
      expect(screen.getByTestId(`swimlane-${vendor}`)).toBeInTheDocument();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Historical vendor still renders (coordinator-kanban-viz): the component
// consults no roster allow-list (design D5), so a retired `gemini` agent renders
// exactly like any current vendor.

describe("VendorSwimlanes — historical vendor", () => {
  it("still renders a lane for a retired vendor (no allow-list)", () => {
    render(<VendorSwimlanes agents={[geminiAgent]} />);
    expect(screen.getByTestId("swimlane-gemini")).toBeInTheDocument();
    expect(screen.getByTestId("swimlane-vendor-label-gemini")).toHaveTextContent(
      "gemini",
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4.3: Lane updates when audit event arrives (within 200ms)

describe("VendorSwimlanes — live activity update", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("updates lane activity when re-rendered with new event timestamp", async () => {
    const { rerender } = render(<VendorSwimlanes agents={[claudeAgent]} />);

    const newAgent: AgentActivity = {
      ...claudeAgent,
      last_event_at: new Date().toISOString(),
    };

    // Simulate SSE audit event arriving — component is re-rendered with fresh data
    await act(async () => {
      rerender(<VendorSwimlanes agents={[newAgent]} />);
    });

    expect(screen.getByTestId("swimlane-activity-claude")).toHaveTextContent(
      /just now|0s ago/i,
    );
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4.4: Completed work-package collapses to consensus indicator

describe("VendorSwimlanes — consensus indicator", () => {
  const successAgents: AgentActivity[] = [
    { ...claudeAgent, outcome: "success" },
    { ...codexAgent, outcome: "success" },
  ];

  const failedAgents: AgentActivity[] = [
    { ...claudeAgent, outcome: "success" },
    { ...codexAgent, outcome: "failure" },
  ];

  it("shows checkmark (✓) when all agents succeeded", () => {
    render(<VendorSwimlanes agents={successAgents} completed />);
    const indicator = screen.getByTestId("consensus-indicator");
    expect(indicator).toHaveTextContent("✓");
    expect(indicator).toHaveAttribute("data-consensus", "pass");
  });

  it("shows cross (✗) when any agent failed", () => {
    render(<VendorSwimlanes agents={failedAgents} completed />);
    const indicator = screen.getByTestId("consensus-indicator");
    expect(indicator).toHaveTextContent("✗");
    expect(indicator).toHaveAttribute("data-consensus", "fail");
  });

  it("does NOT render swimlane rows when completed", () => {
    render(<VendorSwimlanes agents={successAgents} completed />);
    expect(screen.queryByTestId("vendor-swimlanes")).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// extractVendor unit tests

describe("extractVendor", () => {
  it("extracts suffix after -- delimiter", () => {
    expect(extractVendor("wp-backend--claude")).toBe("claude");
    expect(extractVendor("wp-db--codex")).toBe("codex");
    expect(extractVendor("wp-test--chatgpt-pro")).toBe("chatgpt-pro");
  });

  it("returns full agent_id when no -- delimiter", () => {
    expect(extractVendor("plain-agent")).toBe("plain-agent");
  });

  it("uses the last -- segment for double-hyphen ids", () => {
    expect(extractVendor("wp-a--wp-b--gemini")).toBe("gemini");
  });
});
