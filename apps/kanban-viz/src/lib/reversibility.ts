/**
 * Reversibility classifier for Kanban UI actions.
 *
 * Design D8: classifies every user-initiated action as one of:
 *   - reversible-write: can be undone (save view, label add)
 *   - destructive-write: cannot be fully undone (kick agent, force-release lock)
 *   - ephemeral-event: fires and forgets (UI navigation, panel open/close)
 *
 * Mirror: skills/shared/op_reversibility.py (Python counterpart reserved for
 * coordinator-side audit classification — see D8 reservation).
 *
 * Keep in sync with contracts/README.md "Audit Event Schema" action enum.
 */

export type ReversibilityClass =
  | "reversible-write"
  | "destructive-write"
  | "ephemeral-event";

/** Canonical action keys (mirrors audit-event.json schema action enum). */
export type ActionKey =
  | "save-view"
  | "load-view"
  | "drag-to-ready"
  | "kick-agent"
  | "force-release-lock"
  | "panel-open"
  | "panel-close";

const REVERSIBILITY_TABLE: Record<ActionKey, ReversibilityClass> = {
  "save-view": "reversible-write",
  "load-view": "ephemeral-event",
  "drag-to-ready": "reversible-write",
  "kick-agent": "destructive-write",
  "force-release-lock": "destructive-write",
  "panel-open": "ephemeral-event",
  "panel-close": "ephemeral-event",
};

/**
 * Classify an action by its reversibility.
 *
 * @throws {Error} if the action key is not in the classification table.
 *   Callers should use `classifyOrDefault` for unknown keys.
 */
export function classify(action: ActionKey): ReversibilityClass {
  return REVERSIBILITY_TABLE[action];
}

/**
 * Classify an action, returning "ephemeral-event" for unknown keys.
 * Use this for UI event handlers where the action may not be in the table.
 */
export function classifyOrDefault(action: string): ReversibilityClass {
  return (REVERSIBILITY_TABLE as Record<string, ReversibilityClass>)[action] ?? "ephemeral-event";
}

/** True if the action requires a ConsentPrompt before execution. */
export function requiresConsent(action: ActionKey): boolean {
  return classify(action) === "destructive-write";
}
