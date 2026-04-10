"""Tests for scripts/check_docker_imports.py.

Covers:
- collect_imports: finds top-level packages in Python source
- collect_dockerfile_copies: parses Dockerfile COPY statements
- check_dockerfile_imports: end-to-end check with missing/unused detection
- CLI exit codes and error messages
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# Load the script as a module (it's in scripts/, not src/, so it's not on sys.path)
_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "check_docker_imports.py"
_spec = importlib.util.spec_from_file_location("check_docker_imports", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules["check_docker_imports"] = _module
_spec.loader.exec_module(_module)

collect_imports = _module.collect_imports
collect_dockerfile_copies = _module.collect_dockerfile_copies
check_dockerfile_imports = _module.check_dockerfile_imports
format_report = _module.format_report
main = _module.main


# =============================================================================
# collect_imports
# =============================================================================


def test_collect_imports_absolute_import(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("import json\nimport my_pkg.subpkg\n")

    imports = collect_imports(src)
    assert "json" in imports
    assert "my_pkg" in imports


def test_collect_imports_from_import(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("from evaluation.gen_eval import mcp_service\n")

    imports = collect_imports(src)
    assert "evaluation" in imports
    assert "src/a.py" in imports["evaluation"]


def test_collect_imports_skips_relative_imports(tmp_path: Path) -> None:
    src = tmp_path / "src"
    pkg = src / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").touch()
    (pkg / "a.py").write_text("from . import sibling\nfrom ..other import thing\n")

    imports = collect_imports(src)
    # Relative imports don't produce top-level packages
    assert "sibling" not in imports
    assert "other" not in imports


def test_collect_imports_skips_pycache(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"fake")
    (src / "b.py").write_text("import real_pkg\n")

    imports = collect_imports(src)
    assert "real_pkg" in imports
    # Ensure nothing bogus leaked from __pycache__
    assert all(not f.startswith("__pycache__") for pkg_files in imports.values() for f in pkg_files)


def test_collect_imports_handles_syntax_errors_gracefully(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.py").write_text("this is not valid python !!!")
    (src / "good.py").write_text("import ok_pkg\n")

    imports = collect_imports(src)
    assert "ok_pkg" in imports
    # bad.py contributed no imports — doesn't crash the whole scan


def test_collect_imports_tracks_multiple_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("import shared_pkg\n")
    (src / "b.py").write_text("from shared_pkg import thing\n")

    imports = collect_imports(src)
    assert set(imports["shared_pkg"]) == {"src/a.py", "src/b.py"}


# =============================================================================
# collect_dockerfile_copies
# =============================================================================


def test_collect_copies_simple(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        dedent(
            """\
            FROM python:3.12-slim
            COPY src/ /app/src/
            COPY evaluation/ /app/evaluation/
            """
        )
    )
    copies = collect_dockerfile_copies(dockerfile)
    assert copies == {"src", "evaluation"}


def test_collect_copies_multi_stage_takes_last_stage(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        dedent(
            """\
            FROM python:3.12 AS builder
            COPY pyproject.toml /build/
            COPY build_only/ /build/build_only/

            FROM python:3.12-slim AS runtime
            COPY src/ /app/src/
            COPY profiles/ /app/profiles/
            """
        )
    )
    copies = collect_dockerfile_copies(dockerfile)
    # Only the runtime stage should contribute
    assert "src" in copies
    assert "profiles" in copies
    assert "build_only" not in copies


def test_collect_copies_ignores_file_copies(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        dedent(
            """\
            FROM python:3.12-slim
            COPY src/ /app/src/
            COPY agents.yaml /app/agents.yaml
            COPY teams.yaml /app/teams.yaml
            """
        )
    )
    copies = collect_dockerfile_copies(dockerfile)
    assert copies == {"src"}


def test_collect_copies_ignores_cross_stage_copies(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        dedent(
            """\
            FROM python:3.12 AS builder
            RUN echo build

            FROM python:3.12-slim
            COPY --from=builder /app/.venv /app/.venv
            COPY src/ /app/src/
            """
        )
    )
    copies = collect_dockerfile_copies(dockerfile)
    # --from copies are cross-stage artifacts, not local dirs
    assert "src" in copies
    assert ".venv" not in copies


# =============================================================================
# check_dockerfile_imports end-to-end
# =============================================================================


def _make_project(
    tmp_path: Path,
    src_files: dict[str, str],
    dockerfile_content: str,
) -> tuple[Path, Path]:
    src = tmp_path / "src"
    src.mkdir()
    for name, content in src_files.items():
        (src / name).write_text(content)
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(dockerfile_content)
    return src, dockerfile


def test_check_detects_missing_local_copy(tmp_path: Path) -> None:
    """Regression: the evaluation/ bug should be caught."""
    src, dockerfile = _make_project(
        tmp_path,
        src_files={
            "api.py": "from evaluation.gen_eval import mcp_service\n",
        },
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )

    result = check_dockerfile_imports(src_dir=src, dockerfile=dockerfile)
    assert result["status"] == "missing_copies"
    assert "evaluation" in result["missing"]  # type: ignore[operator]


def test_check_ignores_stdlib(tmp_path: Path) -> None:
    src, dockerfile = _make_project(
        tmp_path,
        src_files={
            "api.py": "import json\nimport os\nfrom pathlib import Path\n",
        },
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )

    result = check_dockerfile_imports(src_dir=src, dockerfile=dockerfile)
    assert result["status"] == "ok"
    assert result["missing"] == []


def test_check_ignores_installed_packages(tmp_path: Path) -> None:
    """Packages provided by the venv should not be flagged."""
    src, dockerfile = _make_project(
        tmp_path,
        src_files={
            # pytest is installed in the test environment
            "api.py": "import pytest\n",
        },
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )

    result = check_dockerfile_imports(src_dir=src, dockerfile=dockerfile)
    assert result["status"] == "ok"
    assert "pytest" not in result["missing"]  # type: ignore[operator]


def test_check_ignores_src_itself(tmp_path: Path) -> None:
    """``from src.x import y`` should not require a separate COPY for src."""
    src, dockerfile = _make_project(
        tmp_path,
        src_files={
            "api.py": "from src.other import thing\n",
        },
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )

    result = check_dockerfile_imports(src_dir=src, dockerfile=dockerfile)
    assert result["status"] == "ok"


def test_check_warns_unused_copy(tmp_path: Path) -> None:
    src, dockerfile = _make_project(
        tmp_path,
        src_files={
            "api.py": "import json\n",
        },
        dockerfile_content=(
            "FROM python:3.12-slim\n"
            "COPY src/ /app/src/\n"
            "COPY dead_weight/ /app/dead_weight/\n"
        ),
    )

    result = check_dockerfile_imports(src_dir=src, dockerfile=dockerfile)
    assert "dead_weight" in result["unused_copies"]  # type: ignore[operator]
    # Still "ok" because unused is only a warning
    assert result["status"] == "ok"


def test_check_excludes_data_dirs_from_unused(tmp_path: Path) -> None:
    """Data directories (profiles, cedar) should not be flagged as unused."""
    src, dockerfile = _make_project(
        tmp_path,
        src_files={"api.py": "import json\n"},
        dockerfile_content=(
            "FROM python:3.12-slim\n"
            "COPY src/ /app/src/\n"
            "COPY profiles/ /app/profiles/\n"
        ),
    )

    result = check_dockerfile_imports(
        src_dir=src,
        dockerfile=dockerfile,
        data_dirs={"profiles"},
    )
    assert "profiles" not in result["unused_copies"]  # type: ignore[operator]


# =============================================================================
# CLI
# =============================================================================


def test_cli_returns_0_on_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src, dockerfile = _make_project(
        tmp_path,
        src_files={"api.py": "import json\n"},
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )
    exit_code = main(
        ["--root", str(tmp_path), "--src", str(src), "--dockerfile", str(dockerfile)]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "OK" in captured.out


def test_cli_returns_1_on_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src, dockerfile = _make_project(
        tmp_path,
        src_files={"api.py": "from my_local_pkg import thing\n"},
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )
    exit_code = main(
        ["--root", str(tmp_path), "--src", str(src), "--dockerfile", str(dockerfile)]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "my_local_pkg" in captured.out
    assert "ERROR" in captured.out


def test_cli_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json as json_mod

    src, dockerfile = _make_project(
        tmp_path,
        src_files={"api.py": "import json\n"},
        dockerfile_content="FROM python:3.12-slim\nCOPY src/ /app/src/\n",
    )
    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "--src",
            str(src),
            "--dockerfile",
            str(dockerfile),
            "--json",
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    result = json_mod.loads(captured.out)
    assert result["status"] == "ok"
    assert result["missing"] == []


def test_cli_fails_on_missing_src(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n")
    exit_code = main(
        ["--src", str(tmp_path / "nope"), "--dockerfile", str(dockerfile)]
    )
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "src directory not found" in captured.err
