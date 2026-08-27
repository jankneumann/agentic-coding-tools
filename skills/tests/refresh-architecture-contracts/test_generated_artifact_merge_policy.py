"""Merge-policy contract for generated architecture artifacts (wp-merge-hygiene).

``docs/architecture-analysis/`` holds resolver-style generated JSON. Two branches
that both regenerate it produce different bytes for the same inputs, so without an
explicit merge policy every parallel branch pays a rebase-and-regenerate tax.

These tests pin the policy declared in ``.gitattributes``: ``merge=binary``, which
leaves the path conflicted so the only correct resolution — take one side and
regenerate — is the one git forces.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

_GENERATED_ARTIFACTS = [
    "docs/architecture-analysis/architecture.graph.json",
    "docs/architecture-analysis/architecture.diagnostics.json",
    "docs/architecture-analysis/treesitter_enrichment.json",
    "docs/architecture-analysis/parallel_zones.json",
]


def _check_attr(attribute: str, path: str) -> str:
    """Return the value git resolves for ``attribute`` on ``path``.

    ``git check-attr`` is path-based, so it answers for artifacts that are
    committed and for ones that are only generated locally.
    """
    completed = subprocess.run(
        ["git", "check-attr", attribute, "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    # Output shape: "<path>: <attribute>: <value>"
    return completed.stdout.strip().rsplit(": ", 1)[-1]


@pytest.mark.parametrize("artifact", _GENERATED_ARTIFACTS)
def test_generated_artifact_uses_binary_merge(artifact: str) -> None:
    assert _check_attr("merge", artifact) == "binary", (
        f"{artifact} is generated output; .gitattributes must declare it "
        "merge=binary so a two-sided regeneration conflicts instead of being "
        "silently line-merged"
    )


@pytest.mark.parametrize("artifact", _GENERATED_ARTIFACTS)
def test_generated_artifact_is_not_union_merged(artifact: str) -> None:
    # Union merge would concatenate two regenerated documents and report a clean
    # merge of JSON that no longer describes any single revision of the repo.
    assert _check_attr("merge", artifact) != "union"
