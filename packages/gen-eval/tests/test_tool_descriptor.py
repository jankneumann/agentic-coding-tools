"""Tool-descriptor derivation from a CLI contract (task 1.3).

Spec scenarios:
  - gen-eval-framework.contract-as-descriptor-source-of-truth
      · descriptor derives from a contract
      · unreachable implementation does not shrink the declared surface
  - gen-eval-framework.operation-and-surface-coverage-model
      · flag-only tool surfaces are nameable
  - gen-eval-framework.service-and-tool-descriptor-archetypes
      · tool descriptor requires no lifecycle configuration

Design decisions: D1 (contract is the source, introspection is the verifier),
D2 (derivation produces checked-in artifacts, never runtime output),
D3 (the tool archetype's coverage unit is the flag/positional/named
subcommand — never the command), D5 (tool contracts are their own schema).

Two things in here are easy to get wrong, and both are load-bearing:

1. **The lifecycle claim is not "startup was omitted".** A tool descriptor
   that merely leaves ``startup`` unset passes any test that checks
   ``descriptor.startup is None``, whether or not the archetype means
   anything. What the spec pins is orchestrator *behaviour*: startup, health
   check, seeding and teardown are skipped. So those are driven through the
   real ``GenEvalOrchestrator``, with a negative control proving the same
   assertions fail for a descriptor that does declare a lifecycle.

2. **The expected coverage units are re-derived from the contract here**, by
   this test module, rather than imported from the implementation. Sharing the
   counting function between the code under test and its test turns the
   assertion into a tautology — a derivation that drops every flag would
   agree with itself. The duplication is the assertion.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from pydantic import ValidationError

from gen_eval.config import GenEvalConfig
from gen_eval.descriptor import (
    InterfaceDescriptor,
    ServiceSpec,
    StartupConfig,
    ToolDescriptor,
)
from gen_eval.evaluator import Evaluator
from gen_eval.orchestrator import GenEvalOrchestrator

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent

#: gen-eval's own CLI contract, read from the *promoted* location. The
#: change-local copy under ``openspec/changes/`` moves on archival; this one
#: does not. See ``openspec/contracts/README.md``.
CONTRACT_PATH = (
    REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"
)


# ---------------------------------------------------------------------------
# Helpers — an independent reading of the contract, owned by the tests
# ---------------------------------------------------------------------------


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    if not path.is_file():
        pytest.fail(
            f"CLI contract not found at {path.relative_to(REPO_ROOT)} — "
            "task 1.7 authors it and task 1.9 promotes it"
        )
    return yaml.safe_load(path.read_text())


def expected_units(contract: dict[str, Any]) -> list[str]:
    """Re-derive the coverage units straight from a contract document.

    Deliberately NOT the implementation's function. D3's second assertion
    ("the derived count equals the contract's") is only a gate while the two
    sides are computed independently.
    """

    def unit(command_name: str, leaf: str = "") -> str:
        return "cli:" + " ".join(part for part in (command_name, leaf) if part)

    units: list[str] = []
    for command in contract.get("commands") or []:
        name = command.get("name", "")
        if name:
            units.append(unit(name))
        for flag in command.get("flags") or []:
            units.append(unit(name, flag["name"]))
        for positional in command.get("positionals") or []:
            units.append(unit(name, f"<{positional['name']}>"))
    return units


def write_contract(tmp_path: Path, contract: dict[str, Any], name: str = "cli.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(contract, sort_keys=False))
    return path


FLAT_CONTRACT: dict[str, Any] = {
    "contract_version": "1",
    "tool": {"name": "flatty", "executable": "flatty"},
    "commands": [
        {
            "name": "",
            "flags": [
                {"name": "--input", "type": "path", "required": True},
                {"name": "--verbose", "type": "boolean"},
            ],
        }
    ],
}

SUBCOMMAND_CONTRACT: dict[str, Any] = {
    "contract_version": "1",
    "tool": {"name": "locker", "executable": "locker"},
    "commands": [
        {
            "name": "lock acquire",
            "flags": [{"name": "--ttl", "type": "integer"}],
            "positionals": [{"name": "path", "type": "path"}],
            "operation_ids": ["acquire_lock"],
        },
        {"name": "lock list", "flags": [{"name": "--json", "type": "boolean"}]},
    ],
}


# ---------------------------------------------------------------------------
# D1 — the contract populates the declared surface
# ---------------------------------------------------------------------------


class TestDerivesFromTheContract:
    def test_declared_surface_is_non_empty(self) -> None:
        descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.all_interfaces(), (
            "gen-eval's own contract derived an empty surface — this is the "
            "0-interfaces dogfood bug the change exists to close"
        )

    def test_units_match_an_independent_reading_of_the_contract(self) -> None:
        descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        assert sorted(descriptor.all_interfaces()) == sorted(expected_units(load_contract()))

    def test_specific_contracted_flags_are_present(self) -> None:
        """Guards the equality above against a both-sides-empty vacuous pass."""
        units = set(ToolDescriptor.from_contract(CONTRACT_PATH).all_interfaces())
        assert "cli:--descriptor" in units
        assert "cli:--print-contract-version" in units
        assert "cli:--fail-threshold" in units

    def test_total_interface_count_agrees_with_the_unit_list(self) -> None:
        descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.total_interface_count() == len(descriptor.all_interfaces())

    def test_exit_codes_are_carried_from_the_contract(self) -> None:
        """OpenAPI cannot express these; carrying them is why D5 exists."""
        descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        codes = {ec.code for ec in descriptor.exit_codes}
        assert {0, 1, 2, 64} <= codes

    def test_executable_comes_from_the_contract_not_from_path_lookup(self) -> None:
        descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.executable == load_contract()["tool"]["executable"]

    def test_named_subcommands_flags_and_positionals_are_all_units(self, tmp_path: Path) -> None:
        descriptor = ToolDescriptor.from_contract(write_contract(tmp_path, SUBCOMMAND_CONTRACT))
        assert sorted(descriptor.all_interfaces()) == sorted(
            [
                "cli:lock acquire",
                "cli:lock acquire --ttl",
                "cli:lock acquire <path>",
                "cli:lock list",
                "cli:lock list --json",
            ]
        )

    def test_a_flat_command_contributes_no_unit_of_its_own(self, tmp_path: Path) -> None:
        """D3 — commands are not coverage units; the empty name derives nothing.

        Without this, a contract of ``[{"name": ""}]`` counts 1 unit while
        declaring an empty surface, which is the vacuous pass D3 was written
        against.
        """
        descriptor = ToolDescriptor.from_contract(write_contract(tmp_path, FLAT_CONTRACT))
        units = descriptor.all_interfaces()
        assert "cli:" not in units
        assert sorted(units) == ["cli:--input", "cli:--verbose"]


# ---------------------------------------------------------------------------
# D1 — introspection never populates the surface
# ---------------------------------------------------------------------------


class TestImplementationIsNeverConsulted:
    def test_derivation_runs_no_subprocess_and_no_path_lookup(self) -> None:
        """The direction of D1, asserted rather than assumed.

        If derivation ever reached for ``--help`` output or a PATH probe, a
        broken or uninstalled tool would yield a smaller declared surface —
        and ``unevaluated_interfaces == []`` would report full coverage of
        nothing. That is UP-1's failure mode.
        """
        with (
            patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run called")),
            patch.object(
                subprocess, "Popen", side_effect=AssertionError("subprocess.Popen called")
            ),
            patch.object(shutil, "which", side_effect=AssertionError("shutil.which called")),
        ):
            descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.all_interfaces()

    def test_unreachable_implementation_does_not_shrink_the_surface(self, tmp_path: Path) -> None:
        """Same contract, an executable that cannot possibly exist."""
        reachable = ToolDescriptor.from_contract(CONTRACT_PATH)

        contract = load_contract()
        contract["tool"]["executable"] = "definitely-not-installed-anywhere"
        unreachable = ToolDescriptor.from_contract(write_contract(tmp_path, contract))

        assert unreachable.all_interfaces() == reachable.all_interfaces()


# ---------------------------------------------------------------------------
# Coverage model — flag-only surfaces are nameable
# ---------------------------------------------------------------------------


class TestFlagOnlySurfacesAreNameable:
    def test_every_unit_names_something(self) -> None:
        """A flat CLI has no subcommand to name; its flags must carry the names.

        The pre-change interface model could only name commands, so gen-eval's
        own descriptor declared zero interfaces and its coverage assertion
        passed for free (evaluation/README.md's "known limitation").
        """
        units = ToolDescriptor.from_contract(CONTRACT_PATH).all_interfaces()
        assert units
        for unit in units:
            assert unit.startswith("cli:")
            assert unit[len("cli:") :].strip(), f"unit {unit!r} names nothing"

    def test_units_are_unique(self) -> None:
        units = ToolDescriptor.from_contract(CONTRACT_PATH).all_interfaces()
        assert len(units) == len(set(units))


# ---------------------------------------------------------------------------
# Archetype — no lifecycle configuration
# ---------------------------------------------------------------------------


def _orchestrator(descriptor: InterfaceDescriptor, tmp_path: Path) -> GenEvalOrchestrator:
    descriptor_path = tmp_path / "descriptor.yaml"
    descriptor_path.write_text("project: t\nversion: '1'\nservices: []\n")
    return GenEvalOrchestrator(
        config=GenEvalConfig(descriptor_path=descriptor_path, max_iterations=1),
        descriptor=descriptor,
        generator=AsyncMock(),
        evaluator=AsyncMock(spec=Evaluator),
    )


@pytest.fixture
def tool_orchestrator(tmp_path: Path) -> GenEvalOrchestrator:
    descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
    return _orchestrator(descriptor, tmp_path)


class TestToolArchetypeHasNoLifecycle:
    def test_lifecycle_configuration_is_structurally_impossible(self) -> None:
        """Stronger than "omitted": the archetype cannot carry one at all.

        A tool descriptor that merely defaults ``startup`` to None can still
        be handed a lifecycle by a caller, and then the orchestrator would
        run it. Rejecting the field is what makes the skip unconditional.
        """
        with pytest.raises(ValidationError) as excinfo:
            ToolDescriptor(
                project="t",
                version="1",
                executable="t",
                services=[],
                startup=StartupConfig(
                    command="true", health_check="file:///dev/null", teardown="true"
                ),
            )
        # Naming the field matters: any missing-argument error would otherwise
        # satisfy this test without the archetype rejecting a lifecycle at all.
        assert "startup" in str(excinfo.value)

    def test_startup_runs_no_subprocess(self, tool_orchestrator: GenEvalOrchestrator) -> None:
        with patch("gen_eval.orchestrator.subprocess.run") as run:
            tool_orchestrator._run_startup()
        run.assert_not_called()

    def test_seeding_runs_no_subprocess(self, tool_orchestrator: GenEvalOrchestrator) -> None:
        with patch("gen_eval.orchestrator.subprocess.run") as run:
            tool_orchestrator._seed_data()
        run.assert_not_called()

    def test_teardown_runs_no_subprocess(self, tool_orchestrator: GenEvalOrchestrator) -> None:
        with patch("gen_eval.orchestrator.subprocess.run") as run:
            tool_orchestrator._run_teardown()
        run.assert_not_called()

    async def test_health_check_is_skipped_entirely(
        self, tool_orchestrator: GenEvalOrchestrator
    ) -> None:
        with patch("urllib.request.urlopen") as urlopen:
            await tool_orchestrator._health_check()
        urlopen.assert_not_called()

    async def test_negative_control_a_declared_lifecycle_still_runs(self, tmp_path: Path) -> None:
        """Proves the four assertions above can fail.

        Without this, an orchestrator whose lifecycle hooks were all no-ops —
        or were deleted — would satisfy every test in this class.
        """
        descriptor = InterfaceDescriptor(
            project="with-startup",
            version="1.0",
            services=[ServiceSpec(name="svc", type="cli", command="my-tool")],
            startup=StartupConfig(
                command="true",
                health_check="http://127.0.0.1:9/health",
                teardown="true",
            ),
        )
        orch = _orchestrator(descriptor, tmp_path)

        with patch("gen_eval.orchestrator.subprocess.run") as run:
            orch._run_startup()
        run.assert_called()

        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            await orch._health_check()
        urlopen.assert_called()


# ---------------------------------------------------------------------------
# D2 — the checked-in artifact is the descriptor; loading does not re-derive
# ---------------------------------------------------------------------------


class TestContractReferenceLoading:
    def test_from_contract_records_the_contract_it_came_from(self) -> None:
        descriptor = ToolDescriptor.from_contract(CONTRACT_PATH)
        assert descriptor.contract == CONTRACT_PATH

    def test_relative_contract_reference_resolves_against_the_descriptor(
        self, tmp_path: Path
    ) -> None:
        """Same convention as ``scenario_dirs``: relative to the file, not the CWD."""
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        write_contract(contracts, FLAT_CONTRACT)

        descriptor_path = tmp_path / "evaluation" / "descriptor.yaml"
        descriptor_path.parent.mkdir()
        descriptor_path.write_text(
            "project: flatty\n"
            "version: '1'\n"
            "executable: flatty\n"
            "contract: ../contracts/cli.yaml\n"
            "services: []\n"
            "commands:\n"
            "  - name: ''\n"
            "    flags:\n"
            "      - {name: '--input', type: path}\n"
        )

        descriptor = ToolDescriptor.from_yaml(descriptor_path)
        assert descriptor.contract == (contracts / "cli.yaml").resolve()

    def test_loading_uses_the_checked_in_surface_not_the_current_contract(
        self, tmp_path: Path
    ) -> None:
        """D2 — derivation is generation-time, never load-time.

        The rejected alternative (re-derive on load) makes the declared
        surface depend on generator success at run time, reintroducing D1's
        failure mode through the back door. Drift between the two is the
        guard's job (task 1.6), not the loader's.
        """
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        drifted = {
            **FLAT_CONTRACT,
            "commands": [
                {
                    "name": "",
                    "flags": [
                        {"name": "--input", "type": "path"},
                        {"name": "--added-later", "type": "boolean"},
                        {"name": "--and-another", "type": "boolean"},
                    ],
                }
            ],
        }
        write_contract(contracts, drifted)

        descriptor_path = tmp_path / "descriptor.yaml"
        descriptor_path.write_text(
            "project: flatty\n"
            "version: '1'\n"
            "executable: flatty\n"
            "contract: contracts/cli.yaml\n"
            "services: []\n"
            "commands:\n"
            "  - name: ''\n"
            "    flags:\n"
            "      - {name: '--input', type: path}\n"
        )

        descriptor = ToolDescriptor.from_yaml(descriptor_path)
        assert descriptor.all_interfaces() == ["cli:--input"]


# ---------------------------------------------------------------------------
# Reclamation — the name now denotes the document archetype
# ---------------------------------------------------------------------------


class TestArchetypeIsTheDocumentLevel:
    def test_it_is_not_the_superseded_mcp_tool_element(self) -> None:
        """``ToolDescriptor`` used to alias the single-MCP-tool element type.

        Reclaiming a name that resolved to something else for a release is
        exactly what the spec's reclamation requirement is about; within its
        defining module the name must now denote the archetype.
        """
        from gen_eval.descriptor import McpToolSpec

        assert ToolDescriptor is not McpToolSpec
        assert "input_schema" not in ToolDescriptor.model_fields

    def test_it_declares_a_tool_surface_rather_than_a_single_element(self) -> None:
        for field in ("commands", "executable", "contract", "exit_codes"):
            assert field in ToolDescriptor.model_fields
