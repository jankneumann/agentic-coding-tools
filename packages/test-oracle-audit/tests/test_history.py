"""Tests for the history stage (spec: Git History Signals; design D6).

Scenario ids (openspec/changes/pilot-test-quality-audit/specs/test-oracle-audit/spec.md):

- ``test-oracle-audit.33`` Shallow clone degrades
- ``test-oracle-audit.34`` Small denominator is insufficient
- ``test-oracle-audit.35`` Regression pin is detected

API under test (defined by these tests, constrained by the spec and design D6)::

    history.run_history(entries, *, repo_root, source_paths=None) -> list[StageRecord]

Every test builds a synthetic repository in ``tmp_path`` with explicit, dated
commits; nothing touches the network or the surrounding checkout.
"""

from __future__ import annotations

import ast
import os
import shutil
import stat
import subprocess
import textwrap
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from test_oracle_audit import history
from test_oracle_audit.records import StageRecord, TestEntry, TestId, content_hash

GIT = shutil.which("git") or "git"

SRC_PATH = "src/pkg/calc.py"
SRC_MODULE = "pkg.calc"
OTHER_SRC_PATH = "src/pkg/util.py"
OTHER_SRC_MODULE = "pkg.util"
TEST_PATH = "tests/test_calc.py"


# --- synthetic repository helpers -----------------------------------------


class Repo:
    """A tiny git repo with deterministic authorship and strictly increasing dates."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._tick = 0
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def _env(self) -> dict[str, str]:
        self._tick += 1
        stamp = f"2024-01-01T00:{self._tick // 60:02d}:{self._tick % 60:02d}+0000"
        env = dict(os.environ)
        env.update(
            GIT_AUTHOR_NAME="fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid",
            GIT_COMMITTER_NAME="fixture",
            GIT_COMMITTER_EMAIL="fixture@example.invalid",
            GIT_AUTHOR_DATE=stamp,
            GIT_COMMITTER_DATE=stamp,
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_NOSYSTEM="1",
        )
        return env

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            [GIT, *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
            env=self._env(),
        )
        return proc.stdout

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")

    def commit(self, subject: str, files: Mapping[str, str] | None = None) -> None:
        for rel, text in (files or {}).items():
            self.write(rel, text)
        self.git("add", "-A")
        self.git("-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", subject)

    def mv(self, old: str, new: str, subject: str) -> None:
        (self.root / new).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", old, new)
        self.git("-c", "commit.gpgsign=false", "commit", "-q", "-m", subject)


def calc_src(rev: int) -> str:
    return f"def add(a, b):\n    return a + b  # rev {rev}\n"


def util_src(rev: int) -> str:
    return f"def twice(a):\n    return a * 2  # rev {rev}\n"


def calc_tests(*, f_assert: int = 2, f_setup: int = 1, g_assert: int = 5) -> str:
    """A test module with two independent tests, ``test_f`` and ``test_g``."""
    return textwrap.dedent(
        f"""\
        from pkg.calc import add


        def test_f():
            x = {f_setup}
            assert add(x, 1) == {f_assert}


        def test_g():
            y = 4
            assert add(y, 1) == {g_assert}
        """
    )


def entry_for(
    repo_root: Path,
    rel_path: str,
    name: str,
    *,
    cls: str | None = None,
    covered: tuple[str, ...] = (SRC_MODULE,),
) -> TestEntry:
    """A :class:`TestEntry` for a test function as it exists in the working tree."""
    source = (repo_root / rel_path).read_text("utf-8")
    tree = ast.parse(source)
    scope = tree.body
    if cls is not None:
        scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls).body
    node = next(n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name)
    node_id = f"{rel_path}::{cls}::{name}" if cls else f"{rel_path}::{name}"
    return TestEntry(
        test_id=TestId(node_id=node_id, content_hash=content_hash(source, name, cls)),
        path=rel_path,
        line_start=node.lineno,
        line_end=node.end_lineno or node.lineno,
        function_name=name,
        class_name=cls,
        fixtures=(),
        covered_modules=covered,
    )


def run(
    repo_root: Path,
    entries: list[TestEntry],
    source_paths: Mapping[str, str] | None = None,
) -> list[StageRecord]:
    if source_paths is None:
        source_paths = {SRC_MODULE: SRC_PATH, OTHER_SRC_MODULE: OTHER_SRC_PATH}
    return history.run_history(entries, repo_root=repo_root, source_paths=source_paths)


def only(records: list[StageRecord]) -> StageRecord:
    assert len(records) == 1
    return records[0]


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "repo")


# --- record shape ----------------------------------------------------------


def test_ok_record_shape_and_schema(repo: Repo, schema_validator: Callable[..., None]) -> None:
    """Scenario test-oracle-audit.34: an ok history record is a schema-valid ``history`` record per test."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    repo.commit("feat: tweak calc", {SRC_PATH: calc_src(1)})
    entries = [entry_for(repo.root, TEST_PATH, "test_f"), entry_for(repo.root, TEST_PATH, "test_g")]

    records = run(repo.root, entries)

    assert [r.test_id for r in records] == [e.test_id for e in entries]
    for rec in records:
        assert rec.stage == "history"
        assert rec.status == "ok"
        assert rec.evidence_class == "history"
        assert set(rec.payload) >= {"co_change_ratio", "co_change_denominator", "added_with_fix"}
        assert isinstance(rec.payload["co_change_denominator"], int)
        assert isinstance(rec.payload["added_with_fix"], bool)
        schema_validator(rec.to_json())


