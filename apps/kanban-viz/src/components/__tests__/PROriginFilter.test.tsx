/**
 * Tests for PROriginFilter component (tasks 8.1, 8.2).
 *
 * Covers:
 * - Chips for all six origins render
 * - Deselecting a chip filters the PR row (no network request)
 * - Selection persists via localStorage["kanban-viz:pr-origins"]
 * - filterByOrigin pure function works correctly
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PROriginFilter, ALL_PR_ORIGINS, filterByOrigin } from "../PROriginFilter";
import type { PROrigin } from "../../lib/coordinator-types";

const STORAGE_KEY = "kanban-viz:pr-origins";

// localStorage mock (jsdom in this env doesn't expose .clear)
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

beforeEach(() => {
  Object.defineProperty(globalThis, "localStorage", {
    value: localStorageMock,
    writable: true,
    configurable: true,
  });
  localStorageMock.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorageMock.clear();
});

// ─────────────────────────────────────────────────────────────────────────────
// Rendering and chip behavior

describe("PROriginFilter — rendering", () => {
  it("renders chips for all six origins", () => {
    render(<PROriginFilter />);
    for (const origin of ALL_PR_ORIGINS) {
      expect(screen.getByTestId(`origin-chip-${origin}`)).toBeInTheDocument();
    }
  });

  it("all chips are pressed (selected) by default", () => {
    render(<PROriginFilter />);
    for (const origin of ALL_PR_ORIGINS) {
      const chip = screen.getByTestId(`origin-chip-${origin}`);
      expect(chip).toHaveAttribute("aria-pressed", "true");
    }
  });

  it("clicking a chip deselects it", async () => {
    const user = userEvent.setup();
    render(<PROriginFilter />);
    const chip = screen.getByTestId("origin-chip-dependabot");
    await user.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking a deselected chip re-selects it", async () => {
    const user = userEvent.setup();
    render(<PROriginFilter />);
    const chip = screen.getByTestId("origin-chip-dependabot");
    await user.click(chip); // deselect
    await user.click(chip); // re-select
    expect(chip).toHaveAttribute("aria-pressed", "true");
  });

  it("deselecting a chip calls onSelectionChange without that origin", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<PROriginFilter onSelectionChange={onChange} />);
    await user.click(screen.getByTestId("origin-chip-dependabot"));
    expect(onChange).toHaveBeenCalledTimes(1);
    const lastCall = onChange.mock.calls[0][0] as PROrigin[];
    expect(lastCall).not.toContain("dependabot");
    expect(lastCall).toHaveLength(ALL_PR_ORIGINS.length - 1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Persistence

describe("PROriginFilter — localStorage persistence (task 8.2)", () => {
  it("saves selection to localStorage on chip click", async () => {
    const user = userEvent.setup();
    render(<PROriginFilter />);
    await user.click(screen.getByTestId("origin-chip-dependabot"));
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as PROrigin[];
    expect(stored).not.toContain("dependabot");
    expect(stored.length).toBe(ALL_PR_ORIGINS.length - 1);
  });

  it("loads selection from localStorage on mount", () => {
    const stored: PROrigin[] = ["openspec", "codex", "jules"];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
    render(<PROriginFilter />);
    // Only the stored origins should be selected
    for (const origin of stored) {
      expect(screen.getByTestId(`origin-chip-${origin}`)).toHaveAttribute("aria-pressed", "true");
    }
    for (const origin of ALL_PR_ORIGINS.filter((o) => !stored.includes(o))) {
      expect(screen.getByTestId(`origin-chip-${origin}`)).toHaveAttribute("aria-pressed", "false");
    }
  });

  it("defaults to all selected when localStorage has no entry", () => {
    render(<PROriginFilter />);
    for (const origin of ALL_PR_ORIGINS) {
      expect(screen.getByTestId(`origin-chip-${origin}`)).toHaveAttribute("aria-pressed", "true");
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// filterByOrigin pure function

describe("filterByOrigin", () => {
  const cards = [
    { id: "1", origin: "openspec" as PROrigin, title: "a" },
    { id: "2", origin: "dependabot" as PROrigin, title: "b" },
    { id: "3", origin: "codex" as PROrigin, title: "c" },
    { id: "4", origin: "manual" as PROrigin, title: "d" },
  ];

  it("returns all cards when all origins are selected", () => {
    expect(filterByOrigin(cards, ALL_PR_ORIGINS)).toHaveLength(4);
  });

  it("filters to only matching origins", () => {
    const result = filterByOrigin(cards, ["openspec", "codex"]);
    expect(result).toHaveLength(2);
    expect(result.map((c) => c.id)).toEqual(["1", "3"]);
  });

  it("returns empty array when no origins selected", () => {
    expect(filterByOrigin(cards, [])).toHaveLength(0);
  });
});
