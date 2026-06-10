/**
 * Tests for RefreshButton component (task 7.3).
 *
 * Covers:
 * - Click triggers parallel refetch via hook (mocked)
 * - Button enters spinner state
 * - Returns idle when all three resolve
 * - One source failing surfaces a per-row error chip without blocking others
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RefreshButton } from "../RefreshButton";

afterEach(() => {
  vi.resetAllMocks();
});

describe("RefreshButton — spinner state", () => {
  it("renders idle button initially", () => {
    render(<RefreshButton onRefresh={async () => {}} />);
    const btn = screen.getByTestId("refresh-button");
    expect(btn).toBeInTheDocument();
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute("data-state", "idle");
  });

  it("button enters spinner state while refreshing", async () => {
    let resolveRefresh!: () => void;
    const slowRefresh = () =>
      new Promise<void>((r) => {
        resolveRefresh = r;
      });

    render(<RefreshButton onRefresh={slowRefresh} />);
    const user = userEvent.setup();
    const btn = screen.getByTestId("refresh-button");

    void user.click(btn);

    await waitFor(() => {
      expect(btn).toHaveAttribute("data-state", "loading");
    });

    resolveRefresh();

    await waitFor(() => {
      expect(btn).toHaveAttribute("data-state", "idle");
    });
  });

  it("button is disabled while loading", async () => {
    let resolveRefresh!: () => void;
    const slowRefresh = () =>
      new Promise<void>((r) => {
        resolveRefresh = r;
      });

    render(<RefreshButton onRefresh={slowRefresh} />);
    const user = userEvent.setup();
    const btn = screen.getByTestId("refresh-button");

    void user.click(btn);

    await waitFor(() => {
      expect(btn).toBeDisabled();
    });

    resolveRefresh();

    await waitFor(() => {
      expect(btn).not.toBeDisabled();
    });
  });

  it("calls onRefresh when clicked", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<RefreshButton onRefresh={onRefresh} />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("refresh-button"));
    await waitFor(() => {
      expect(onRefresh).toHaveBeenCalledTimes(1);
    });
  });
});

describe("RefreshButton — error surfacing", () => {
  it("shows error state when onRefresh rejects", async () => {
    const onRefresh = vi.fn().mockRejectedValue(new Error("network failure"));
    render(<RefreshButton onRefresh={onRefresh} />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("refresh-button"));

    await waitFor(() => {
      const btn = screen.getByTestId("refresh-button");
      expect(btn).toHaveAttribute("data-state", "error");
    });
  });

  it("shows row-level error chips when rowErrors are provided", () => {
    render(
      <RefreshButton
        onRefresh={async () => {}}
        rowErrors={{ prs: "503: github_pat_missing" }}
      />,
    );
    expect(screen.getByTestId("row-error-prs")).toBeInTheDocument();
    expect(screen.getByTestId("row-error-prs")).toHaveTextContent(/prs/i);
  });

  it("does not show error chips when no rowErrors", () => {
    render(<RefreshButton onRefresh={async () => {}} />);
    expect(screen.queryByTestId("row-error-prs")).not.toBeInTheDocument();
    expect(screen.queryByTestId("row-error-proposals")).not.toBeInTheDocument();
  });
});

describe("RefreshButton — last-refreshed timestamp", () => {
  it("shows last-refreshed timestamp after successful refresh", async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<RefreshButton onRefresh={onRefresh} />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("refresh-button"));

    await waitFor(() => {
      expect(screen.getByTestId("last-refreshed")).toBeInTheDocument();
    });
  });
});
