/**
 * Runtime feature detection for Tauri vs browser environments.
 *
 * Design D11 / KANBAN-006: every code path that uses Tauri APIs MUST be
 * guarded by isTauri() so the browser build never attempts to import
 * or evaluate @tauri-apps/api.
 *
 * Detection: the Tauri runtime injects window.__TAURI__ before any
 * application scripts run. A falsy value means the browser path.
 */

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI__" in window;
}

/**
 * Return true if the app is running inside a browser (not Tauri).
 * Sugar for !isTauri() — prefer calling isTauri() directly when
 * the context is obvious.
 */
export function isBrowser(): boolean {
  return !isTauri();
}
