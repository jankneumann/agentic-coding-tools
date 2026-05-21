/**
 * Tests for SaveViewButton (task 6.7 reduced scope: save-only UI surface).
 *
 * Verifies the button:
 *   - prompts for a name and slugifies it
 *   - calls saveView (browser path → PUT /kanban-viz/saved-views/{slug})
 *   - emits a schema-valid audit event (action=save-view, class=reversible-write)
 *   - surfaces an error message when saveView throws
 *   - rejects invalid names client-side before hitting the API
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SaveViewButton } from "../components/SaveViewButton";

let fetchMock: ReturnType<typeof vi.fn>;
// Loose typing for the prompt spy — vitest's MockContext narrows the
// signature in ways that don't compose with the precise window.prompt
// overloads. We only care about return-value mocking + restore, not the
// full mock context.
let promptSpy: { mockRestore: () => void } | null = null;

beforeEach(() => {
  vi.clearAllMocks();
  fetchMock = vi.fn();
  (globalThis as Record<string, unknown>).fetch = fetchMock;
});

afterEach(() => {
  promptSpy?.mockRestore();
  promptSpy = null;
});

describe("SaveViewButton — save flow", () => {
  it("prompts for a name, calls saveView, emits schema-valid reversible-write audit", async () => {
    promptSpy = vi.spyOn(window, "prompt").mockReturnValue("Q1 Review");
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        saved: true,
        path: "docs/kanban-viz/saved-views/q1-review.json",
        git_sha: "abc1234",
      }),
    });
    const audits: Record<string, unknown>[] = [];

    render(
      <SaveViewButton
        apiUrl="http://localhost:8081"
        apiKey="test"
        currentFilters={{ change_ids: ["a", "b"] }}
        onAuditEmit={(e) => audits.push(e)}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("save-view-button"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    // Slugified from "Q1 Review" → "q1-review"
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/kanban-viz/saved-views/q1-review");
    expect(init.method).toBe("PUT");
    const body = JSON.parse(String(init.body ?? "{}")) as {
      view: { name: string; filters: Record<string, unknown> };
    };
    expect(body.view.name).toBe("Q1 Review");
    expect(body.view.filters).toEqual({ change_ids: ["a", "b"] });

    // Audit event schema: action=save-view, class=reversible-write,
    // outcome=confirmed (success), args carries slug + path + git_sha.
    await waitFor(() => {
      expect(audits.length).toBeGreaterThan(0);
    });
    expect(audits[0]).toMatchObject({
      action: "save-view",
      class: "reversible-write",
      outcome: "confirmed",
    });
    const args = audits[0].args as Record<string, unknown>;
    expect(args.slug).toBe("q1-review");
    expect(args.path).toContain("q1-review.json");
    expect(args.git_sha).toBe("abc1234");
  });

  it("emits outcome=failed with failure_reason when saveView rejects", async () => {
    promptSpy = vi.spyOn(window, "prompt").mockReturnValue("backend-blew-up");
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: "internal error" }),
    });
    const audits: Record<string, unknown>[] = [];

    render(
      <SaveViewButton
        apiUrl="http://localhost:8081"
        apiKey="test"
        currentFilters={{}}
        onAuditEmit={(e) => audits.push(e)}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("save-view-button"));

    await waitFor(() => {
      expect(audits.length).toBeGreaterThan(0);
    });
    expect(audits[0]).toMatchObject({
      action: "save-view",
      class: "reversible-write",
      outcome: "failed",
    });
    const args = audits[0].args as Record<string, unknown>;
    expect(args.failure_reason).toBeTruthy();
    expect(screen.getByTestId("save-view-error")).toBeInTheDocument();
  });

  it("does NOT call saveView when the user cancels the prompt", async () => {
    promptSpy = vi.spyOn(window, "prompt").mockReturnValue(null);
    const audits: Record<string, unknown>[] = [];

    render(
      <SaveViewButton
        apiUrl="http://localhost:8081"
        apiKey="test"
        currentFilters={{}}
        onAuditEmit={(e) => audits.push(e)}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("save-view-button"));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(audits).toHaveLength(0);
  });

  it("rejects invalid names client-side without an audit emission", async () => {
    // Slug pattern is ^[a-z0-9][a-z0-9-]{0,63}$ — punctuation-only would
    // strip down to "" after slugify().
    promptSpy = vi.spyOn(window, "prompt").mockReturnValue("!!!");
    const audits: Record<string, unknown>[] = [];

    render(
      <SaveViewButton
        apiUrl="http://localhost:8081"
        apiKey="test"
        currentFilters={{}}
        onAuditEmit={(e) => audits.push(e)}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("save-view-button"));

    expect(fetchMock).not.toHaveBeenCalled();
    // No audit event since we never attempted the save.
    expect(audits).toHaveLength(0);
    expect(screen.getByTestId("save-view-error")).toBeInTheDocument();
  });
});
