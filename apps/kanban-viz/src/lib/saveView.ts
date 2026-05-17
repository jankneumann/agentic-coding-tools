/**
 * saveView() — writes a saved view via the coordinator file-write endpoint.
 *
 * Browser path: POSTs to PUT /kanban-viz/saved-views/{slug}.
 *   The coordinator owns the on-disk write per design D10.
 *   The browser NEVER writes directly to the filesystem.
 *
 * Tauri path: uses @tauri-apps/api fs.writeTextFile.
 *   Detected via runtime.ts isTauri().
 *   The Tauri path writes the same JSON schema directly so the format is
 *   identical on both paths (design decision KANBAN-006 resolution).
 *
 * Callers receive { saved: boolean; path: string; git_sha: string }.
 */
import { isTauri } from "./runtime";

export interface SavedViewPayload {
  name: string;
  filters: Record<string, unknown>;
  column_layout?: Record<string, unknown>;
}

export interface SaveViewResult {
  saved: boolean;
  path: string;
  git_sha?: string;
}

export async function saveView(
  slug: string,
  view: SavedViewPayload,
  apiUrl: string,
  apiKey: string,
): Promise<SaveViewResult> {
  if (isTauri()) {
    return saveTauri(slug, view);
  }
  return saveBrowser(slug, view, apiUrl, apiKey);
}

async function saveBrowser(
  slug: string,
  view: SavedViewPayload,
  apiUrl: string,
  apiKey: string,
): Promise<SaveViewResult> {
  const res = await fetch(`${apiUrl}/kanban-viz/saved-views/${slug}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ view }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(`saveView: ${res.status} ${body.detail ?? ""}`);
  }
  return (await res.json()) as SaveViewResult;
}

async function saveTauri(
  slug: string,
  view: SavedViewPayload,
): Promise<SaveViewResult> {
  // Dynamic import via string concatenation to prevent Vite from trying to
  // bundle @tauri-apps/api/fs (which only exists in the Tauri runtime).
  // The isTauri() guard in the public saveView() ensures this path never
  // runs in a browser.
  const tauriPkg = "@tauri-apps" + "/api/fs";
  const { writeTextFile } = (await import(/* @vite-ignore */ tauriPkg)) as {
    writeTextFile: (path: string, content: string) => Promise<void>;
  };
  const path = `docs/kanban-viz/saved-views/${slug}.json`;
  const document = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    git_sha: "0000000",
    generator: "kanban-viz@0.1.0",
    view,
  };
  await writeTextFile(path, JSON.stringify(document, null, 2) + "\n");
  return { saved: true, path };
}
