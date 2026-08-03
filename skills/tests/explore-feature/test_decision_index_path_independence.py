"""Rendered decision-index links are repository-relative (ri-10 task 6.2, D12).

``emit_decisions_from_archive`` used to interpolate the ``archive_root`` it was
handed straight into every rendered ``Source:`` back-reference. Because the
decision index is a **committed** artifact, that turned a caller detail into
repository content: invoking the emitter with an absolute root wrote the
checkout's absolute path into ``docs/decisions/<capability>.md``, and any
freshness check comparing a fresh render against the committed tree reported
drift that did not exist.

These assertions are on the **rendered bytes**, not on a diff count, so they name
the defect rather than one of its symptoms:

* no rendered file may contain the absolute archive root or the absolute
  repository root;
* every ``Source:`` back-reference must be a repository-relative path that
  actually resolves inside the repository;
* a relative and an absolute archive root must render byte-identical trees.

The final test renders the *real* repository with an absolute archive root. It
asserts only the absence of machine paths — never freshness — so it cannot fail
because someone added an ``architectural:`` tag without regenerating.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "explore-feature" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

REPO_ROOT = Path(__file__).resolve().parents[3]

from archive_index import emit_decisions_from_archive  # noqa: E402

#: A rendered back-reference: ``- Source: [<text>](<href>) (D<n>)``.
_SOURCE_LINE_RE = re.compile(
    r"^- Source: \[(?P<text>[^\]]+)\]\((?P<href>[^)]+)\) \(D(?P<index>\d+)\)$"
)

_CAPABILITY = "software-factory-tooling"


# --------------------------------------------------------------------------- #
# A miniature repository carrying real emitter inputs
# --------------------------------------------------------------------------- #
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_repository(root: Path) -> Path:
    """Create a checkout with two archived session logs carrying tagged decisions.

    ``.git`` is created as a plain directory: the emitter only needs the
    repository-root *marker*, so the fixture stays free of a real ``git init``.
    """
    (root / ".git").mkdir(parents=True, exist_ok=True)
    _write(root / "openspec" / "specs" / _CAPABILITY / "spec.md", f"# {_CAPABILITY}\n")

    _write(
        root / "openspec" / "changes" / "archive" / "2026-01-05-first-change" / "session-log.md",
        "# Session Log — first-change\n"
        "\n"
        "## Phase: Plan (2026-01-05)\n"
        "\n"
        "### Decisions\n"
        "\n"
        f"1. **Pin worktrees while idle** `architectural: {_CAPABILITY}` — GC would "
        "reclaim them mid-pause\n",
    )
    _write(
        root / "openspec" / "changes" / "archive" / "2026-02-09-second-change" / "session-log.md",
        "# Session Log — second-change\n"
        "\n"
        "## Phase: Implementation (2026-02-09)\n"
        "\n"
        "### Decisions\n"
        "\n"
        f"1. **Use `--` as the agent-branch separator** `architectural: {_CAPABILITY}` "
        "— git refuses nested ref names\n",
    )
    return root


def render(repository: Path, output_dir: Path, *, absolute: bool) -> int:
    """Render the index for *repository* from a relative or absolute archive root."""
    base = repository.resolve() if absolute else repository
    return emit_decisions_from_archive(
        archive_root=base / "openspec" / "changes",
        output_dir=output_dir,
        capabilities_root=base / "openspec" / "specs",
        strict=False,
    )


def read_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.md"))
        if path.is_file()
    }


def source_lines(tree: dict[str, bytes]) -> list[tuple[str, str]]:
    """Return ``(file, line)`` for every rendered ``- Source:`` back-reference."""
    return [
        (name, line)
        for name, blob in tree.items()
        for line in blob.decode("utf-8").splitlines()
        if line.startswith("- Source:")
    ]


# --------------------------------------------------------------------------- #
# Scenario: Rendered links do not embed the archive root
# --------------------------------------------------------------------------- #
class TestRenderedLinksAreRepositoryRelative:
    def test_the_fixture_renders_back_references_at_all(self, tmp_path: Path) -> None:
        """Without ``Source:`` lines every other assertion here is vacuous."""
        repo = build_repository(tmp_path / "checkout")
        out = tmp_path / "rendered"

        count = render(repo, out, absolute=True)

        assert count == 2
        tree = read_tree(out)
        assert f"{_CAPABILITY}.md" in tree
        assert len(source_lines(tree)) == 2

    def test_no_rendered_file_contains_the_absolute_archive_root(
        self, tmp_path: Path
    ) -> None:
        repo = build_repository(tmp_path / "checkout")
        out = tmp_path / "rendered"
        render(repo, out, absolute=True)

        repo_root = repo.resolve()
        archive_root = repo_root / "openspec" / "changes"
        offenders = {
            name: blob.decode("utf-8")
            for name, blob in read_tree(out).items()
            if str(archive_root) in blob.decode("utf-8")
            or str(repo_root) in blob.decode("utf-8")
        }

        assert not offenders, (
            "rendered output embeds the absolute archive root, so the committed "
            f"index depends on the caller's path conventions: {offenders}"
        )

    def test_every_source_link_is_a_repository_relative_path(
        self, tmp_path: Path
    ) -> None:
        repo = build_repository(tmp_path / "checkout")
        out = tmp_path / "rendered"
        render(repo, out, absolute=True)

        lines = source_lines(read_tree(out))
        assert lines

        for name, line in lines:
            match = _SOURCE_LINE_RE.match(line)
            assert match, f"unparseable back-reference in {name}: {line!r}"
            text = match.group("text")
            assert not text.startswith("/"), (
                f"back-reference in {name} is absolute, not repository-relative: {text!r}"
            )
            assert text.startswith("openspec/changes/"), (
                f"back-reference in {name} is not rooted at the repository: {text!r}"
            )
            assert (repo / text).is_file(), (
                f"back-reference in {name} does not resolve inside the repository: {text!r}"
            )
            assert match.group("href") == f"/{text}", (
                f"link target in {name} disagrees with its text: {line!r}"
            )


# --------------------------------------------------------------------------- #
# Scenario: Relative and absolute roots render identically
# --------------------------------------------------------------------------- #
class TestRelativeAndAbsoluteRootsAgree:
    def test_the_two_rendered_trees_are_byte_identical(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        build_repository(tmp_path / "checkout")
        monkeypatch.chdir(tmp_path)
        relative_repo = Path("checkout")

        relative_out = tmp_path / "rendered-relative"
        absolute_out = tmp_path / "rendered-absolute"
        render(relative_repo, relative_out, absolute=False)
        render(relative_repo, absolute_out, absolute=True)

        relative_tree = read_tree(relative_out)
        absolute_tree = read_tree(absolute_out)

        assert relative_tree, "the relative render produced nothing to compare"
        assert sorted(relative_tree) == sorted(absolute_tree)
        differing = sorted(
            name for name in relative_tree if relative_tree[name] != absolute_tree[name]
        )
        assert not differing, (
            "the emitter's output depends on how the archive root was spelled; "
            f"these files differ between a relative and an absolute root: {differing}"
        )

    def test_rendering_twice_from_the_same_root_stays_deterministic(
        self, tmp_path: Path
    ) -> None:
        """The pre-existing determinism guarantee must survive the fix."""
        repo = build_repository(tmp_path / "checkout")
        first = tmp_path / "first"
        second = tmp_path / "second"
        render(repo, first, absolute=True)
        render(repo, second, absolute=True)

        assert read_tree(first) == read_tree(second)


# --------------------------------------------------------------------------- #
# The real repository, asserted on absence of machine paths only
# --------------------------------------------------------------------------- #
def test_rendering_this_repository_absolutely_writes_no_machine_paths(
    tmp_path: Path,
) -> None:
    """The measured defect, on real inputs.

    Deliberately does *not* assert freshness of ``docs/decisions/`` — only that an
    absolute archive root cannot leak this checkout's location into the artifact.
    """
    out = tmp_path / "rendered"
    emit_decisions_from_archive(
        archive_root=REPO_ROOT / "openspec" / "changes",
        output_dir=out,
        capabilities_root=REPO_ROOT / "openspec" / "specs",
        strict=False,
    )

    tree = read_tree(out)
    assert len(tree) > 1, "the real archive rendered nothing, so this proves nothing"
    assert source_lines(tree), "no back-references rendered from the real archive"

    offenders = sorted(name for name, blob in tree.items() if str(REPO_ROOT).encode() in blob)
    assert not offenders, (
        f"{len(offenders)} rendered file(s) embed this checkout's absolute path: {offenders}"
    )
