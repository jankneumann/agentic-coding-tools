"""Tree-sitter interpreter resolution must not depend on a nested venv (issue #378).

The pipeline and the provenance record used to answer "is tree-sitter available?"
independently — the shell probed a per-skill `scripts/.venv` that does not exist
and nothing creates, while `detect_optional_tools()` imported `tree_sitter` in
whatever process happened to be running. So a refresh could skip the enrichment,
comment-linker and pattern-reporter stages and still stamp
`tree-sitter available: true`, leaving provenance vouching for artifacts that
were never regenerated.

These guard the two properties that prevent that: resolution reaches a
project-root venv without any nested one, and the provenance record reports the
interpreter the pipeline would actually use.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from arch_utils import interpreters  # noqa: E402
from arch_utils import provenance  # noqa: E402

NESTED_VENV = SCRIPTS_DIR / ".venv"


def _treesitter_somewhere() -> bool:
    return interpreters.resolve_treesitter_python() is not None


requires_treesitter = pytest.mark.skipif(
    not _treesitter_somewhere(),
    reason="tree-sitter is not installed in any resolvable interpreter",
)


def test_no_nested_venv_is_required() -> None:
    """The repository must not need `skills/<skill>/scripts/.venv` to exist.

    Per repository convention a virtualenv belongs to a project root, never
    inside an individual skill directory. This is the invariant the old
    hard-coded probe violated.
    """
    assert not NESTED_VENV.exists(), (
        f"{NESTED_VENV} exists — resolution must not depend on a nested venv, "
        "and this test is only meaningful without one"
    )


@requires_treesitter
def test_resolution_finds_a_project_root_interpreter() -> None:
    """Resolution succeeds with no nested venv present."""
    resolved = interpreters.resolve_treesitter_python()
    assert resolved is not None
    assert NESTED_VENV not in resolved.parents, (
        f"resolved to a nested per-skill venv: {resolved}"
    )


@requires_treesitter
def test_resolved_interpreter_imports_every_grammar_it_reports() -> None:
    """The reported availability must be the resolved interpreter's own.

    This replaces a check that the interpreter imported one fixed pair of
    modules. Resolution is now per grammar (see `test_per_grammar_resolution`),
    so the property that matters is truthfulness: whatever the resolution
    reports as available really imports *there*, because that is what the stage
    verdicts and the provenance record are both derived from.
    """
    resolution = interpreters.resolve_grammars()
    assert resolution.python is not None
    for module, available in resolution.available.items():
        result = subprocess.run(
            [str(resolution.python), "-c", f"import {module}"],
            capture_output=True,
            check=False,
        )
        assert (result.returncode == 0) is available, (
            f"{module} reported available={available} by {resolution.python}: "
            f"{result.stderr.decode()}"
        )


def _interpreter_without_treesitter() -> Path | None:
    """Find a real interpreter that cannot import tree-sitter, if one exists."""
    candidates = [
        Path(sys.base_prefix) / "bin" / "python3",
        Path("/usr/bin/python3"),
    ]
    which = shutil.which("python3")
    if which:
        candidates.append(Path(which))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "import tree_sitter"],
            capture_output=True,
            check=False,
        )
        if probe.returncode != 0:
            return candidate
    return None


def test_optional_tools_agree_with_the_resolver() -> None:
    """Provenance reports what the pipeline would use, not its own process."""
    resolved = interpreters.resolve_treesitter_python()
    tools = {t["name"]: t for t in provenance.detect_optional_tools()}

    assert "tree-sitter" in tools
    assert tools["tree-sitter"]["available"] is (resolved is not None)


@requires_treesitter
def test_optional_tools_do_not_depend_on_the_calling_interpreter() -> None:
    """The record must not change with *how* the refresh was invoked.

    This is the defect that mattered, and it is only observable across
    processes: run `detect_optional_tools()` under an interpreter that cannot
    import tree-sitter and it must still report the tool available, because a
    resolvable project-root interpreter can run the stages. The previous
    in-process import reported `available: false` here — while the pipeline,
    driven by a different Python, went on to run them.
    """
    stranger = _interpreter_without_treesitter()
    if stranger is None:
        pytest.skip("every available interpreter has tree-sitter installed")

    code = (
        f"import sys; sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
        "from arch_utils.provenance import detect_optional_tools\n"
        "print(detect_optional_tools()[0]['available'])\n"
    )
    result = subprocess.run(
        [str(stranger), "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True", (
        f"{stranger} cannot import tree_sitter itself, but the pipeline would "
        "use a project-root interpreter that can — provenance must say so"
    )


def test_resolution_is_disabled_by_the_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TREESITTER_ENABLED=false` must disable the tool everywhere at once."""
    monkeypatch.setenv("TREESITTER_ENABLED", "false")
    assert interpreters.resolve_treesitter_python() is None
    tools = {t["name"]: t for t in provenance.detect_optional_tools()}
    assert tools["tree-sitter"]["available"] is False


def test_unusable_override_does_not_mask_a_working_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An override that cannot import the modules falls through, it does not win.

    Resolution is by *capability*, not by path existence — the old probe checked
    `-x` on a path and then trusted it.
    """
    broken = tmp_path / "not-a-python"
    broken.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    broken.chmod(0o755)
    monkeypatch.setenv(interpreters.OVERRIDE_ENV, str(broken))

    if _treesitter_somewhere():
        assert interpreters.resolve_treesitter_python() is not None
    else:
        assert interpreters.resolve_treesitter_python() is None


def test_cli_reports_availability_through_its_exit_code() -> None:
    """The shell pipeline consumes this module as a subprocess."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "arch_utils" / "interpreters.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    if _treesitter_somewhere():
        assert result.returncode == 0
        assert Path(result.stdout.strip()).exists()
    else:
        assert result.returncode == 1
        assert result.stdout.strip() == ""