def test_no_entries_yields_no_records(repo: Repo) -> None:
    """Scenario test-oracle-audit.34: with no tests there is nothing to record."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    assert run(repo.root, []) == []


# --- co_change_ratio --------------------------------------------------------


def _mixed_history(repo: Repo) -> None:
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    # six commits change the covered module after test_f exists
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})  # 1: module created, tests untouched
    repo.commit("fix: calc a", {SRC_PATH: calc_src(1), TEST_PATH: calc_tests(f_assert=3)})  # 2: hit
    repo.commit("feat: calc b", {SRC_PATH: calc_src(2)})  # 3: tests untouched
    repo.commit(  # 4: only a setup (non-assertion) line of test_f changes
        "feat: calc c", {SRC_PATH: calc_src(3), TEST_PATH: calc_tests(f_assert=3, f_setup=7)}
    )
    repo.commit(  # 5: only test_g's assertion changes
        "feat: calc d", {SRC_PATH: calc_src(4), TEST_PATH: calc_tests(f_assert=3, f_setup=7, g_assert=6)}
    )
    repo.commit(  # 6: hit again
        "feat: calc e",
        {SRC_PATH: calc_src(5), TEST_PATH: calc_tests(f_assert=9, f_setup=7, g_assert=6)},
    )
    # a test-only assertion edit never changes the covered module, so it is outside the denominator
    repo.commit("test: tidy", {TEST_PATH: calc_tests(f_assert=10, f_setup=7, g_assert=6)})


def test_co_change_ratio_counts_commits_that_rewrite_assertion_lines(repo: Repo) -> None:
    """Scenario test-oracle-audit.34 (D6): ratio = co-changed commits / commits changing covered modules.

    Commits that change only a setup line of the test, or only another test
    function's assertion, are in the denominator but not the numerator; commits
    touching only the test are not in the denominator.
    """
    _mixed_history(repo)

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.status == "ok"
    assert rec.payload["co_change_denominator"] == 6
    assert rec.payload["co_change_ratio"] == pytest.approx(2 / 6)


def test_co_change_ratio_is_per_test_function(repo: Repo) -> None:
    """Scenario test-oracle-audit.34 (D6): a sibling test's assertion edit is not this test's co-change."""
    _mixed_history(repo)

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_g")]))

    assert rec.payload["co_change_denominator"] == 6
    # test_g's assertion lines change only in commit #5 of the six.
    assert rec.payload["co_change_ratio"] == pytest.approx(1 / 6)


def test_zero_co_change_is_a_numeric_zero_not_insufficient(repo: Repo) -> None:
    """Scenario test-oracle-audit.34: with at least three commits and no co-change the ratio is 0.0."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    for rev in range(4):
        repo.commit(f"feat: calc {rev}", {SRC_PATH: calc_src(rev)})

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.payload["co_change_denominator"] == 4
    assert rec.payload["co_change_ratio"] == 0


def test_every_commit_co_changing_gives_ratio_one(repo: Repo) -> None:
    """Scenario test-oracle-audit.34: a test rewritten with every source change has ratio 1."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests(f_assert=2)})
    for rev in range(3):
        repo.commit(
            f"feat: calc {rev}",
            {SRC_PATH: calc_src(rev), TEST_PATH: calc_tests(f_assert=100 + rev)},
        )

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.payload["co_change_denominator"] == 3
    assert rec.payload["co_change_ratio"] == pytest.approx(1.0)


def test_commit_touching_two_covered_modules_counts_once(repo: Repo) -> None:
    """Scenario test-oracle-audit.34 (D6): "commits that change any covered source module" are distinct commits."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    repo.commit("feat: add util", {OTHER_SRC_PATH: util_src(0)})
    repo.commit(
        "feat: both",
        {SRC_PATH: calc_src(1), OTHER_SRC_PATH: util_src(1), TEST_PATH: calc_tests(f_assert=3)},
    )
    repo.commit("feat: calc only", {SRC_PATH: calc_src(2)})
    entry = entry_for(repo.root, TEST_PATH, "test_f", covered=(SRC_MODULE, OTHER_SRC_MODULE))

    rec = only(run(repo.root, [entry]))

    assert rec.payload["co_change_denominator"] == 4
    assert rec.payload["co_change_ratio"] == pytest.approx(1 / 4)


