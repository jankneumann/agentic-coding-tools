from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from detect_profile import detect_profiles  # noqa: E402


def test_detect_profile_generic(tmp_path: Path) -> None:
    result = detect_profiles(tmp_path)
    assert result["primary_profile"] == "generic"
    assert result["profiles"] == ["generic"]
    assert result["confidence"] == "low"


def test_detect_profile_python(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    result = detect_profiles(tmp_path)
    assert result["primary_profile"] == "python"
    assert "python" in result["profiles"]
    assert result["confidence"] in {"med", "high"}


def test_detect_profile_mixed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    result = detect_profiles(tmp_path)
    assert result["primary_profile"] == "mixed"
    assert "mixed" in result["profiles"]
    assert "python" in result["profiles"]
    assert "node" in result["profiles"]
