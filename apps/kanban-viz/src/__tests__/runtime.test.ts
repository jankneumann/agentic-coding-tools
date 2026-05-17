/**
 * Tests for runtime feature detection.
 * Covers tasks 7.3, 7.4.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { isTauri, isBrowser } from "../lib/runtime";

describe("runtime feature detection", () => {
  afterEach(() => {
    delete (window as Record<string, unknown>).__TAURI__;
  });

  it("isTauri() returns false in jsdom (browser environment)", () => {
    expect(isTauri()).toBe(false);
  });

  it("isBrowser() returns true in jsdom", () => {
    expect(isBrowser()).toBe(true);
  });

  it("isTauri() returns true when window.__TAURI__ is set", () => {
    (window as Record<string, unknown>).__TAURI__ = {};
    expect(isTauri()).toBe(true);
  });

  it("isBrowser() returns false when window.__TAURI__ is set", () => {
    (window as Record<string, unknown>).__TAURI__ = {};
    expect(isBrowser()).toBe(false);
  });
});

// 7.4: verify that browser code paths do NOT evaluate @tauri-apps/api at import time

describe("browser code paths run without Tauri APIs", () => {
  beforeEach(() => {
    delete (window as Record<string, unknown>).__TAURI__;
  });

  it("can import saveView module without @tauri-apps/api being called at module-load", async () => {
    // Dynamic import: if the module tries to call Tauri APIs at module level,
    // this would throw in jsdom. It should load cleanly.
    const mod = await import("../lib/saveView");
    expect(typeof mod.saveView).toBe("function");
  });

  it("can import reversibility module without Tauri APIs", async () => {
    const mod = await import("../lib/reversibility");
    expect(typeof mod.classify).toBe("function");
  });

  it("can import coordinator-types module without Tauri APIs", async () => {
    const mod = await import("../lib/coordinator-types");
    expect(typeof mod.statusToColumn).toBe("function");
  });
});
