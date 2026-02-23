"""Tests for the collect_markers signal collector."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from collect_markers import (
    SKIP_DIRS,
    _file_age_days,
    _git_available,
    _should_skip,
    collect,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, rel_path: str, content: str) -> Path:
    """Write a Python file at *rel_path* under *tmp_path* and return its path."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


# ---------------------------------------------------------------------------
# 1. TODO / FIXME / HACK / XXX detection in Python files
# ---------------------------------------------------------------------------


class TestMarkerDetection:
    """Verify each marker keyword is detected with correct metadata."""

    def test_todo_detected(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "app.py", "# TODO: implement feature\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.status == "ok"
        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.source == "markers"
        assert f.category == "code-marker"
        assert f.title == "TODO: implement feature"
        assert f.detail == "implement feature"
        assert f.file_path == "app.py"
        assert f.line == 1

    def test_fixme_detected(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "util.py", "x = 1  # FIXME race condition\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert result.findings[0].title == "FIXME: race condition"

    def test_hack_detected(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "core.py", "# HACK: fragile workaround\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert "HACK" in result.findings[0].title

    def test_xxx_detected(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "core.py", "# XXX needs review\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert "XXX" in result.findings[0].title

    def test_case_insensitive_detection(self, tmp_path: Path) -> None:
        _write_py(
            tmp_path,
            "mixed.py",
            "# todo: lower\n# Todo: title\n# TODO: upper\n",
        )

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 3

    def test_multiple_markers_in_one_file(self, tmp_path: Path) -> None:
        _write_py(
            tmp_path,
            "multi.py",
            (
                "# TODO: first item\n"
                "x = 1\n"
                "# FIXME: second item\n"
                "# HACK: third item\n"
            ),
        )

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 3
        lines = [f.line for f in result.findings]
        assert lines == [1, 3, 4]

    def test_marker_with_colon(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "# TODO: with colon\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.findings[0].detail == "with colon"

    def test_marker_without_colon(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "# TODO without colon\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.findings[0].detail == "without colon"

    def test_markers_across_multiple_files(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "# TODO: in a\n")
        _write_py(tmp_path, "sub/b.py", "# FIXME: in b\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 2
        paths = {f.file_path for f in result.findings}
        assert "a.py" in paths
        assert str(Path("sub/b.py")) in paths


# ---------------------------------------------------------------------------
# 2. Severity classification
# ---------------------------------------------------------------------------


class TestSeverityClassification:
    """FIXME and HACK map to medium; TODO and XXX map to low."""

    @pytest.mark.parametrize(
        ("marker", "expected_severity"),
        [
            ("TODO", "low"),
            ("XXX", "low"),
            ("FIXME", "medium"),
            ("HACK", "medium"),
        ],
    )
    def test_severity_mapping(
        self, tmp_path: Path, marker: str, expected_severity: str
    ) -> None:
        _write_py(tmp_path, "sev.py", f"# {marker}: some text\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert result.findings[0].severity == expected_severity


# ---------------------------------------------------------------------------
# 3. Directory exclusion (.venv, node_modules, __pycache__)
# ---------------------------------------------------------------------------


class TestDirectoryExclusion:
    """Directories in SKIP_DIRS must be excluded from scanning."""

    @pytest.mark.parametrize("skip_dir", sorted(SKIP_DIRS - {".git"}))
    def test_skip_dir_excluded(self, tmp_path: Path, skip_dir: str) -> None:
        _write_py(tmp_path, f"{skip_dir}/bad.py", "# TODO: should be skipped\n")
        _write_py(tmp_path, "good.py", "# TODO: should appear\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert result.findings[0].file_path == "good.py"

    def test_nested_skip_dir_excluded(self, tmp_path: Path) -> None:
        _write_py(
            tmp_path,
            "pkg/.venv/lib/site.py",
            "# TODO: deep skip\n",
        )
        _write_py(tmp_path, "pkg/real.py", "# TODO: keep\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert result.findings[0].file_path == str(Path("pkg/real.py"))

    def test_should_skip_helper(self) -> None:
        assert _should_skip(Path(".venv/lib/foo.py")) is True
        assert _should_skip(Path("node_modules/pkg/index.py")) is True
        assert _should_skip(Path("__pycache__/mod.pyc")) is True
        assert _should_skip(Path("src/main.py")) is False


# ---------------------------------------------------------------------------
# 4. Age estimation with mocked git output
# ---------------------------------------------------------------------------


class TestAgeEstimation:
    """_file_age_days should parse git log output and compute days."""

    def test_age_days_from_git_log(self, tmp_path: Path) -> None:
        """A mocked git log returning a known date should yield expected days."""
        fake_date = "2025-01-01 12:00:00 +0000"
        mock_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=fake_date + "\n", stderr=""
        )

        with patch("collect_markers.subprocess.run", return_value=mock_proc):
            age = _file_age_days(Path("some/file.py"), str(tmp_path))

        assert age is not None
        # The date is 2025-01-01; the age should be a positive number of days.
        assert age > 0

    def test_age_days_empty_output(self, tmp_path: Path) -> None:
        """If git log returns empty output, age should be None."""
        mock_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        with patch("collect_markers.subprocess.run", return_value=mock_proc):
            age = _file_age_days(Path("new_file.py"), str(tmp_path))

        assert age is None

    def test_age_days_malformed_date(self, tmp_path: Path) -> None:
        """If git log returns garbage, age should be None."""
        mock_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not-a-date\n", stderr=""
        )

        with patch("collect_markers.subprocess.run", return_value=mock_proc):
            age = _file_age_days(Path("file.py"), str(tmp_path))

        assert age is None

    def test_collect_populates_age_when_git_available(
        self, tmp_path: Path
    ) -> None:
        """When git is available, findings should carry age_days."""
        _write_py(tmp_path, "aged.py", "# TODO: old marker\n")

        fake_date = "2024-06-15 10:00:00 +0000"
        mock_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=fake_date + "\n", stderr=""
        )

        # git_available returns True, and every subprocess.run call gets the
        # mocked CompletedProcess.
        with (
            patch("collect_markers._git_available", return_value=True),
            patch("collect_markers.subprocess.run", return_value=mock_proc),
        ):
            result = collect(str(tmp_path))

        assert len(result.findings) == 1
        assert result.findings[0].age_days is not None
        assert result.findings[0].age_days > 0


# ---------------------------------------------------------------------------
# 5. Handling when git is not available
# ---------------------------------------------------------------------------


class TestGitUnavailable:
    """When git is absent, collector must still return findings without age."""

    def test_no_git_still_collects(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "no_git.py", "# FIXME: no git here\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.status == "ok"
        assert len(result.findings) == 1
        assert result.findings[0].age_days is None

    def test_no_git_message(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "msg.py", "# TODO: check messages\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert any("git not available" in m for m in result.messages)

    def test_git_available_false_on_file_not_found(self, tmp_path: Path) -> None:
        """_git_available returns False when git binary is missing."""
        with patch(
            "collect_markers.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            assert _git_available(str(tmp_path)) is False

    def test_git_available_false_on_called_process_error(
        self, tmp_path: Path
    ) -> None:
        """_git_available returns False when not in a git repo."""
        with patch(
            "collect_markers.subprocess.run",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            assert _git_available(str(tmp_path)) is False

    def test_file_age_days_returns_none_on_os_error(
        self, tmp_path: Path
    ) -> None:
        """_file_age_days returns None when subprocess raises OSError."""
        with patch(
            "collect_markers.subprocess.run",
            side_effect=OSError("disk error"),
        ):
            age = _file_age_days(Path("file.py"), str(tmp_path))

        assert age is None


# ---------------------------------------------------------------------------
# 6. File with no markers (should return empty findings)
# ---------------------------------------------------------------------------


class TestNoMarkers:
    """A clean file with no marker comments must produce zero findings."""

    def test_empty_file(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "empty.py", "")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.status == "ok"
        assert result.findings == []

    def test_file_with_regular_comments(self, tmp_path: Path) -> None:
        _write_py(
            tmp_path,
            "clean.py",
            "# This is a normal comment\n# Nothing special here\nx = 42\n",
        )

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.status == "ok"
        assert result.findings == []

    def test_no_python_files(self, tmp_path: Path) -> None:
        """Directory with no *.py files produces no findings."""
        (tmp_path / "readme.txt").write_text("# TODO: not python\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.status == "ok"
        assert result.findings == []

    def test_empty_directory(self, tmp_path: Path) -> None:
        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.status == "ok"
        assert result.findings == []

    def test_source_result_fields(self, tmp_path: Path) -> None:
        """Verify SourceResult metadata fields on a clean scan."""
        _write_py(tmp_path, "ok.py", "x = 1\n")

        with patch("collect_markers._git_available", return_value=False):
            result = collect(str(tmp_path))

        assert result.source == "markers"
        assert result.status == "ok"
        assert result.duration_ms >= 0
        assert isinstance(result.findings, list)
        assert isinstance(result.messages, list)
