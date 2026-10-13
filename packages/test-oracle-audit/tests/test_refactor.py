"""Rename-survival tests for ``test_oracle_audit.refactor`` (tasks 3.7, 3.8).

Derived from the "Refactor Survival via Private-Symbol Rename" requirement
(spec scenarios test-oracle-audit.29 to .32), the "Read-Only Audit Execution"
requirement (.7), design D3/D5 and ``RenamePayload`` in
``stage-record.schema.json``.

The module under test does not exist yet; these tests define its public API:

    run_rename_survival(suite, entries, *, repo_root, python=None) -> list[StageRecord]

One ``rename`` record per entry; payload ``{survives, renamed_symbols,
unrenamable_symbols, low_confidence}``. ``python=sys.executable`` makes the
audited suite run as ``[python, "-m", "pytest", ...]`` so no uv or network is needed.

Interpretation of the per-test counts (spec is silent): ``renamed_symbols`` and
``unrenamable_symbols`` are totals over the eligible private symbols of the
modules the test covers (``TestEntry.covered_modules``), and ``low_confidence``
is true when *any* covered module has more than half of its eligible private
symbols unrenamable.

Fixture ``tests/fixtures/execution/rename_proj`` (package ``shop``):

* ``pricing``: eligible ``_FLOOR``, ``_round_cents``, ``_tax_rate``; none unrenamable.
* ``labels``: six eligible privates. ``_exported_one``/``_exported_two`` are listed in
  ``__all__``; ``_by_string``/``_also_string`` appear as string literals (a registry
  looked up through ``globals()``); ``_plain_one``/``_plain_two`` are renamable.
  Four of six are unrenamable.
* ``catalog``: eligible ``_SEP`` and ``_slugify``; ``_slugify`` is re-exported by
  ``shop/__init__.py``. One of two is unrenamable, which is *not* more than half.
"""

from __future__ import annotations

import ast
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from test_oracle_audit.refactor import run_rename_survival

from test_oracle_audit.records import StageRecord, SuiteSpec, TestEntry, TestId, content_hash

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution"
PROJECT = "rename_proj"

PRICING = ("shop.pricing",)
LABELS = ("shop.labels",)
CATALOG = ("shop.catalog",)

COVERED_MODULES: dict[str, tuple[str, ...]] = {
    "test_price_public_only": PRICING,
    "test_imports_private_helper": PRICING,
    "test_patches_private_rate": PRICING,
    "test_label_public_only": LABELS,
    "test_all_listed_private_name_is_stable": LABELS,
    "test_slug_public_only": CATALOG,
    "test_reexported_private_name_is_stable": CATALOG,
    "test_price_and_label_public_only": PRICING + LABELS,
}

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
}


# --- helpers ---------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**_GIT_ENV, "HOME": str(cwd)},
    )
    return out.stdout


def _make_repo(dest: Path) -> Path:
    shutil.copytree(
        FIXTURES / PROJECT,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "fixture: initial commit")
    return dest


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def _worktree_count(repo: Path) -> int:
    listing = _git(repo, "worktree", "list", "--porcelain")
    return sum(1 for line in listing.splitlines() if line.startswith("worktree "))


def _suite() -> SuiteSpec:
    return SuiteSpec(
        name=PROJECT,
        project_root=".",
        test_paths=("tests",),
        source_roots=("src/shop",),
        pytest_args=("-p", "no:cacheprovider"),
    )


def _entries(repo: Path) -> list[TestEntry]:
    entries: list[TestEntry] = []
    for path in sorted((repo / "tests").glob("test_*.py")):
        rel = path.relative_to(repo).as_posix()
        source = path.read_text("utf-8")
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                entries.append(
                    TestEntry(
                        test_id=TestId(f"{rel}::{node.name}", content_hash(source, node.name)),
                        path=rel,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        function_name=node.name,
                        covered_modules=COVERED_MODULES[node.name],
                    )
                )
    return entries


