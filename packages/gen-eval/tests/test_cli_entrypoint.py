"""Tests for the ``gen-eval`` console-script entry point (UP-1).

Background: ``[project.scripts]`` pointed at ``gen_eval.__main__:main`` while
``main`` was ``async def main(args)``. The generated launcher calls the target
with *no* arguments, so every invocation of the installed executable died with
``TypeError: main() missing 1 required positional argument: 'args'``. The
existing suite never caught it because every test drove the async body
directly — the module path was healthy the whole time.

Three layers of guard, cheapest first:

1. :class:`TestEntryPointMetadata` resolves the ``[project.scripts]`` target
   and asserts it is a zero-argument synchronous callable. This is the unit
   test that would have caught the original defect.
2. :class:`TestCliContract` drives the real executable and asserts the
   documented exit codes.
3. :class:`TestInstalledArtifact` builds a wheel, installs it into a throwaway
   venv, and runs the console script from there — the only layer that
   exercises packaging metadata end to end.
"""

from __future__ import annotations

import importlib
import inspect
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Exit codes the CLI contract promises.
EX_OK = 0
EX_ARGPARSE = 2  # argparse default for a missing required argument
EX_USAGE = 64  # BSD sysexits.h, used for --openspec-change validation failure


def _console_script_target() -> tuple[str, str]:
    """Return ``(module, attr)`` for the ``gen-eval`` console script."""
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    assert "gen-eval" in scripts, f"pyproject must declare a gen-eval script; got {scripts}"
    module, _, attr = scripts["gen-eval"].partition(":")
    return module, attr


