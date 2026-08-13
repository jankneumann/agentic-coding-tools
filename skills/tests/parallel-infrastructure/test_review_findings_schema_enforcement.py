"""ri-14: single canonical review-findings schema, enforced end-to-end.

Guards that:

* the canonical ``openspec/schemas/review-findings.schema.json`` and its
  installed ``install_assets`` copy do not drift,
* ``agents.yaml`` carries the schema sentinel rather than a hand-copied,
  drift-prone ``--json-schema`` blob, and the dispatch adapter injects the
  schema derived from the canonical file,
* the dispatcher rejects a drifted finding (missing field / wrong enum)
  instead of surfacing it as a successful review,
* the consensus synthesizer fails loudly on a drifted per-vendor findings
  file rather than merging it silently,
* conforming findings still flow through both layers unchanged.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py adds skills/parallel-infrastructure/scripts to sys.path.
import review_findings_schema as rfs  # type: ignore[import-untyped]
from review_dispatcher import (  # type: ignore[import-untyped]
    CliConfig,
    CliVendorAdapter,
    ModeConfig,
)
from consensus_synthesizer import ConsensusInputError  # type: ignore[import-untyped]
import consensus_synthesizer  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"
INSTALL_COPY = (
    REPO_ROOT
    / "skills"
    / "parallel-infrastructure"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "review-findings.schema.json"
)
AGENTS_YAML = REPO_ROOT / "agent-coordinator" / "agents.yaml"


def _finding(**overrides: object) -> dict:
    base = {
        "id": 1,
        "type": "security",
        "criticality": "high",
        "description": "leaks a token",
        "disposition": "fix",
        "axis": "security",
        "severity": "critical",
    }
    base.update(overrides)
    return base


def _document(findings: list[dict]) -> dict:
    return {
        "review_type": "plan",
        "target": "demo-feature",
        "reviewer_vendor": "test",
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Canonical file is the single source of truth
# ---------------------------------------------------------------------------


def test_canonical_and_install_copy_do_not_drift() -> None:
    assert CANONICAL.is_file()
    assert INSTALL_COPY.is_file()
    assert CANONICAL.read_text() == INSTALL_COPY.read_text(), (
        "install_assets copy has drifted from the canonical schema"
    )


def test_module_resolves_the_canonical_file() -> None:
    resolved = rfs.find_schema_path()
    assert resolved.read_text() == CANONICAL.read_text()


# ---------------------------------------------------------------------------
# agents.yaml no longer carries a divergent inlined schema
# ---------------------------------------------------------------------------


def test_agents_yaml_uses_sentinel_not_inlined_schema() -> None:
    import yaml

    doc = yaml.safe_load(AGENTS_YAML.read_text())
    review_args = doc["agents"]["grok-local"]["cli"]["dispatch_modes"]["review"]["args"]
    assert "--json-schema" in review_args
    assert rfs.GROK_SCHEMA_SENTINEL in review_args
    # The schema is injected by the adapter, never carried inline: no arg
    # should be a JSON object literal describing findings.
    for arg in review_args:
        assert '"findings"' not in arg, "agents.yaml still inlines a findings schema"


def test_adapter_injects_canonical_schema_for_grok_sentinel() -> None:
    adapter = CliVendorAdapter(
        agent_id="grok-local",
        vendor="grok",
        cli_config=CliConfig(
            command="grok",
            dispatch_modes={
                "review": ModeConfig(args=[
                    "--prompt-file", "/dev/stdin",
                    "--output-format", "json",
                    "--always-approve",
                    "--json-schema", rfs.GROK_SCHEMA_SENTINEL,
                ]),
            },
            model_flag="-m",
            prompt_via_stdin=True,
        ),
    )
    cmd = adapter.build_command("review", "prompt")
    # Sentinel gone, replaced by the derived schema JSON string.
    assert rfs.GROK_SCHEMA_SENTINEL not in cmd
    idx = cmd.index("--json-schema")
    injected = json.loads(cmd[idx + 1])
    assert injected == rfs.derive_output_schema()
    # And the derived schema really requires the axis/severity fields, i.e.
    # it came from the canonical definition rather than a stale copy.
    item = injected["properties"]["findings"]["items"]
    assert {"axis", "severity"} <= set(item["required"])


# ---------------------------------------------------------------------------
# Dispatcher rejects drift
# ---------------------------------------------------------------------------


def _grok_adapter() -> CliVendorAdapter:
    return CliVendorAdapter(
        agent_id="grok-local",
        vendor="grok",
        cli_config=CliConfig(
            command="grok",
            dispatch_modes={"review": ModeConfig(args=["--output-format", "json"])},
            model_flag="-m",
        ),
    )


@patch("review_dispatcher.subprocess.run")
def test_dispatch_conforming_findings_succeed(mock_run: MagicMock, tmp_path: Path) -> None:
    import subprocess as _sp

    mock_run.return_value = _sp.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"findings": [_finding()]}), stderr="",
    )
    result = _grok_adapter().dispatch("review", "prompt", cwd=tmp_path)
    assert result.success is True
    assert result.findings is not None
    assert len(result.findings["findings"]) == 1


@patch("review_dispatcher.subprocess.run")
def test_dispatch_missing_required_field_fails(mock_run: MagicMock, tmp_path: Path) -> None:
    import subprocess as _sp

    drifted = _finding()
    del drifted["severity"]  # required field missing
    mock_run.return_value = _sp.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"findings": [drifted]}), stderr="",
    )
    result = _grok_adapter().dispatch("review", "prompt", cwd=tmp_path)
    assert result.success is False
    assert result.findings is None
    assert "schema validation" in (result.error or "")


@patch("review_dispatcher.subprocess.run")
def test_dispatch_wrong_enum_fails(mock_run: MagicMock, tmp_path: Path) -> None:
    import subprocess as _sp

    drifted = _finding(disposition="ignore")  # not in the disposition enum
    mock_run.return_value = _sp.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps({"findings": [drifted]}), stderr="",
    )
    result = _grok_adapter().dispatch("review", "prompt", cwd=tmp_path)
    assert result.success is False
    assert "schema validation" in (result.error or "")


# ---------------------------------------------------------------------------
# Consensus synthesizer fails loudly on drift
# ---------------------------------------------------------------------------


def _run_consensus(tmp_path: Path, argv_extra: list[str]) -> None:
    output = tmp_path / "consensus.json"
    argv = [
        "consensus_synthesizer.py",
        "--review-type", "plan",
        "--target", "demo-feature",
        "--output", str(output),
        "--quorum", "1",
        *argv_extra,
    ]
    with patch.object(sys, "argv", argv):
        consensus_synthesizer.main()


def test_consensus_accepts_conforming_findings(tmp_path: Path) -> None:
    f1 = tmp_path / "findings-claude.json"
    f2 = tmp_path / "findings-codex.json"
    f1.write_text(json.dumps(_document([_finding(id=1, file_path="a.py")])))
    f2.write_text(json.dumps(_document([_finding(id=1, file_path="b.py")])))
    _run_consensus(tmp_path, ["--findings", str(f1), str(f2)])
    assert (tmp_path / "consensus.json").exists()


def test_consensus_rejects_drifted_finding_loudly(tmp_path: Path) -> None:
    pytest.importorskip("jsonschema")
    drifted = _finding(id=1, file_path="a.py")
    del drifted["axis"]  # required field missing
    bad = tmp_path / "findings-claude.json"
    bad.write_text(json.dumps(_document([drifted])))
    with pytest.raises(ConsensusInputError) as exc:
        _run_consensus(tmp_path, ["--findings", str(bad)])
    assert "schema violation" in str(exc.value)
    # It fails before writing a consensus report — nothing silently merged.
    assert not (tmp_path / "consensus.json").exists()


def test_consensus_rejects_wrong_enum_via_cli(tmp_path: Path) -> None:
    """End-to-end via the real CLI: a bad enum yields a non-zero exit."""
    pytest.importorskip("jsonschema")
    drifted = _finding(id=1, criticality="blocking", file_path="a.py")  # bad enum
    bad = tmp_path / "findings-claude.json"
    bad.write_text(json.dumps(_document([drifted])))
    script = (
        REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
        / "consensus_synthesizer.py"
    )
    result = subprocess.run(
        [
            sys.executable, str(script),
            "--review-type", "plan",
            "--target", "demo-feature",
            "--findings", str(bad),
            "--output", str(tmp_path / "out.json"),
            "--quorum", "1",
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "schema violation" in (result.stderr + result.stdout)