@dataclass
class World:
    repo: Path
    before: dict[str, bytes]
    entries: list[TestEntry]
    records: dict[str, StageRecord]
    all_records: list[StageRecord]
    leftover: list[Path]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    """Run the rename stage once over the fixture repo; every scenario reads the same records."""
    base = tmp_path_factory.mktemp("rename")
    repo = _make_repo(base / "repo")
    scratch = base / "systmp"
    scratch.mkdir()
    entries = _entries(repo)
    before = _snapshot(repo)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TMPDIR", str(scratch))
        mp.setattr(tempfile, "tempdir", str(scratch))
        records = run_rename_survival(_suite(), entries, repo_root=repo, python=sys.executable)
    return World(
        repo=repo,
        before=before,
        entries=entries,
        records={r.test_id.node_id: r for r in records},
        all_records=records,
        leftover=list(scratch.iterdir()),
    )


def _payload(world: World, name: str) -> dict:
    matches = [r for node_id, r in world.records.items() if node_id.endswith(f"::{name}")]
    assert len(matches) == 1, f"expected exactly one record for {name}"
    return matches[0].payload


# --- record shape ------------------------------------------------------------


def test_one_schema_valid_rename_record_per_test(world: World, schema_validator: Callable[..., None]) -> None:
    """test-oracle-audit.29 to .32: each test gets one ``rename`` record matching RenamePayload."""
    assert {r.test_id for r in world.all_records} == {e.test_id for e in world.entries}
    assert len(world.all_records) == len(world.entries)
    for record in world.all_records:
        assert record.stage == "rename"
        assert record.status == "ok", (record.test_id.node_id, record.reason)
        assert record.evidence_class == "execution"
        schema_validator(record.to_json())
        assert set(record.payload) >= {"survives", "renamed_symbols", "unrenamable_symbols", "low_confidence"}
        assert isinstance(record.payload["survives"], bool)
        assert isinstance(record.payload["low_confidence"], bool)


# --- survival (scenarios .29, .30) -------------------------------------------


def test_test_importing_a_private_helper_breaks(world: World) -> None:
    """test-oracle-audit.29: a test that imports ``module._helper`` has ``survives: false`` after the rename."""
    assert _payload(world, "test_imports_private_helper")["survives"] is False


def test_test_patching_a_private_name_breaks(world: World) -> None:
    """test-oracle-audit.29: a test that patches ``module._helper`` has ``survives: false`` after the rename."""
    assert _payload(world, "test_patches_private_rate")["survives"] is False


@pytest.mark.parametrize(
    "name",
    [
        "test_price_public_only",
        "test_label_public_only",
        "test_slug_public_only",
        "test_price_and_label_public_only",
    ],
)
def test_public_only_test_survives(world: World, name: str) -> None:
    """test-oracle-audit.30: a test that uses only public names has ``survives: true``."""
    assert _payload(world, name)["survives"] is True


def test_tests_are_never_renamed(world: World) -> None:
    """test-oracle-audit.29 and D5: the rename is applied to the source tree only. If tests were
    renamed too, the private-importing tests would still pass, so they must fail."""
    broken = {
        node_id.split("::")[-1]
        for node_id, record in world.records.items()
        if record.payload["survives"] is False
    }
    assert broken == {"test_imports_private_helper", "test_patches_private_rate"}


# --- unrenamable symbols (scenario .31) --------------------------------------


def test_string_referenced_private_names_are_not_renamed_and_counted(world: World) -> None:
    """test-oracle-audit.31: ``_by_string`` and ``_also_string`` appear as string literals, so the
    registry lookup in ``label`` keeps working (the test survives) and they count as unrenamable."""
    payload = _payload(world, "test_label_public_only")
    assert payload["survives"] is True
    assert payload["unrenamable_symbols"] >= 2
    assert payload["unrenamable_symbols"] == 4  # two string-referenced + two listed in __all__
    assert payload["renamed_symbols"] == 2  # _plain_one, _plain_two


def test_names_listed_in_all_are_not_renamed(world: World) -> None:
    """test-oracle-audit.31 / D5: a private name exported in ``__all__`` keeps its name, so a test
    that imports it still passes."""
    payload = _payload(world, "test_all_listed_private_name_is_stable")
    assert payload["survives"] is True
    assert payload["unrenamable_symbols"] == 4


