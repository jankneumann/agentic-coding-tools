/**
 * How the board authenticates to the coordinator, and how it builds URLs.
 *
 * Two deployments:
 *   - Direct (laptop / Tauri): VITE_COORDINATOR_API_KEY is baked into the
 *     build and sent as `Authorization: Bearer <key>`.
 *   - Proxied (GX-10): VITE_COORDINATOR_AUTH=proxy and no key. The analyzer's
 *     Caddy injects the key server-side, so it never reaches the bundle.
 *
 * In the proxied deployment the board MUST NOT send an Authorization header:
 * the site sits behind Caddy basic_auth, and an explicit header replaces the
 * browser's cached Basic credentials, so every API call would 401 at Caddy.
 */

export function proxyAuth(): boolean {
  return import.meta.env["VITE_COORDINATOR_AUTH"] === "proxy";
}

/** Headers carrying the key, or none when there is no key to send. */
export function authHeaders(apiKey: string | undefined): Record<string, string> {
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
}

/** True when write actions can authenticate: a baked key, or the proxy's. */
export function canAuthenticate(apiKey: string | undefined): boolean {
  return Boolean(apiKey) || proxyAuth();
}

/**
 * Absolute URL for an API path. `apiUrl` may be same-origin relative
 * (`/kanban/api`), which `new URL()` rejects without a base.
 */
export function endpoint(apiUrl: string, path: string): URL {
  return new URL(`${apiUrl}${path}`, window.location.href);
}