def test_only_covered_modules_count(repo: Repo) -> None:
    """Scenario test-oracle-audit.34 (D6): changes to modules the test does not cover are ignored."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    repo.commit("feat: calc 1", {SRC_PATH: calc_src(1)})
    for rev in range(5):  # noise in a module the test does not cover
        repo.commit(f"feat: util {rev}", {OTHER_SRC_PATH: util_src(rev)})
    entry = entry_for(repo.root, TEST_PATH, "test_f", covered=(SRC_MODULE,))

    rec = only(run(repo.root, [entry]))

    assert rec.payload["co_change_denominator"] == 2
    assert rec.payload["co_change_ratio"] == "insufficient"


# --- small denominator ------------------------------------------------------


def test_fewer_than_three_commits_is_insufficient(repo: Repo, schema_validator: Callable[..., None]) -> None:
    """Scenario test-oracle-audit.34: two commits changing covered modules -> ``insufficient``."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    repo.commit("feat: calc 1", {SRC_PATH: calc_src(1), TEST_PATH: calc_tests(f_assert=3)})

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.status == "ok"
    assert rec.payload["co_change_denominator"] == 2
    assert rec.payload["co_change_ratio"] == "insufficient"
    schema_validator(rec.to_json())


def test_exactly_three_commits_is_sufficient(repo: Repo) -> None:
    """Scenario test-oracle-audit.34 (D6): the denominator threshold is 3 inclusive."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    repo.commit("feat: calc 1", {SRC_PATH: calc_src(1), TEST_PATH: calc_tests(f_assert=3)})
    repo.commit("feat: calc 2", {SRC_PATH: calc_src(2)})

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.payload["co_change_denominator"] == 3
    assert rec.payload["co_change_ratio"] == pytest.approx(1 / 3)


def test_no_covered_modules_is_insufficient_with_zero_denominator(repo: Repo) -> None:
    """Scenario test-oracle-audit.34: a test covering no source module has denominator 0 -> ``insufficient``."""
    repo.commit("chore: init", {"README.md": "hi\n", SRC_PATH: calc_src(0)})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    entry = entry_for(repo.root, TEST_PATH, "test_f", covered=())

    rec = only(run(repo.root, [entry]))

    assert rec.status == "ok"
    assert rec.payload["co_change_denominator"] == 0
    assert rec.payload["co_change_ratio"] == "insufficient"


# --- added_with_fix ---------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("fix: handle empty input", True),
        ("fix(parser): handle empty input", True),
        ("fix!: drop legacy path", True),
        ("fix(api)!: drop legacy path", True),
        ("fixup! feat: add calc", False),
        ("feat: add calc", False),
        ("feat(fix): add calc", False),
        ("chore: fix typo", False),
        ("Fix: capitalised", False),
        ("prefix: not a fix", False),
    ],
)
def test_added_with_fix_follows_the_introducing_commit_subject(
    repo: Repo, subject: str, expected: bool
) -> None:
    """Scenario test-oracle-audit.35: only conventional ``fix`` introductions set ``added_with_fix``."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit(subject, {TEST_PATH: calc_tests()})
    repo.commit("feat: add calc", {SRC_PATH: calc_src(0)})

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.status == "ok"
    assert rec.payload["added_with_fix"] is expected


