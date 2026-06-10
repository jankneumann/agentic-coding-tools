/**
 * Tests for ClusterBadge component (task 8.4).
 *
 * Covers:
 * - Cards sharing change_id render the badge with correct count
 * - Click highlights siblings for ≥ 1.5s (aria-label present + highlight class)
 * - Cards with change_id=null do NOT render a badge
 * - badge aria-label describes the cluster
 * - ClusterHighlightWrapper applies highlight outline on sibling click
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClusterBadge, ClusterHighlightWrapper, emitHighlight } from "../ClusterBadge";

afterEach(() => {
  // Reset highlight state after each test
  act(() => {
    emitHighlight(null);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ClusterBadge rendering

describe("ClusterBadge — rendering", () => {
  it("renders badge with correct count when clusterCount > 1", () => {
    render(<ClusterBadge changeId="change-a" clusterCount={3} />);
    const badge = screen.getByTestId("cluster-badge-change-a");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("3");
  });

  it("does NOT render badge when change_id is null", () => {
    render(<ClusterBadge changeId={null} clusterCount={3} />);
    expect(screen.queryByTestId(/cluster-badge/)).not.toBeInTheDocument();
  });

  it("does NOT render badge when clusterCount is null", () => {
    render(<ClusterBadge changeId="change-a" clusterCount={null} />);
    expect(screen.queryByTestId(/cluster-badge/)).not.toBeInTheDocument();
  });

  it("does NOT render badge when clusterCount is 1", () => {
    render(<ClusterBadge changeId="change-a" clusterCount={1} />);
    expect(screen.queryByTestId(/cluster-badge/)).not.toBeInTheDocument();
  });

  it("badge has aria-label describing the cluster", () => {
    render(<ClusterBadge changeId="change-a" clusterCount={3} />);
    const badge = screen.getByTestId("cluster-badge-change-a");
    expect(badge).toHaveAttribute("aria-label");
    const ariaLabel = badge.getAttribute("aria-label") ?? "";
    expect(ariaLabel).toContain("change-a");
    expect(ariaLabel).toContain("3");
  });

  it("badge shows cluster count in title", () => {
    render(<ClusterBadge changeId="my-change" clusterCount={2} />);
    const badge = screen.getByTestId("cluster-badge-my-change");
    expect(badge).toHaveAttribute("title");
    const title = badge.getAttribute("title") ?? "";
    expect(title).toContain("my-change");
    expect(title).toContain("2");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ClusterBadge click-to-highlight

describe("ClusterBadge — click highlights siblings", () => {
  it("clicking badge emits highlight for that change_id via emitHighlight", async () => {
    const user = userEvent.setup();
    render(
      <>
        <ClusterBadge changeId="change-a" clusterCount={2} />
        <ClusterHighlightWrapper changeId="change-a">
          <div data-testid="sibling-card">Sibling</div>
        </ClusterHighlightWrapper>
      </>,
    );
    const badge = screen.getByTestId("cluster-badge-change-a");
    await user.click(badge);
    // The wrapper should now have highlight outline
    const wrapper = screen.getByTestId("cluster-highlight-change-a");
    expect(wrapper).toHaveStyle("outline: 2px solid #ff7043");
  });

  it("highlight clears after 1500ms (timer-based)", async () => {
    vi.useFakeTimers();
    try {
      render(
        <>
          <ClusterBadge changeId="change-b" clusterCount={2} />
          <ClusterHighlightWrapper changeId="change-b">
            <div>Card</div>
          </ClusterHighlightWrapper>
        </>,
      );
      // Trigger highlight directly
      act(() => {
        emitHighlight("change-b");
      });
      const wrapper = screen.getByTestId("cluster-highlight-change-b");
      expect(wrapper).toHaveStyle("outline: 2px solid #ff7043");

      act(() => {
        vi.advanceTimersByTime(1600);
      });

      expect(wrapper).toHaveStyle("outline: none");
    } finally {
      vi.useRealTimers();
    }
  });
});
