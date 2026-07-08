/**
 * RepoBadge — micro-component that renders a small colored chip attributing
 * a card to its source repository.
 *
 * Color is derived deterministically from the repo string via a 24-bit hash
 * → HSL color. Same repo always produces the same color, no randomization,
 * no per-session state (R1 spec invariant).
 *
 * Lightness is constrained to [35%, 55%] for readability against white text,
 * and saturation is fixed at 55% for consistent vibrancy.
 *
 * Display:
 *   - Short form: basename of the repo (the part after the last slash)
 *     e.g. "owner/myrepo" → "myrepo", "local/checkout" → "checkout"
 *   - Tooltip (title): full <owner>/<repo> string
 *   - aria-label: "repository: <owner>/<repo>"
 *
 * Hidden when repo is null or undefined.
 */

/** Deterministic 24-bit hash of a string (FNV-1a variant). */
function hashString(str: string): number {
  let hash = 2166136261; // FNV offset basis (32-bit)
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    // FNV prime multiply (simulate 32-bit overflow with modulo)
    hash = (hash * 16777619) >>> 0;
  }
  return hash;
}

/** Derive a deterministic HSL background color from a repo string. */
function repoToColor(repo: string): string {
  const hash = hashString(repo);
  const hue = hash % 360;
  const saturation = 55;
  // Lightness [35%, 55%] — dark enough for white text, varied enough to distinguish
  const lightness = 35 + (hash % 21);
  return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
}

/** Short display form: basename after the last slash. */
function shortForm(repo: string): string {
  const idx = repo.lastIndexOf("/");
  return idx >= 0 ? repo.slice(idx + 1) : repo;
}

interface Props {
  /** Full <owner>/<repo> string. Renders nothing when null/undefined. */
  repo: string | null | undefined;
}

export function RepoBadge({ repo }: Props) {
  if (repo == null) return null;

  const bgColor = repoToColor(repo);
  const displayText = shortForm(repo);

  return (
    <span
      data-testid="repo-badge"
      title={repo}
      aria-label={`Repository ${repo}`}
      style={{
        display: "inline-block",
        backgroundColor: bgColor,
        color: "#fff",
        fontSize: 10,
        fontWeight: 600,
        padding: "1px 5px",
        borderRadius: 8,
        whiteSpace: "nowrap",
        cursor: "default",
        userSelect: "none",
        letterSpacing: "0.01em",
      }}
    >
      {displayText}
    </span>
  );
}