def test_later_fix_commit_touching_the_test_does_not_make_it_a_regression_pin(repo: Repo) -> None:
    """Scenario test-oracle-audit.35: the *introducing* commit decides, not later edits of the test."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.commit("fix: adjust expectation", {TEST_PATH: calc_tests(f_assert=3)})

    rec = only(run(repo.root, [entry_for(repo.root, TEST_PATH, "test_f")]))

    assert rec.payload["added_with_fix"] is False


def test_function_added_to_existing_file_is_attributed_to_the_later_commit(repo: Repo) -> None:
    """Scenario test-oracle-audit.35 (D6 introduction rule): attribution is per function, not per file.

    The file is created by a ``feat`` commit; ``test_late`` is added by a later
    ``fix`` commit and is the regression pin, ``test_early`` is not.
    """
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit(
        "feat: add early test",
        {TEST_PATH: "from pkg.calc import add\n\n\ndef test_early():\n    assert add(1, 1) == 2\n"},
    )
    repo.commit(
        "fix(calc): add late regression test",
        {
            TEST_PATH: (
                "from pkg.calc import add\n\n\ndef test_early():\n    assert add(1, 1) == 2\n\n\n"
                "def test_late():\n    assert add(2, 2) == 4\n"
            )
        },
    )
    early = entry_for(repo.root, TEST_PATH, "test_early")
    late = entry_for(repo.root, TEST_PATH, "test_late")

    rec_early, rec_late = run(repo.root, [early, late])

    assert rec_early.test_id == early.test_id
    assert rec_early.payload["added_with_fix"] is False
    assert rec_late.test_id == late.test_id
    assert rec_late.payload["added_with_fix"] is True


def test_function_added_by_feat_to_a_file_created_by_fix_is_not_a_pin(repo: Repo) -> None:
    """Scenario test-oracle-audit.35 (D6): a ``fix`` that created the file does not taint later functions."""
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit(
        "fix: initial regression test",
        {TEST_PATH: "from pkg.calc import add\n\n\ndef test_first():\n    assert add(1, 1) == 2\n"},
    )
    repo.commit(
        "feat: add second test",
        {
            TEST_PATH: (
                "from pkg.calc import add\n\n\ndef test_first():\n    assert add(1, 1) == 2\n\n\n"
                "def test_second():\n    assert add(2, 2) == 4\n"
            )
        },
    )

    first, second = run(
        repo.root,
        [entry_for(repo.root, TEST_PATH, "test_first"), entry_for(repo.root, TEST_PATH, "test_second")],
    )

    assert first.payload["added_with_fix"] is True
    assert second.payload["added_with_fix"] is False


def test_added_with_fix_follows_a_file_rename(repo: Repo) -> None:
    """Scenario test-oracle-audit.35 (D6): ``--follow`` finds the introduction under the old path."""
    new_path = "tests/unit/test_calc_renamed.py"
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("fix: regression for add", {TEST_PATH: calc_tests()})
    repo.mv(TEST_PATH, new_path, "refactor: move tests")

    rec = only(run(repo.root, [entry_for(repo.root, new_path, "test_f")]))

    assert rec.status == "ok"
    assert rec.payload["added_with_fix"] is True


def test_rename_commit_is_not_the_introduction(repo: Repo) -> None:
    """Scenario test-oracle-audit.35 (D6): a ``fix`` commit that merely renames the file is not the introduction."""
    new_path = "tests/unit/test_calc_renamed.py"
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.mv(TEST_PATH, new_path, "fix: move tests to the right folder")

    rec = only(run(repo.root, [entry_for(repo.root, new_path, "test_f")]))

    assert rec.payload["added_with_fix"] is False


def test_function_added_after_a_rename_is_attributed_to_its_own_commit(repo: Repo) -> None:
    """Scenario test-oracle-audit.35 (D6): introduction after a rename is still found per function."""
    new_path = "tests/unit/test_calc_renamed.py"
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add tests", {TEST_PATH: calc_tests()})
    repo.mv(TEST_PATH, new_path, "refactor: move tests")
    repo.commit(
        "fix(calc): regression pin after the move",
        {new_path: calc_tests() + "\n\ndef test_h():\n    assert add(3, 3) == 6\n"},
    )

    f_rec, h_rec = run(
        repo.root,
        [entry_for(repo.root, new_path, "test_f"), entry_for(repo.root, new_path, "test_h")],
    )

    assert f_rec.payload["added_with_fix"] is False
    assert h_rec.payload["added_with_fix"] is True


def test_method_inside_a_test_class_is_located_by_name(repo: Repo) -> None:
    """Scenario test-oracle-audit.35: class-based tests are attributed to the commit that added the method."""
    base = "from pkg.calc import add\n\n\nclass TestAdd:\n    def test_one(self):\n        assert add(1, 1) == 2\n"
    repo.commit("chore: init", {"README.md": "hi\n"})
    repo.commit("feat: add class", {TEST_PATH: base})
    repo.commit(
        "fix: add regression method",
        {TEST_PATH: base + "\n    def test_two(self):\n        assert add(2, 2) == 4\n"},
    )

    one, two = run(
        repo.root,
        [
            entry_for(repo.root, TEST_PATH, "test_one", cls="TestAdd"),
            entry_for(repo.root, TEST_PATH, "test_two", cls="TestAdd"),
        ],
    )

    assert one.payload["added_with_fix"] is False
    assert two.payload["added_with_fix"] is True


# --- shallow clones ---------------------------------------------------------

FORBIDDEN_NETWORK_TOKENS = {
    "fetch",
    "pull",
    "clone",
    "push",
    "ls-remote",
    "--unshallow",
    "--deepen",
    "--depth",
}


def _shallow_clone(origin: Repo, dest: Path) -> Path:
    subprocess.run(
        [GIT, "clone", "-q", "--depth", "1", f"file://{origin.root}", str(dest)],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
    )
    return dest


def _logging_git_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a ``git`` shim first on PATH that logs argv and delegates to the real git."""
    bindir = tmp_path / "shim-bin"
    bindir.mkdir()
    log = tmp_path / "git-invocations.log"
    log.write_text("", encoding="utf-8")
    shim = bindir / "git"
    shim.write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{log}"\nexec "{GIT}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return log