class TestEntryPointMetadata:
    """The declared console-script target must match what a launcher can call."""

    def test_target_resolves(self) -> None:
        module_name, attr = _console_script_target()
        module = importlib.import_module(module_name)
        assert hasattr(module, attr), (
            f"pyproject declares {module_name}:{attr} but {module_name} has no {attr!r}"
        )

    def test_target_is_not_a_coroutine_function(self) -> None:
        """The original defect: a launcher cannot await the result of main()."""
        module_name, attr = _console_script_target()
        target = getattr(importlib.import_module(module_name), attr)
        assert not inspect.iscoroutinefunction(target), (
            f"{module_name}:{attr} is async; the generated console-script launcher "
            "calls it synchronously and would leak an un-awaited coroutine"
        )

    def test_target_is_callable_with_no_arguments(self) -> None:
        """The generated launcher calls the target as ``main()``, full stop."""
        module_name, attr = _console_script_target()
        target = getattr(importlib.import_module(module_name), attr)
        sig = inspect.signature(target)
        required = [
            p
            for p in sig.parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        assert not required, (
            f"{module_name}:{attr}{sig} requires {[p.name for p in required]}; "
            "the console-script launcher passes no arguments"
        )

    def test_async_body_remains_public_as_run(self) -> None:
        """``run`` stays importable for callers driving the pipeline in-loop."""
        from gen_eval.__main__ import run

        assert inspect.iscoroutinefunction(run)
        assert "args" in inspect.signature(run).parameters


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI through the module path (always available in-tree)."""
    return subprocess.run(
        [sys.executable, "-m", "gen_eval", *args],
        cwd=str(PACKAGE_ROOT),
        capture_output=True,
        text=True,
    )


class TestCliContract:
    """Documented exit codes, driven through a real process."""

    def test_help_exits_zero_and_prints_usage(self) -> None:
        result = _run_cli("--help")
        assert result.returncode == EX_OK, result.stderr
        assert "usage:" in result.stdout.lower()
        assert "--descriptor" in result.stdout

    def test_missing_descriptor_exits_two(self) -> None:
        """Regression guard on parse_args() still being reached at all."""
        result = _run_cli()
        assert result.returncode == EX_ARGPARSE, result.stderr
        assert "--descriptor" in result.stderr

    def test_invalid_openspec_change_exits_ex_usage(self) -> None:
        """The custom parser.error override must survive the refactor."""
        result = _run_cli("--descriptor", "x.yaml", "--openspec-change", "../etc/passwd")
        assert result.returncode == EX_USAGE, (
            f"expected {EX_USAGE}, got {result.returncode}: {result.stderr}"
        )

    def test_valid_openspec_change_does_not_exit_ex_usage(self) -> None:
        result = _run_cli("--descriptor", "does-not-exist.yaml", "--openspec-change", "some-id")
        assert result.returncode != EX_USAGE

    def test_print_contract_version_exits_zero_without_descriptor(self) -> None:
        """The version probe must not require the otherwise-mandatory flag."""
        from gen_eval.contracts import CONTRACT_VERSION

        result = _run_cli("--print-contract-version")
        assert result.returncode == EX_OK, result.stderr
        assert result.stdout.strip() == CONTRACT_VERSION
        assert len(result.stdout.strip().splitlines()) == 1


@pytest.mark.slow
class TestInstalledArtifact:
    """Build → install → execute. The layer that exercises packaging metadata.

    Everything above imports from the source tree, where a broken
    ``[project.scripts]`` entry is invisible. Only running the executable that
    a wheel install generates proves the published interface works.
    """

    @pytest.fixture(scope="class")
    def installed_console_script(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        uv = shutil.which("uv")
        if uv is None:
            pytest.skip("uv not on PATH — cannot build/install the wheel")

        tmp = tmp_path_factory.mktemp("installed-artifact")
        dist = tmp / "dist"

        build = subprocess.run(
            [uv, "build", "--wheel", "--out-dir", str(dist)],
            cwd=str(PACKAGE_ROOT),
            capture_output=True,
            text=True,
        )
        if build.returncode != 0:
            pytest.skip(f"uv build --wheel failed: {build.stderr[:500]}")

        wheels = list(dist.glob("*.whl"))
        if not wheels:
            pytest.skip("uv build produced no wheel")

        venv = tmp / "venv"
        subprocess.run([uv, "venv", str(venv)], capture_output=True, text=True, check=True)
        install = subprocess.run(
            [uv, "pip", "install", "--python", str(venv / "bin" / "python"), str(wheels[0])],
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            pytest.skip(f"wheel install failed: {install.stderr[:500]}")

        script = venv / "bin" / "gen-eval"
        assert script.exists(), (
            f"wheel install produced no gen-eval executable in {venv / 'bin'}: "
            f"{sorted(p.name for p in (venv / 'bin').iterdir())}"
        )
        return script

    def test_installed_console_script_runs(self, installed_console_script: Path) -> None:
        """``gen-eval --help`` from a real install exits 0 and prints usage.

        This is the assertion that fails on the pre-fix code with
        ``TypeError: main() missing 1 required positional argument``.
        """
        result = subprocess.run(
            [str(installed_console_script), "--help"], capture_output=True, text=True
        )
        assert result.returncode == EX_OK, (
            f"installed console script failed (exit {result.returncode}): {result.stderr}"
        )
        assert "usage:" in result.stdout.lower()
        assert "Traceback" not in result.stderr

    def test_installed_console_script_reports_contract_version(
        self, installed_console_script: Path
    ) -> None:
        from gen_eval.contracts import CONTRACT_VERSION

        result = subprocess.run(
            [str(installed_console_script), "--print-contract-version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == EX_OK, result.stderr
        assert result.stdout.strip() == CONTRACT_VERSION

    def test_wheel_ships_contract_schemas(self, installed_console_script: Path) -> None:
        """The published schemas must be readable from the installed wheel."""
        python = installed_console_script.parent / "python"
        result = subprocess.run(
            [
                str(python),
                "-c",
                "from gen_eval.contracts import SCHEMA_FILENAMES, load_schema;"
                "print(sorted(load_schema(n)['$id'].rsplit('/', 1)[-1] for n in SCHEMA_FILENAMES))",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == EX_OK, (
            f"contract schemas not loadable from the installed wheel: {result.stderr}"
        )
        assert "eval-report.schema.json" in result.stdout
