/**
 * Tests for HiddenReposToggle component — task 9.1
 *
 * Spec scenarios:
 *   - Chip group renders one entry per unique repo on board
 *   - Clicking a chip toggles hidden state
 *   - Persisted via saved view round-trip (onHiddenReposChange callback)
 *   - Hidden cards excluded when hiddenRepos is applied
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HiddenReposToggle } from "../HiddenReposToggle";

describe("HiddenReposToggle — chip rendering", () => {
  it("renders one chip per unique repo", () => {
    const repos = ["jankneumann/repo-a", "jankneumann/repo-b"];
    render(
      <HiddenReposToggle
        repos={repos}
        hiddenRepos={[]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId("hidden-repos-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("repo-toggle-chip-jankneumann/repo-a")).toBeInTheDocument();
    expect(screen.getByTestId("repo-toggle-chip-jankneumann/repo-b")).toBeInTheDocument();
  });

  it("renders nothing when repos is empty", () => {
    const { container } = render(
      <HiddenReposToggle
        repos={[]}
        hiddenRepos={[]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("chip shows repo basename as display text", () => {
    render(
      <HiddenReposToggle
        repos={["owner/myrepo"]}
        hiddenRepos={[]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    const chip = screen.getByTestId("repo-toggle-chip-owner/myrepo");
    expect(chip.textContent).toContain("myrepo");
  });

  it("chips for all repos are visible by default (none hidden)", () => {
    const repos = ["owner/a", "owner/b"];
    render(
      <HiddenReposToggle
        repos={repos}
        hiddenRepos={[]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    const chipA = screen.getByTestId("repo-toggle-chip-owner/a");
    const chipB = screen.getByTestId("repo-toggle-chip-owner/b");
    // Active chips should look visually different from hidden ones
    expect(chipA.getAttribute("aria-pressed")).toBe("true");
    expect(chipB.getAttribute("aria-pressed")).toBe("true");
  });

  it("hidden repos chips show as inactive (aria-pressed=false)", () => {
    render(
      <HiddenReposToggle
        repos={["owner/a", "owner/b"]}
        hiddenRepos={["owner/a"]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    const chipA = screen.getByTestId("repo-toggle-chip-owner/a");
    const chipB = screen.getByTestId("repo-toggle-chip-owner/b");
    expect(chipA.getAttribute("aria-pressed")).toBe("false");
    expect(chipB.getAttribute("aria-pressed")).toBe("true");
  });
});

describe("HiddenReposToggle — click to toggle", () => {
  it("clicking an active chip calls onHiddenReposChange with the repo added to hiddenRepos", async () => {
    const user = userEvent.setup();
    const onchange = vi.fn();
    render(
      <HiddenReposToggle
        repos={["owner/a", "owner/b"]}
        hiddenRepos={[]}
        onHiddenReposChange={onchange}
      />,
    );
    await user.click(screen.getByTestId("repo-toggle-chip-owner/a"));
    expect(onchange).toHaveBeenCalledWith(["owner/a"]);
  });

  it("clicking a hidden chip calls onHiddenReposChange with the repo removed from hiddenRepos", async () => {
    const user = userEvent.setup();
    const onchange = vi.fn();
    render(
      <HiddenReposToggle
        repos={["owner/a", "owner/b"]}
        hiddenRepos={["owner/a"]}
        onHiddenReposChange={onchange}
      />,
    );
    await user.click(screen.getByTestId("repo-toggle-chip-owner/a"));
    expect(onchange).toHaveBeenCalledWith([]);
  });

  it("toggling one chip does not affect others", async () => {
    const user = userEvent.setup();
    const onchange = vi.fn();
    render(
      <HiddenReposToggle
        repos={["owner/a", "owner/b"]}
        hiddenRepos={[]}
        onHiddenReposChange={onchange}
      />,
    );
    await user.click(screen.getByTestId("repo-toggle-chip-owner/a"));
    // Should only add owner/a, not owner/b
    expect(onchange).toHaveBeenCalledWith(["owner/a"]);
  });
});

describe("HiddenReposToggle — saved-view round-trip", () => {
  it("hiddenRepos prop controls visual state on re-render (controlled component)", () => {
    const { rerender } = render(
      <HiddenReposToggle
        repos={["owner/a"]}
        hiddenRepos={[]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    // Initially active
    expect(screen.getByTestId("repo-toggle-chip-owner/a").getAttribute("aria-pressed")).toBe("true");

    // Simulate saved-view restoring hidden state
    rerender(
      <HiddenReposToggle
        repos={["owner/a"]}
        hiddenRepos={["owner/a"]}
        onHiddenReposChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId("repo-toggle-chip-owner/a").getAttribute("aria-pressed")).toBe("false");
  });
});
