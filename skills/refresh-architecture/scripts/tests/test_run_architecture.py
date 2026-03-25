"""Tests for scripts/run_architecture.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import run_architecture


def _refresh_script_path() -> str:
    return str((Path(__file__).resolve().parents[1] / "refresh_architecture.sh").resolve())


def test_main_passes_target_env_and_overrides(tmp_path: Path) -> None:
    """Wrapper should run refresh script in target dir with expected env vars."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        rc = run_architecture.main([
            "--target-dir", str(target),
            "--python-src-dir", "app",
            "--ts-src-dir", "frontend",
            "--migrations-dir", "db/migrations",
            "--arch-dir", "docs/architecture-analysis",
            "--python", "python3.11",
        ])

    assert rc == 0
    args, kwargs = mock_run.call_args
    assert args[0] == ["bash", _refresh_script_path()]
    assert kwargs["cwd"] == target.resolve()

    env = kwargs["env"]
    assert env["SCRIPTS_DIR"] == str((Path(__file__).resolve().parents[1]).resolve())
    assert env["PYTHON_SRC_DIR"] == "app"
    assert env["TS_SRC_DIR"] == "frontend"
    assert env["MIGRATIONS_DIR"] == "db/migrations"
    assert env["ARCH_DIR"] == "docs/architecture-analysis"
    assert env["PYTHON"] == "python3.11"


def test_main_quick_adds_flag(tmp_path: Path) -> None:
    """--quick should append the quick flag for refresh_architecture.sh."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        rc = run_architecture.main([
            "--target-dir", str(target),
            "--quick",
        ])

    assert rc == 0
    args, _ = mock_run.call_args
    assert args[0] == ["bash", _refresh_script_path(), "--quick"]


def test_main_returns_child_exit_code(tmp_path: Path) -> None:
    """Wrapper should return refresh script exit code."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=17)
        rc = run_architecture.main(["--target-dir", str(target)])

    assert rc == 17


def test_main_missing_target_returns_error_code(tmp_path: Path) -> None:
    """Missing target directory should fail before spawning subprocess."""
    missing = tmp_path / "missing"

    with patch("run_architecture.subprocess.run") as mock_run:
        rc = run_architecture.main(["--target-dir", str(missing)])

    assert rc == 2
    mock_run.assert_not_called()


def test_main_launch_failure_returns_error_code(tmp_path: Path) -> None:
    """Launcher errors should map to non-zero wrapper failure."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("exec failed")
        rc = run_architecture.main(["--target-dir", str(target)])

    assert rc == 1
