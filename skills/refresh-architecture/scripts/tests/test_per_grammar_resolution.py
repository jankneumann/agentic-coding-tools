"""Optional-tool resolution is per-analyzer, not one boolean for the pipeline.

`REQUIRED_MODULES = ("tree_sitter", "tree_sitter_sql")` made the SQL grammar a
precondition for *every* tree-sitter stage: an interpreter carrying the Python
and TypeScript grammars but not the SQL one resolved to `None`, which disabled
`treesitter_enrichment`, `comment_linker` and `pattern_reporter` as well — the
three stages that give the graph its comment links and pattern annotations.

D6 narrows that to per-stage resolution while keeping the single resolver that
issue #378 introduced. These tests pin both halves: a stage runs when *its own*
grammars are importable, and the record provenance writes cannot disagree with
the verdicts the shell pipeline reads, at grammar granularity.

The interpreters here are real: a wrapper puts a module on `PYTHONPATH` that
raises `ImportError` on import, shadowing the installed grammar. Probing is
therefore a genuine subprocess import, not a stubbed answer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from arch_utils import interpreters  # noqa: E402
from arch_utils import provenance  # noqa: E402

INTERPRETERS_PY = SCRIPTS_DIR / "arch_utils" / "interpreters.py"

ENRICHMENT_STAGES = ("treesitter_enrichment", "comment_linker", "pattern_reporter")


def _has(module: str) -> bool:
    probe = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, check=False
    )
    return probe.returncode == 0


requires_all_grammars = pytest.mark.skipif(
    not all(_has(m) for m in ("tree_sitter", "tree_sitter_sql", "tree_sitter_python")),
    reason="the grammar packages are not installed in this interpreter",
)


def _interpreter_without(tmp_path: Path, *blocked: str) -> Path:
    """Return a real interpreter that cannot import *blocked*.

    Shadowing with a module that raises `ImportError` reproduces a partial
    grammar install exactly as the probe would encounter it, without needing a
    second virtualenv.
    """
    block_dir = tmp_path / ("blocked_" + "_".join(blocked))
    block_dir.mkdir(parents=True, exist_ok=True)
    for module in blocked:
        (block_dir / f"{module}.py").write_text(
            f'raise ImportError("{module} is not installed in this interpreter")\n',
            encoding="utf-8",
        )
    wrapper = tmp_path / ("python_without_" + "_".join(blocked))
    wrapper.write_text(
        "#!/bin/sh\n"
        f'PYTHONPATH="{block_dir}:${{PYTHONPATH:-}}" exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


@pytest.fixture
def only_candidate(monkeypatch: pytest.MonkeyPatch):
    """Pin the candidate list so a scenario describes one interpreter."""

    def _pin(python: Path) -> None:
        monkeypatch.setattr(interpreters, "candidate_pythons", lambda *a, **k: [python])

    return _pin


def test_requirements_are_declared_per_stage() -> None:
    """The requirement table replaces the single `REQUIRED_MODULES` tuple."""
    table = interpreters.STAGE_REQUIREMENTS

    assert table["treesitter_sql"] == ("tree_sitter", "tree_sitter_sql")
    for stage in ENRICHMENT_STAGES:
        assert "tree_sitter_sql" not in table[stage], (
            f"{stage} does not parse SQL and must not require its grammar"
        )
        assert "tree_sitter" in table[stage]
        assert "tree_sitter_python" in table[stage]

    for stage, required in table.items():
        assert required, f"{stage} declares no grammars"
        for module in required:
            assert module in interpreters.GRAMMAR_MODULES, (
                f"{stage} requires {module}, which is not a reported grammar"
            )


@requires_all_grammars
def test_absent_sql_grammar_disables_only_the_sql_stage(
    tmp_path: Path, only_candidate
) -> None:
    """The measured defect: one grammar disabling three unrelated stages."""
    only_candidate(_interpreter_without(tmp_path, "tree_sitter_sql"))

    resolution = interpreters.resolve_grammars()

    assert resolution.python is not None
    assert resolution.available["tree_sitter"] is True
    assert resolution.available["tree_sitter_python"] is True
    assert resolution.available["tree_sitter_sql"] is False
    assert resolution.stage_available("treesitter_sql") is False
    for stage in ENRICHMENT_STAGES:
        assert resolution.stage_available(stage) is True, (
            f"{stage} needs no SQL grammar and must remain available"
        )


@requires_all_grammars
def test_absent_python_grammar_does_not_disable_the_sql_stage(
    tmp_path: Path, only_candidate
) -> None:
    """Independence runs in both directions, not just away from SQL."""
    only_candidate(_interpreter_without(tmp_path, "tree_sitter_python"))

    resolution = interpreters.resolve_grammars()

    assert resolution.stage_available("treesitter_sql") is True
    for stage in ENRICHMENT_STAGES:
        assert resolution.stage_available(stage) is False


@requires_all_grammars
def test_absent_core_grammar_disables_every_stage(
    tmp_path: Path, only_candidate
) -> None:
    """No `tree_sitter` at all means no interpreter and no tree-sitter stage."""
    only_candidate(_interpreter_without(tmp_path, "tree_sitter"))

    resolution = interpreters.resolve_grammars()

    assert resolution.python is None
    assert not any(resolution.stages().values())
    assert all(available is False for available in resolution.available.values())


def test_kill_switch_disables_every_grammar(monkeypatch: pytest.MonkeyPatch) -> None:
    """`TREESITTER_ENABLED=false` still switches the whole tool off at once."""
    monkeypatch.setenv("TREESITTER_ENABLED", "false")

    resolution = interpreters.resolve_grammars()

    assert resolution.python is None
    assert all(available is False for available in resolution.available.values())
    assert not any(resolution.stages().values())


def test_optional_tools_record_one_entry_per_grammar() -> None:
    """Provenance records grammar identity, not a single tree-sitter boolean."""
    tools = provenance.detect_optional_tools()
    names = [tool["name"] for tool in tools]

    assert names == sorted(names), "entries must be ordered for byte-stable provenance"
    assert names == [interpreters.tool_name(m) for m in sorted(interpreters.GRAMMAR_MODULES)]
    for tool in tools:
        assert set(tool) == {"name", "available", "version"}
        assert isinstance(tool["available"], bool)
        if not tool["available"]:
            assert tool["version"] is None


def test_optional_tools_stay_valid_against_the_published_schema() -> None:
    """The per-grammar shape must need no schema change (it is out of scope)."""
    schema_path = provenance._published_schema_path()
    if schema_path is None:  # pragma: no cover - depends on install layout
        pytest.skip("published provenance schema is not available in this layout")
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema["properties"]["optional_tools"])
    errors = list(validator.iter_errors(provenance.detect_optional_tools()))
    assert errors == [], [e.message for e in errors]


@requires_all_grammars
def test_a_stage_that_can_run_has_every_required_grammar_recorded_available(
    tmp_path: Path, only_candidate
) -> None:
    """The ri-10 D14 invariant, held at grammar granularity.

    The pipeline reads the stage verdicts and provenance writes the grammar
    entries. If a stage can run while a grammar it requires is recorded
    unavailable, the record vouches for artifacts the run could not have
    produced — the exact failure D14 closed for the single boolean.
    """
    only_candidate(_interpreter_without(tmp_path, "tree_sitter_sql"))

    resolution = interpreters.resolve_grammars()
    recorded = {tool["name"]: tool for tool in provenance.detect_optional_tools()}

    ran_something = False
    for stage, required in interpreters.STAGE_REQUIREMENTS.items():
        if not resolution.stage_available(stage):
            continue
        ran_something = True
        for module in required:
            entry = recorded[interpreters.tool_name(module)]
            assert entry["available"] is True, (
                f"{stage} may run, but provenance records {entry['name']} as unavailable"
            )
    assert ran_something, "the scenario must leave at least one stage runnable"

    for stage, required in interpreters.STAGE_REQUIREMENTS.items():
        if any(not recorded[interpreters.tool_name(m)]["available"] for m in required):
            assert resolution.stage_available(stage) is False, (
                f"{stage} is runnable while provenance records a required grammar absent"
            )


def test_the_shell_and_provenance_read_one_resolution() -> None:
    """The shell reads a JSON map from the same resolver provenance calls.

    The shell consumes this module as a subprocess, so agreement has to hold
    across processes — that is where the two answers diverged before #378.
    """
    completed = subprocess.run(
        [sys.executable, str(INTERPRETERS_PY), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode in (0, 1), completed.stderr
    emitted = json.loads(completed.stdout)

    recorded = {tool["name"]: tool for tool in provenance.detect_optional_tools()}
    for module, available in emitted["grammars"].items():
        assert recorded[interpreters.tool_name(module)]["available"] is available

    resolution = interpreters.resolve_grammars()
    assert emitted["stages"] == resolution.stages()


def test_the_shell_map_is_evaluable_and_matches_the_json_map(tmp_path: Path) -> None:
    """`--shell` is the form the pipeline evals; it must say the same thing."""
    completed = subprocess.run(
        [sys.executable, str(INTERPRETERS_PY), "--shell"],
        capture_output=True,
        text=True,
        check=False,
    )
    emitted = json.loads(
        subprocess.run(
            [sys.executable, str(INTERPRETERS_PY), "--json"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    )

    script = tmp_path / "eval_map.sh"
    script.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        f"eval \"$(cat {tmp_path / 'map.sh'})\"\n"
        'echo "python=${TREESITTER_PYTHON}"\n'
        + "".join(
            f'echo "{stage}=${{TREESITTER_STAGE_{stage}}}"\n'
            for stage in sorted(interpreters.STAGE_REQUIREMENTS)
        ),
        encoding="utf-8",
    )
    (tmp_path / "map.sh").write_text(completed.stdout, encoding="utf-8")

    evaluated = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, check=False
    )
    assert evaluated.returncode == 0, evaluated.stderr
    values = dict(line.split("=", 1) for line in evaluated.stdout.strip().splitlines())

    assert values["python"] == (emitted["python"] or "")
    for stage, available in emitted["stages"].items():
        assert values[stage] == ("true" if available else "false")
