"""Behavior tests for simplify/scripts/check_test_prune.py.

Each test pins an outcome the gate is responsible for (blocked vs. allowed and
why), not the shape of the implementation that produces it.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "simplify" / "scripts"


def _load():
    path = SCRIPTS / "check_test_prune.py"
    name = "simplify_check_test_prune"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    for key, value in (("user.email", "test@example.com"), ("user.name", "Test")):
        subprocess.run(
            ["git", "config", key, value], cwd=repo, check=True, capture_output=True
        )
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "app.py").write_text("TIMEOUT = 30\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_timeout_is_thirty():\n    assert TIMEOUT == 30\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def _ledger(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "ledger.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_no_removals_needs_no_ledger(git_repo: Path):
    mod = _load()
    (git_repo / "tests" / "test_extra.py").write_text(
        "def test_added():\n    assert True\n", encoding="utf-8"
    )
    _commit(git_repo, "test: add coverage")
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", None)
    assert result.clean is True


def test_removal_without_ledger_is_blocked(git_repo: Path):
    mod = _load()
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: prune source-mirroring test")
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", None)
    assert result.clean is False
    assert "tests/test_app.py::test_timeout_is_thirty" in result.removed_tests
    assert "tests/test_app.py::test_timeout_is_thirty" in result.unjustified


def test_removal_with_justifying_ledger_is_allowed(git_repo: Path, tmp_path: Path):
    mod = _load()
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: prune source-mirroring test")
    ledger = _ledger(
        tmp_path,
        "- removed: tests/test_app.py::test_timeout_is_thirty\n"
        "  reason: source-mirroring\n"
        "  covered-by: none\n",
    )
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", ledger)
    assert result.clean is True, result


def test_change_detector_removal_must_name_a_surviving_test(git_repo: Path, tmp_path: Path):
    """A test that covered real behavior cannot be dropped into a coverage hole."""
    mod = _load()
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: prune change-detector test")
    ledger = _ledger(
        tmp_path,
        "- removed: tests/test_app.py::test_timeout_is_thirty\n"
        "  reason: change-detector\n"
        "  covered-by: none\n",
    )
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", ledger)
    assert result.clean is False
    assert any("covered-by" in err for err in result.ledger_errors)


def test_file_level_ledger_entry_covers_every_test_in_that_file(git_repo: Path, tmp_path: Path):
    mod = _load()
    (git_repo / "tests" / "test_app.py").unlink()
    _commit(git_repo, "test: drop implementation-coupled suite")
    ledger = _ledger(
        tmp_path,
        "- removed: tests/test_app.py\n"
        "  reason: duplicative\n"
        "  covered-by: tests/test_integration.py::test_request_lifecycle\n",
    )
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", ledger)
    assert result.clean is True, result
    assert "tests/test_app.py" in result.removed_test_files


def test_production_edit_in_prune_range_is_blocked(git_repo: Path, tmp_path: Path):
    """Pruning and simplifying in one commit hides which one caused a regression."""
    mod = _load()
    (git_repo / "src" / "app.py").write_text("TIMEOUT = 30  # simplified\n", encoding="utf-8")
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: prune and refactor together")
    ledger = _ledger(
        tmp_path,
        "- removed: tests/test_app.py::test_timeout_is_thirty\n"
        "  reason: source-mirroring\n"
        "  covered-by: none\n",
    )
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", ledger)
    assert result.clean is False
    assert "src/app.py" in result.production_files_touched


def test_unknown_reason_code_is_rejected(git_repo: Path, tmp_path: Path):
    mod = _load()
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: prune")
    ledger = _ledger(
        tmp_path,
        "- removed: tests/test_app.py::test_timeout_is_thirty\n"
        "  reason: felt-unnecessary\n"
        "  covered-by: none\n",
    )
    result = mod.evaluate(git_repo, "HEAD~1", "HEAD", ledger)
    assert result.clean is False
    assert any("unknown reason" in err for err in result.ledger_errors)


def test_cli_exit_codes(git_repo: Path, tmp_path: Path):
    """0 allows the prune phase to proceed; 2 blocks it."""
    mod = _load()
    (git_repo / "tests" / "test_app.py").write_text(
        "from src.app import TIMEOUT\n\n"
        "def test_request_times_out_after_timeout():\n    assert TIMEOUT > 0\n",
        encoding="utf-8",
    )
    _commit(git_repo, "test: prune")
    assert mod.main(["--base", "HEAD~1", "--head", "HEAD", "--repo", str(git_repo)]) == 2
    ledger = _ledger(
        tmp_path,
        "- removed: tests/test_app.py::test_timeout_is_thirty\n"
        "  reason: source-mirroring\n",
    )
    assert (
        mod.main(
            [
                "--base", "HEAD~1", "--head", "HEAD",
                "--repo", str(git_repo), "--ledger", str(ledger),
            ]
        )
        == 0
    )
