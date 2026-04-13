"""Tests for the import complexity analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_imports import _extract_imports, _module_name_from_path, analyze

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path: Path, rel_path: str, content: str) -> Path:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


# ---------------------------------------------------------------------------
# 1. Module name extraction
# ---------------------------------------------------------------------------


class TestModuleNameFromPath:
    def test_simple_file(self) -> None:
        assert _module_name_from_path(Path("foo.py")) == "foo"

    def test_nested_file(self) -> None:
        assert _module_name_from_path(Path("pkg/sub/mod.py")) == "pkg.sub.mod"

    def test_init_file(self) -> None:
        assert _module_name_from_path(Path("pkg/__init__.py")) == "pkg"


# ---------------------------------------------------------------------------
# 2. Import extraction
# ---------------------------------------------------------------------------


class TestImportExtraction:
    def test_simple_import(self) -> None:
        imports, stars = _extract_imports("import os\nimport sys\n", "test")
        assert "os" in imports
        assert "sys" in imports
        assert stars == []

    def test_from_import(self) -> None:
        imports, stars = _extract_imports("from pathlib import Path\n", "test")
        assert "pathlib" in imports

    def test_star_import_detected(self) -> None:
        imports, stars = _extract_imports("from os.path import *\n", "test")
        assert "os.path" in stars

    def test_syntax_error_returns_empty(self) -> None:
        imports, stars = _extract_imports("def broken(\n", "test")
        assert imports == []
        assert stars == []


# ---------------------------------------------------------------------------
# 3. Star import detection
# ---------------------------------------------------------------------------


class TestStarImports:
    def test_star_import_finding(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "bad.py", "from os.path import *\nx = 1\n")
        result = analyze(str(tmp_path))
        stars = [f for f in result.findings if "star" in f.title.lower()]
        assert len(stars) == 1
        assert stars[0].category == "import-complexity"


# ---------------------------------------------------------------------------
# 4. Circular import detection
# ---------------------------------------------------------------------------


class TestCircularImports:
    def test_simple_cycle_detected(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "import b\n")
        _write_py(tmp_path, "b.py", "import a\n")
        result = analyze(str(tmp_path))
        cycles = [f for f in result.findings if "circular" in f.title.lower()]
        assert len(cycles) >= 1

    def test_no_cycle(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "import b\n")
        _write_py(tmp_path, "b.py", "x = 1\n")
        result = analyze(str(tmp_path))
        cycles = [f for f in result.findings if "circular" in f.title.lower()]
        assert len(cycles) == 0

    def test_three_node_cycle(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "a.py", "import b\n")
        _write_py(tmp_path, "b.py", "import c\n")
        _write_py(tmp_path, "c.py", "import a\n")
        result = analyze(str(tmp_path))
        cycles = [f for f in result.findings if "circular" in f.title.lower()]
        assert len(cycles) >= 1


# ---------------------------------------------------------------------------
# 5. Import fan-out
# ---------------------------------------------------------------------------


class TestImportFanOut:
    def test_high_fan_out_detected(self, tmp_path: Path) -> None:
        imports = "\n".join(f"import mod_{i}" for i in range(20))
        _write_py(tmp_path, "heavy.py", imports + "\n")
        # Create the imported modules so they count as internal
        for i in range(20):
            _write_py(tmp_path, f"mod_{i}.py", "x = 1\n")
        result = analyze(str(tmp_path))
        fan_out = [f for f in result.findings if "fan-out" in f.title.lower()]
        assert len(fan_out) >= 1

    def test_low_fan_out_no_finding(self, tmp_path: Path) -> None:
        _write_py(tmp_path, "light.py", "import os\nimport sys\n")
        result = analyze(str(tmp_path))
        fan_out = [f for f in result.findings if "fan-out" in f.title.lower()]
        assert len(fan_out) == 0


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_directory(self, tmp_path: Path) -> None:
        result = analyze(str(tmp_path))
        assert result.status == "ok"
        assert result.findings == []

    def test_venv_excluded(self, tmp_path: Path) -> None:
        _write_py(tmp_path, ".venv/pkg/a.py", "from os.path import *\n")
        _write_py(tmp_path, "ok.py", "x = 1\n")
        result = analyze(str(tmp_path))
        assert all(".venv" not in f.file_path for f in result.findings)
