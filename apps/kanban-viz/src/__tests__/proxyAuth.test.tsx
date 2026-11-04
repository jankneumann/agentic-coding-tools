/**
 * The GX-10 deployment: the board is served under /kanban/ behind Caddy
 * basic_auth, and Caddy injects the coordinator key. Built with
 * VITE_COORDINATOR_URL=/kanban/api, VITE_COORDINATOR_AUTH=proxy, no key.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Board } from "../components/Board";
import { authHeaders, canAuthenticate, endpoint } from "../lib/coordinatorAuth";
import { claimedIssue } from "./fixtures";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("proxy-authenticated deployment", () => {
  it("sends no Authorization header without a key", () => {
    // An explicit header replaces the browser's cached Basic credentials,
    // so Caddy's basic_auth would reject every API call.
    expect(authHeaders("")).toEqual({});
    expect(authHeaders(undefined)).toEqual({});
    expect(authHeaders("k")).toEqual({ Authorization: "Bearer k" });
  });

  it("resolves a same-origin relative API URL", () => {
    // new URL("/kanban/api/github/prs") throws without a base.
    const url = endpoint("/kanban/api", "/github/prs");
    expect(url.pathname).toBe("/kanban/api/github/prs");
    expect(url.origin).toBe(window.location.origin);
    expect(endpoint("http://localhost:8081", "/events/work").toString()).toBe(
      "http://localhost:8081/events/work",
    );
  });

  it("treats the proxy as able to authenticate writes", () => {
    expect(canAuthenticate("")).toBe(false);
    vi.stubEnv("VITE_COORDINATOR_AUTH", "proxy");
    expect(canAuthenticate("")).toBe(true);
  });

  it("offers Mark Ready and PATCHes without a key header", async () => {
    vi.stubEnv("VITE_COORDINATOR_AUTH", "proxy");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    render(<Board issues={[claimedIssue]} apiUrl="/kanban/api" apiKey="" />);
    await userEvent.click(screen.getByTestId(`card-ready-${claimedIssue.id}`));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/kanban/api/issues/${claimedIssue.id}/labels`);
    expect(init.headers).not.toHaveProperty("Authorization");
  });
});
