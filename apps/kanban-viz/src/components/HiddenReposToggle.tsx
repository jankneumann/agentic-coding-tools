/**
 * HiddenReposToggle — chip group showing all repos visible on the current board.
 *
 * Clicking a chip toggles its repo between visible and hidden. The caller is
 * responsible for persisting the hidden list via the saved-view `hidden_repos`
 * field (extended in wp-coord-sources).
 *
 * UX vocabulary mirrors PROriginFilter: active (visible) chips are highlighted;
 * inactive (hidden) chips are dimmed. The component is controlled — the caller
 * manages the hiddenRepos state and provides onHiddenReposChange.
 *
 * Renders nothing when repos is empty.
 */

/** Short display form: basename after the last slash. */
function shortForm(repo: string): string {
  const idx = repo.lastIndexOf("/");
  return idx >= 0 ? repo.slice(idx + 1) : repo;
}

interface Props {
  /** Unique repo strings seen on the current board, e.g. ["owner/a", "owner/b"]. */
  repos: readonly string[];
  /** Which repos are currently hidden. Controlled from saved-view. */
  hiddenRepos: readonly string[];
  /** Called when the user toggles a chip; receives the updated hiddenRepos list. */
  onHiddenReposChange: (hiddenRepos: string[]) => void;
}

export function HiddenReposToggle({ repos, hiddenRepos, onHiddenReposChange }: Props) {
  if (repos.length === 0) return null;

  const hiddenSet = new Set(hiddenRepos);

  const handleClick = (repo: string) => {
    const next = hiddenSet.has(repo)
      ? [...hiddenRepos].filter((r) => r !== repo)
      : [...hiddenRepos, repo];
    onHiddenReposChange(next);
  };

  return (
    <div
      data-testid="hidden-repos-toggle"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
        alignItems: "center",
      }}
      aria-label="Visible repositories"
    >
      {repos.map((repo) => {
        const isVisible = !hiddenSet.has(repo);
        return (
          <button
            key={repo}
            type="button"
            data-testid={`repo-toggle-chip-${repo}`}
            aria-pressed={isVisible}
            aria-label={`${isVisible ? "Hide" : "Show"} ${repo}`}
            title={repo}
            onClick={() => { handleClick(repo); }}
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: 10,
              border: "1px solid",
              cursor: "pointer",
              background: isVisible ? "#deebff" : "#f4f5f7",
              color: isVisible ? "#0052cc" : "#666",
              borderColor: isVisible ? "#4c9aff" : "#dfe1e6",
              userSelect: "none",
            }}
          >
            {shortForm(repo)}
          </button>
        );
      })}
    </div>
  );
}
