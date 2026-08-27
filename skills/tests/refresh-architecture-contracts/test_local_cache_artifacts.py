"""Contract test: local-cache architecture artifacts stay OUT of the git index.

``treesitter_enrichment.json``, ``python_analysis.json`` and ``parallel_zones.json``
are generated analyzer caches. Nothing outside the refresh-architecture pipeline
reads them, they are large and churn on every run, and ``provenance.py`` marks them
``tier: local-cache`` so their absence is not drift. Tracking them therefore buys
nothing and costs ~2.76 MB of blob churn per refresh, so they are untracked and
ignored.

The complementary assertion — that the genuinely committed artifacts are still
tracked — guards the other direction: an over-eager ``git rm --cached`` or a
``.gitignore`` glob that swallows the whole directory trips this suite.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Generated analyzer caches. Present on disk after a refresh, never in the index.
LOCAL_CACHE_ARTIFACTS = (
    "docs/architecture-analysis/treesitter_enrichment.json",
    "docs/architecture-analysis/python_analysis.json",
    "docs/architecture-analysis/parallel_zones.json",
)

#: Artifacts whose absence in a clean clone IS real drift, so they must stay tracked.
COMMITTED_ARTIFACTS = (
    "docs/architecture-analysis/architecture.graph.json",
    "docs/architecture-analysis/architecture.summary.json",
)


def _git_ls_files(path: str) -> str:
    result = subprocess.run(
        ["git", "ls-files", "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TestLocalCacheArtifactsAreUntracked:
    @pytest.mark.parametrize("path", LOCAL_CACHE_ARTIFACTS)
    def test_local_cache_artifact_is_not_tracked(self, path: str) -> None:
        tracked = _git_ls_files(path)
        assert tracked == "", (
            f"{path} is tracked in git but is a local-cache artifact "
            f"(tier: local-cache in provenance.py). Untrack it with "
            f"`git rm --cached {path}` — do not delete it from disk."
        )

    @pytest.mark.parametrize("path", LOCAL_CACHE_ARTIFACTS)
    def test_local_cache_artifact_is_ignored(self, path: str) -> None:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", path],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{path} is untracked but not ignored, so a refresh leaves it as "
            f"untracked noise in `git status`. Add it to .gitignore."
        )


class TestCommittedArtifactsStayTracked:
    @pytest.mark.parametrize("path", COMMITTED_ARTIFACTS)
    def test_committed_artifact_is_still_tracked(self, path: str) -> None:
        tracked = _git_ls_files(path)
        assert tracked == path, (
            f"{path} is a committed-tier artifact and must stay in the index; "
            f"`git ls-files` returned {tracked!r}."
        )
