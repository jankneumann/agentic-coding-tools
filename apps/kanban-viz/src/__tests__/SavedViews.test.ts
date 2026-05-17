/**
 * Tests for saved-view functionality and reversibility classifier.
 * Covers tasks 6.1, 6.2, 6.3, 6.4, 6.9.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { saveView } from "../lib/saveView";
import { classify, classifyOrDefault, requiresConsent } from "../lib/reversibility";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: () =>
      Promise.resolve({
        saved: true,
        path: "docs/kanban-viz/saved-views/my-view.json",
        git_sha: "abc1234",
      }),
  });
  (globalThis as Record<string, unknown>).fetch = fetchMock;
  // Ensure window.__TAURI__ is not set (browser path)
  if (typeof window !== "undefined") {
    delete (window as unknown as Record<string, unknown>).__TAURI__;
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 6.1: saveView sends correct request and returns saved result

describe("saveView — browser path", () => {
  it("calls PUT /kanban-viz/saved-views/{slug} with correct body", async () => {
    await saveView(
      "my-view",
      { name: "My View", filters: { status: "running" } },
      "http://localhost:8081",
      "test-key",
    );

    const calls = fetchMock.mock.calls;
    expect(calls.length).toBe(1);
    const [url, options] = calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8081/kanban-viz/saved-views/my-view");
    expect(options.method).toBe("PUT");

    const body = JSON.parse(String(options.body)) as {
      view: { name: string; filters: Record<string, unknown> };
    };
    expect(body.view.name).toBe("My View");
    expect(body.view.filters).toEqual({ status: "running" });
  });

  it("returns {saved: true, path, git_sha} from coordinator response", async () => {
    const result = await saveView(
      "my-view",
      { name: "Test", filters: {} },
      "http://localhost:8081",
      "test-key",
    );

    expect(result.saved).toBe(true);
    expect(result.path).toContain("my-view.json");
    expect(result.git_sha).toBe("abc1234");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6.2: Re-save under same slug (idempotent PUT)

describe("saveView — re-save", () => {
  it("sends a second PUT for the same slug (overwrite)", async () => {
    const view = { name: "Same Slug", filters: {} };
    await saveView("same-slug", view, "http://localhost:8081", "key");
    await saveView("same-slug", view, "http://localhost:8081", "key");

    type FetchCall = [string, ...unknown[]];
    const calls = (fetchMock.mock.calls as unknown as FetchCall[]).filter(
      ([url]) => String(url).includes("same-slug"),
    );
    expect(calls.length).toBe(2);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6.3: save-view audit (via fetch to POST /kanban-viz/audit — callers emit audit)

describe("saveView — audit emission contract", () => {
  it("classifies save-view as reversible-write", () => {
    expect(classify("save-view")).toBe("reversible-write");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6.4: drag-to-Ready classified as reversible-write

describe("reversibility classifier", () => {
  it("classifies drag-to-ready as reversible-write", () => {
    expect(classify("drag-to-ready")).toBe("reversible-write");
  });

  it("classifies kick-agent as destructive-write", () => {
    expect(classify("kick-agent")).toBe("destructive-write");
  });

  it("classifies force-release-lock as destructive-write", () => {
    expect(classify("force-release-lock")).toBe("destructive-write");
  });

  it("classifies panel-open as ephemeral-event", () => {
    expect(classify("panel-open")).toBe("ephemeral-event");
  });

  it("requiresConsent is true for destructive-write actions", () => {
    expect(requiresConsent("kick-agent")).toBe(true);
    expect(requiresConsent("force-release-lock")).toBe(true);
  });

  it("requiresConsent is false for reversible-write actions", () => {
    expect(requiresConsent("save-view")).toBe(false);
    expect(requiresConsent("drag-to-ready")).toBe(false);
  });

  it("classifyOrDefault returns ephemeral-event for unknown keys", () => {
    expect(classifyOrDefault("unknown-action")).toBe("ephemeral-event");
  });
});