@pytest.fixture
def shallow_clone(tmp_path: Path) -> tuple[Path, list[TestEntry]]:
    origin = Repo(tmp_path / "origin")
    origin.commit("chore: init", {"README.md": "hi\n"})
    origin.commit("fix: add tests", {TEST_PATH: calc_tests()})
    origin.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    origin.commit("feat: calc 1", {SRC_PATH: calc_src(1), TEST_PATH: calc_tests(f_assert=3)})
    origin.commit("feat: calc 2", {SRC_PATH: calc_src(2)})
    clone = _shallow_clone(origin, tmp_path / "clone")
    entries = [entry_for(clone, TEST_PATH, "test_f"), entry_for(clone, TEST_PATH, "test_g")]
    return clone, entries


def test_shallow_clone_degrades_every_record(
    shallow_clone: tuple[Path, list[TestEntry]], schema_validator: Callable[..., None]
) -> None:
    """Scenario test-oracle-audit.33: a shallow clone yields ``degraded`` / ``shallow_history`` for every test."""
    clone, entries = shallow_clone
    assert (clone / ".git" / "shallow").exists(), "fixture must really be shallow"

    records = run(clone, entries)

    assert [r.test_id for r in records] == [e.test_id for e in entries]
    for rec in records:
        assert rec.stage == "history"
        assert rec.status == "degraded"
        assert rec.reason == "shallow_history"
        assert rec.evidence_class == "history"
        schema_validator(rec.to_json())


def test_shallow_clone_runs_no_network_git_command_and_stays_shallow(
    shallow_clone: tuple[Path, list[TestEntry]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario test-oracle-audit.33: the stage never fetches or unshallows (D6)."""
    clone, entries = shallow_clone
    log = _logging_git_on_path(tmp_path, monkeypatch)

    records = run(clone, entries)

    assert records and all(r.reason == "shallow_history" for r in records)
    invocations = [line.split() for line in log.read_text("utf-8").splitlines() if line.strip()]
    for argv in invocations:
        assert not (FORBIDDEN_NETWORK_TOKENS & set(argv)), f"network git command ran: {argv}"
        assert not (argv[:2] == ["remote", "update"] or argv[:2] == ["remote", "show"]), argv
        assert not any(tok.startswith("file://") for tok in argv), argv
    # The shallow boundary is untouched: still one commit, still flagged shallow.
    assert (clone / ".git" / "shallow").exists()
    count = subprocess.run(
        [GIT, "rev-list", "--count", "HEAD"], cwd=clone, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert count == "1"


def test_shallow_clone_makes_no_network_call_even_if_python_network_is_blocked(
    shallow_clone: tuple[Path, list[TestEntry]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario test-oracle-audit.33: the degraded path needs no network at all (sockets forbidden)."""
    import socket

    def _no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("history stage opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    clone, entries = shallow_clone

    records = run(clone, entries)

    assert all(r.status == "degraded" and r.reason == "shallow_history" for r in records)


def test_full_clone_is_not_degraded(tmp_path: Path) -> None:
    """Scenario test-oracle-audit.33 (converse): a non-shallow clone of the same history computes real signals."""
    origin = Repo(tmp_path / "origin")
    origin.commit("chore: init", {"README.md": "hi\n"})
    origin.commit("fix: add tests", {TEST_PATH: calc_tests()})
    origin.commit("feat: add calc", {SRC_PATH: calc_src(0)})
    full = tmp_path / "full"
    subprocess.run(
        [GIT, "clone", "-q", f"file://{origin.root}", str(full)],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
    )

    rec = only(run(full, [entry_for(full, TEST_PATH, "test_f")]))

    assert rec.status == "ok"
    assert rec.reason is None
    assert rec.payload["added_with_fix"] is True
    assert rec.payload["co_change_ratio"] == "insufficient"
