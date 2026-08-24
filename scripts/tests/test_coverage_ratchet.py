"""Tests for scripts/coverage_ratchet.py.

The script is at the repo's top-level scripts/ — outside skills/ pyproject
testpaths — so run these explicitly:

    pytest scripts/tests/test_coverage_ratchet.py -v

No coverage run is required: the ratchet takes measured percentages as
arguments (``--measured NAME=PCT``) or reads a Cobertura ``coverage.xml``
(``--coverage-xml NAME=PATH``), so every case here is pure I/O over tmp_path.

The invalid-baseline cases are cross-checked against the authoritative
contract schema (``openspec/changes/introduce-fitness-function-gates/
contracts/coverage-baseline.schema.json``): each fixture must be rejected by
jsonschema *and* by the script, so the script's hand-rolled validation cannot
drift away from the contract without a test failing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import coverage_ratchet as cr

SCHEMA_PATH = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "introduce-fitness-function-gates"
    / "contracts"
    / "coverage-baseline.schema.json"
)


def load_schema() -> dict[str, Any]:
    if not SCHEMA_PATH.exists():  # pragma: no cover - archived change
        pytest.skip(f"contract schema not present at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text())


def valid_baseline(**overrides: Any) -> dict[str, Any]:
    baseline: dict[str, Any] = {
        "schema_version": 1,
        "tolerance_pp": 0.5,
        "suites": {
            "agent-coordinator": {
                "line_coverage_pct": 70.0,
                "command": 'uv run pytest -m "not e2e and not integration" --cov=src',
            },
            "skills": {
                "line_coverage_pct": 60.0,
                "command": "uv run pytest --cov=.",
            },
        },
    }
    baseline.update(overrides)
    return baseline


def write_baseline(tmp_path: Path, baseline: Any) -> Path:
    path = tmp_path / "coverage-baseline.json"
    path.write_text(json.dumps(baseline))
    return path


def run(argv: list[str]) -> int:
    return cr.main(argv)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def test_reports_measured_coverage_per_suite(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(
        [
            "--baseline",
            str(path),
            "--measured",
            "agent-coordinator=70.0",
            "--measured",
            "skills=60.0",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "agent-coordinator" in out
    assert "skills" in out
    assert "70.00" in out
    assert "60.00" in out


def test_reads_measured_coverage_from_coverage_xml(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())
    xml = tmp_path / "coverage.xml"
    xml.write_text('<?xml version="1.0" ?><coverage line-rate="0.7123"></coverage>')

    code = run(
        [
            "--baseline",
            str(path),
            "--coverage-xml",
            f"agent-coordinator={xml}",
            "--measured",
            "skills=60.0",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "71.23" in out


# --------------------------------------------------------------------------
# The ratchet
# --------------------------------------------------------------------------


def test_fails_when_decrease_exceeds_tolerance(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(
        [
            "--baseline",
            str(path),
            "--measured",
            "agent-coordinator=66.4",
            "--measured",
            "skills=60.0",
        ]
    )
    captured = capsys.readouterr()
    message = captured.out + captured.err

    assert code != 0, "a beyond-tolerance decrease must exit non-zero"
    assert "agent-coordinator" in message, "the failure must name the suite"
    assert "70.00" in message, "the failure must name the baseline"
    assert "66.40" in message, "the failure must name the measured value"


def test_passes_when_decrease_is_within_tolerance(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(
        [
            "--baseline",
            str(path),
            "--measured",
            "agent-coordinator=69.6",
            "--measured",
            "skills=59.5",
        ]
    )

    assert code == 0
    assert "69.60" in capsys.readouterr().out


def test_signals_baseline_update_when_coverage_improves(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(
        [
            "--baseline",
            str(path),
            "--measured",
            "agent-coordinator=74.5",
            "--measured",
            "skills=60.0",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "coverage_ratchet.py" in out, "an improvement must print the update command"
    assert "--update" in out
    # The baseline is not touched without --update: the ratchet reports, the
    # human (or a follow-up commit) moves it.
    assert json.loads(path.read_text())["suites"]["agent-coordinator"][
        "line_coverage_pct"
    ] == pytest.approx(70.0)


def test_update_writes_improved_values_only(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(
        [
            "--baseline",
            str(path),
            "--measured",
            "agent-coordinator=74.5",
            "--measured",
            "skills=59.8",
            "--update",
        ]
    )
    capsys.readouterr()
    written = json.loads(path.read_text())

    assert code == 0
    assert written["suites"]["agent-coordinator"]["line_coverage_pct"] == pytest.approx(74.5)
    # Ratchet only moves upward: a within-tolerance dip does not lower the bar.
    assert written["suites"]["skills"]["line_coverage_pct"] == pytest.approx(60.0)
    assert written["schema_version"] == 1
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(written, load_schema())


def test_unknown_suite_is_an_error(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(["--baseline", str(path), "--measured", "nope=99.0"])
    message = "".join(capsys.readouterr())

    assert code == 2
    assert "nope" in message


def test_missing_measurement_for_a_baselined_suite_is_an_error(tmp_path, capsys):
    path = write_baseline(tmp_path, valid_baseline())

    code = run(["--baseline", str(path), "--measured", "skills=60.0"])
    message = "".join(capsys.readouterr())

    assert code == 2
    assert "agent-coordinator" in message


# --------------------------------------------------------------------------
# Contract validation
# --------------------------------------------------------------------------


INVALID_BASELINES: dict[str, Any] = {
    "wrong_schema_version": valid_baseline(schema_version=2),
    "missing_schema_version": {
        "tolerance_pp": 0.5,
        "suites": {"skills": {"line_coverage_pct": 1.0, "command": "x"}},
    },
    "missing_tolerance": {
        "schema_version": 1,
        "suites": {"skills": {"line_coverage_pct": 1.0, "command": "x"}},
    },
    "tolerance_out_of_range": valid_baseline(tolerance_pp=25),
    "negative_tolerance": valid_baseline(tolerance_pp=-1),
    "no_suites": valid_baseline(suites={}),
    "suite_missing_command": valid_baseline(suites={"skills": {"line_coverage_pct": 10.0}}),
    "suite_missing_pct": valid_baseline(suites={"skills": {"command": "x"}}),
    "suite_pct_out_of_range": valid_baseline(
        suites={"skills": {"line_coverage_pct": 101.0, "command": "x"}}
    ),
    "suite_empty_command": valid_baseline(
        suites={"skills": {"line_coverage_pct": 10.0, "command": ""}}
    ),
    "suite_extra_property": valid_baseline(
        suites={"skills": {"line_coverage_pct": 10.0, "command": "x", "nope": 1}}
    ),
    "top_level_extra_property": valid_baseline(nope=1),
    "not_an_object": [1, 2, 3],
}


@pytest.mark.parametrize("name", sorted(INVALID_BASELINES))
def test_rejects_baseline_that_violates_the_contract(name, tmp_path, capsys):
    jsonschema = pytest.importorskip("jsonschema")
    payload = INVALID_BASELINES[name]

    # The contract is the authority: assert the fixture really is invalid.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, load_schema())

    path = write_baseline(tmp_path, payload)
    code = run(["--baseline", str(path), "--measured", "skills=10.0"])
    message = "".join(capsys.readouterr())

    assert code == 2, f"{name}: schema-invalid baseline must exit 2"
    assert "coverage-baseline.json" in message or "baseline" in message.lower()


def test_rejects_unparseable_baseline(tmp_path, capsys):
    path = tmp_path / "coverage-baseline.json"
    path.write_text("{not json")

    code = run(["--baseline", str(path), "--measured", "skills=10.0"])
    capsys.readouterr()

    assert code == 2


def test_missing_baseline_file_is_an_error(tmp_path, capsys):
    code = run(["--baseline", str(tmp_path / "absent.json"), "--measured", "skills=10.0"])
    capsys.readouterr()

    assert code == 2


def test_committed_baseline_matches_the_contract():
    jsonschema = pytest.importorskip("jsonschema")
    committed = REPO_ROOT / "coverage-baseline.json"

    assert committed.exists(), "coverage-baseline.json must be committed at the repo root"
    payload = json.loads(committed.read_text())
    jsonschema.validate(payload, load_schema())
    assert payload["tolerance_pp"] == pytest.approx(0.5), "design D5 fixes tolerance at 0.5pp"
    assert set(payload["suites"]) == {"agent-coordinator", "skills"}
