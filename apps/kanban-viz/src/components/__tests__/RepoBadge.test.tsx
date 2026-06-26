/**
 * Tests for RepoBadge component — task 8.1
 *
 * Spec scenarios:
 *   - Renders short form by default (basename of the repo)
 *   - Tooltip shows full <owner>/<repo>
 *   - aria-label includes the repo qualifier
 *   - Same repo produces same color across renders (deterministic hash)
 *   - null repo renders nothing
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RepoBadge } from "../RepoBadge";

describe("RepoBadge", () => {
  it("renders nothing when repo is null", () => {
    const { container } = render(<RepoBadge repo={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when repo is undefined", () => {
    const { container } = render(<RepoBadge repo={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the short form (repo basename) by default", () => {
    render(<RepoBadge repo="owner/myrepo" />);
    const badge = screen.getByTestId("repo-badge");
    expect(badge).toBeTruthy();
    // Short form: just the basename "myrepo"
    expect(badge.textContent).toBe("myrepo");
  });

  it("renders local/ prefix repos as short form (strips 'local/' prefix)", () => {
    render(<RepoBadge repo="local/my-checkout" />);
    const badge = screen.getByTestId("repo-badge");
    // For local/ repos the short form should be the basename after 'local/'
    expect(badge.textContent).toBe("my-checkout");
  });

  it("tooltip (title) shows full <owner>/<repo>", () => {
    render(<RepoBadge repo="owner/myrepo" />);
    const badge = screen.getByTestId("repo-badge");
    expect(badge.getAttribute("title")).toBe("owner/myrepo");
  });

  it("aria-label matches spec: 'Repository <owner>/<repo>'", () => {
    render(<RepoBadge repo="jankneumann/agentic-coding-tools" />);
    const badge = screen.getByTestId("repo-badge");
    // Spec scenario: aria-label SHALL equal "Repository jankneumann/agentic-coding-tools"
    expect(badge.getAttribute("aria-label")).toBe(
      "Repository jankneumann/agentic-coding-tools",
    );
  });

  it("same repo string always produces the same color (deterministic)", () => {
    const { container: c1, unmount: u1 } = render(<RepoBadge repo="owner/stable" />);
    const style1 = (c1.firstChild as HTMLElement)?.style.backgroundColor;
    u1();

    const { container: c2, unmount: u2 } = render(<RepoBadge repo="owner/stable" />);
    const style2 = (c2.firstChild as HTMLElement)?.style.backgroundColor;
    u2();

    // Both renders should produce the exact same color
    expect(style1).toBe(style2);
    // Color should be non-empty (some color was set)
    expect(style1).toBeTruthy();
  });

  it("different repos produce different colors (no constant color)", () => {
    const { container: c1, unmount: u1 } = render(<RepoBadge repo="owner/repo-alpha" />);
    const style1 = (c1.firstChild as HTMLElement)?.style.backgroundColor;
    u1();

    const { container: c2, unmount: u2 } = render(<RepoBadge repo="totally/different" />);
    const style2 = (c2.firstChild as HTMLElement)?.style.backgroundColor;
    u2();

    // High probability they differ (birthday paradox negligible for 2 repos)
    expect(style1).not.toBe(style2);
  });

  it("renders with a data-testid for integration test targeting", () => {
    render(<RepoBadge repo="some/repo" />);
    expect(screen.getByTestId("repo-badge")).toBeTruthy();
  });
});