def test_names_reexported_by_a_public_module_are_not_renamed(world: World) -> None:
    """test-oracle-audit.31 / D5: ``shop/__init__.py`` re-exports ``_slugify``, so it is
    unrenamable and ``from shop import _slugify`` keeps working."""
    for name in ("test_reexported_private_name_is_stable", "test_slug_public_only"):
        payload = _payload(world, name)
        assert payload["survives"] is True, name
        assert payload["unrenamable_symbols"] == 1, name
        assert payload["renamed_symbols"] == 1, name  # _SEP


def test_fully_renamable_module_reports_zero_unrenamable(world: World) -> None:
    """test-oracle-audit.31: modules without excluded names report all eligible symbols as renamed."""
    for name in ("test_price_public_only", "test_imports_private_helper", "test_patches_private_rate"):
        payload = _payload(world, name)
        assert payload["renamed_symbols"] == 3, name  # _FLOOR, _round_cents, _tax_rate
        assert payload["unrenamable_symbols"] == 0, name


# --- low confidence (scenario .32) -------------------------------------------


@pytest.mark.parametrize("name", ["test_label_public_only", "test_all_listed_private_name_is_stable"])
def test_mostly_unrenamable_module_marks_its_tests_low_confidence(world: World, name: str) -> None:
    """test-oracle-audit.32: four of ``labels``' six eligible private symbols are unrenamable, so
    every test covering ``labels`` is ``low_confidence: true``."""
    assert _payload(world, name)["low_confidence"] is True


def test_low_confidence_applies_when_any_covered_module_is_mostly_unrenamable(world: World) -> None:
    """test-oracle-audit.32 / RenamePayload: a test that covers a healthy module and ``labels`` is
    low confidence because of ``labels``."""
    assert _payload(world, "test_price_and_label_public_only")["low_confidence"] is True


@pytest.mark.parametrize(
    "name",
    [
        "test_price_public_only",
        "test_imports_private_helper",
        "test_patches_private_rate",
    ],
)
def test_module_without_unrenamable_symbols_is_confident(world: World, name: str) -> None:
    """test-oracle-audit.32: no unrenamable symbols means the verdict is trusted."""
    assert _payload(world, name)["low_confidence"] is False


@pytest.mark.parametrize("name", ["test_slug_public_only", "test_reexported_private_name_is_stable"])
def test_exactly_half_unrenamable_is_not_low_confidence(world: World, name: str) -> None:
    """test-oracle-audit.32: the threshold is *more than* half, and ``catalog`` has one of two."""
    assert _payload(world, name)["low_confidence"] is False


# --- read-only execution (scenarios .6, .7) ----------------------------------


def test_the_audited_tree_is_untouched_by_the_rename_stage(world: World) -> None:
    """test-oracle-audit.6: renaming happens in the copy; source and tests in the audited tree are
    byte-identical and git-clean afterwards."""
    assert _snapshot(world.repo) == world.before
    assert _git(world.repo, "status", "--porcelain") == ""
    assert "_tax_rate" in (world.repo / "src/shop/pricing.py").read_text("utf-8")
    assert "__r" not in (world.repo / "src/shop/pricing.py").read_text("utf-8")


def test_the_stage_leaves_no_copy_or_worktree_behind(world: World) -> None:
    """test-oracle-audit.7: after the stage returns its isolated copy is gone."""
    assert world.leftover == []
    assert _worktree_count(world.repo) == 1


def test_copy_is_removed_when_the_rename_stage_raises_midway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test-oracle-audit.7: a rename stage that cannot run its suite (it may raise or degrade)
    still removes its isolated copy and leaves the audited tree alone."""
    repo = _make_repo(tmp_path / "repo")
    scratch = tmp_path / "systmp"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    before = _snapshot(repo)
    with contextlib.suppress(Exception):  # the stage may raise or degrade; both are allowed
        run_rename_survival(_suite(), _entries(repo), repo_root=repo, python=str(tmp_path / "no-such-python"))
    assert list(scratch.iterdir()) == []
    assert _worktree_count(repo) == 1
    assert _snapshot(repo) == before
    assert _git(repo, "status", "--porcelain") == ""
