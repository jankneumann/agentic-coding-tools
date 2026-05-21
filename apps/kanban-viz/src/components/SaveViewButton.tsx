/**
 * SaveViewButton — minimal toolbar control for task 6.7 (SavedViewsDrawer
 * scope reduced to a save-only button; loading/listing requires a GET
 * endpoint that doesn't exist yet, deferred per the impl-review-1 handoff).
 *
 * On click: prompts for a slug, captures the current filter state, calls
 * saveView() (library function, browser/Tauri-aware), and emits a
 * schema-valid reversible-write audit event.
 */
import { useState } from "react";
import { classify } from "../lib/reversibility";
import { saveView } from "../lib/saveView";

interface Props {
  apiUrl: string;
  apiKey: string;
  /**
   * The current filter state to persist. Matches SavedViewPayload.filters —
   * change_ids[], vendors[], etc. App.tsx passes the actively-subscribed
   * change_ids at minimum.
   */
  currentFilters: Record<string, unknown>;
  /**
   * Optional name suggestion for the save dialog. If omitted, the user is
   * prompted with an empty string.
   */
  suggestedName?: string;
  /**
   * Schema-valid audit emitter (see App.tsx). The component emits a
   * reversible-write audit with action="save-view" on save success and
   * outcome="failed" on save error.
   */
  onAuditEmit?: (eventData: Record<string, unknown>) => void;
}

/**
 * Slug constraint matches the backend regex (kanban_viz_files.py:38):
 * `^[a-z0-9][a-z0-9-]{0,63}$`. We tighten further client-side so the user
 * sees the error before a 400 round-trips.
 */
const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,63}$/;

function slugify(name: string): string {
  // Best-effort: lowercase, replace spaces and underscores with hyphens,
  // strip everything outside the allowed set.
  return name
    .toLowerCase()
    .trim()
    .replace(/[_\s]+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
}

export function SaveViewButton({
  apiUrl,
  apiKey,
  currentFilters,
  suggestedName,
  onAuditEmit,
}: Props) {
  const [status, setStatus] = useState<
    "idle" | "saving" | "saved" | "error"
  >("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleClick = async () => {
    // window.prompt is the simplest cross-browser modal that fits within MVP
    // scope; a richer drawer with name/preview is deferred.
    const rawName = window.prompt(
      "Name this saved view (letters, numbers, hyphens):",
      suggestedName ?? "",
    );
    if (rawName === null) return; // user cancelled
    const slug = slugify(rawName);
    if (!SLUG_PATTERN.test(slug)) {
      setErrorMessage(
        `Invalid name "${rawName}" — must start with a letter or digit and use only letters, numbers, or hyphens.`,
      );
      setStatus("error");
      return;
    }

    setStatus("saving");
    setErrorMessage(null);

    // IMPL_REVIEW claude#11: classify the action so the audit event class
    // matches the spec's reversibility table (D8).
    const klass = classify("save-view");
    try {
      const result = await saveView(
        slug,
        { name: rawName.trim() || slug, filters: currentFilters },
        apiUrl,
        apiKey,
      );
      onAuditEmit?.({
        action: "save-view",
        class: klass,
        outcome: result.saved ? "confirmed" : "failed",
        args: {
          slug,
          path: result.path,
          ...(result.git_sha ? { git_sha: result.git_sha } : {}),
        },
      });
      setStatus(result.saved ? "saved" : "error");
      if (!result.saved) setErrorMessage("Save returned saved=false");
      // Reset to idle after a brief confirmation so the button is usable again.
      setTimeout(() => setStatus("idle"), 2000);
    } catch (e) {
      const msg = String(e);
      onAuditEmit?.({
        action: "save-view",
        class: klass,
        outcome: "failed",
        args: { slug, failure_reason: msg },
      });
      setErrorMessage(msg);
      setStatus("error");
    }
  };

  const label =
    status === "saving"
      ? "Saving…"
      : status === "saved"
        ? "Saved ✓"
        : "Save View";

  return (
    <div
      data-testid="save-view-control"
      style={{ display: "inline-flex", alignItems: "center", gap: 8 }}
    >
      <button
        type="button"
        data-testid="save-view-button"
        disabled={status === "saving"}
        onClick={() => void handleClick()}
        style={{
          fontSize: 12,
          padding: "4px 10px",
          background: status === "saved" ? "#22a06b" : "#0052cc",
          color: "#fff",
          border: "none",
          borderRadius: 3,
          cursor: status === "saving" ? "wait" : "pointer",
        }}
      >
        {label}
      </button>
      {status === "error" && errorMessage && (
        <span
          data-testid="save-view-error"
          role="alert"
          style={{ fontSize: 11, color: "#de350b" }}
        >
          {errorMessage}
        </span>
      )}
    </div>
  );
}
