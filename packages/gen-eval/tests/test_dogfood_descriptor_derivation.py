"""gen-eval's own descriptor is derived, not typed (task 5.3).

Spec scenarios:
  - gen-eval-framework.dogfood
      · gen-eval evaluates its own CLI surface
  - gen-eval-framework.operation-and-surface-coverage-model
      · flag-only tool surfaces are nameable

Design decisions: D8 (dogfood is the integration test), D3 (the tool's
coverage unit is the flag), D1 (the contract is the source).

Until this task, ``evaluation/descriptor.yaml`` was hand-authored and declared
``commands: []`` — an empty declared surface. The dogfood run therefore
reported ``0 interfaces`` and its coverage assertion passed for free, which is
the failure D3 exists to name: coverage of nothing is not coverage.

It also left the drift guard guarding nothing. ``generate_tool_descriptor.py
--check`` compares the contract against a *derived* artifact; with no derived
artifact on disk it could only fail, and did.

The bare-invocation test below is not incidental. ``--check`` asserts byte
identity against what it would generate *from its own argv*, so a generate
step and a check step that disagree about any flag report drift on an
artifact that is perfectly up to date — a guard that cries wolf gets disabled.
"""

from __future__ import annotations

import subprocess
import sys
import warnings
from pathlib import Path

import yaml

from gen_eval.descriptor import ToolDescriptor, load_descriptor

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
DESCRIPTOR = PACKAGE_ROOT / "evaluation" / "descriptor.yaml"
GENERATOR = PACKAGE_ROOT / "scripts" / "generate_tool_descriptor.py"
CLI_CONTRACT = (
    REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"
)


def run_generator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *args],
        capture_output=True,
        text=True,
    )


class TestTheDogfoodDescriptorIsDerived:
    """The file on disk must name the contract it came from."""

    def test_it_declares_a_contract(self) -> None:
        document = yaml.safe_load(DESCRIPTOR.read_text())
        assert document.get("contract"), (
            "evaluation/descriptor.yaml declares no `contract:` — it is still "
            "hand-authored, so nothing detects drift from the CLI contract"
        )

    def test_the_declared_contract_resolves(self) -> None:
        document = yaml.safe_load(DESCRIPTOR.read_text())
        resolved = (DESCRIPTOR.parent / document["contract"]).resolve()
        assert resolved == CLI_CONTRACT.resolve()

    def test_it_loads_as_the_tool_archetype(self) -> None:
        assert isinstance(load_descriptor(DESCRIPTOR), ToolDescriptor)

    def test_it_no_longer_warns(self) -> None:
        """Task 5.2's warning is for hand-authored files; this is not one."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            load_descriptor(DESCRIPTOR)


class TestTheDeclaredSurfaceIsReal:
    """``0 interfaces`` was a vacuous pass, not a clean run (D3)."""

    def test_the_declared_surface_is_not_empty(self) -> None:
        assert load_descriptor(DESCRIPTOR).all_interfaces()

    def test_it_matches_what_the_contract_declares(self) -> None:
        from_contract = ToolDescriptor.from_contract(CLI_CONTRACT)
        assert sorted(load_descriptor(DESCRIPTOR).all_interfaces()) == sorted(
            from_contract.all_interfaces()
        )

    def test_the_units_are_flags_not_commands(self) -> None:
        """A flat CLI is nameable only at the flag level (D3)."""
        units = load_descriptor(DESCRIPTOR).all_interfaces()
        assert all(unit.startswith("cli:--") for unit in units), units

    def test_the_scenario_directory_still_resolves(self) -> None:
        """Derivation must not drop the dirs the dogfood run reads."""
        descriptor = load_descriptor(DESCRIPTOR)
        assert descriptor.scenario_dirs
        for directory in descriptor.scenario_dirs:
            assert Path(directory).is_dir()
            assert list(Path(directory).glob("*.yaml"))


class TestTheDriftGuardNowGuardsSomething:
    """It could only fail before; it must now pass, and still be able to fail."""

    def test_a_bare_check_invocation_passes(self) -> None:
        """No flags. A guard whose generate and check steps must agree on
        argv reports drift on an up-to-date artifact, and gets disabled."""
        result = run_generator("--check")
        assert result.returncode == 0, result.stderr

    def test_the_check_reports_the_contracted_unit_count(self) -> None:
        result = run_generator("--check")
        expected = len(ToolDescriptor.from_contract(CLI_CONTRACT).all_interfaces())
        assert f"({expected} coverage units)" in result.stdout

    def test_a_truncated_descriptor_fails_the_check(self, tmp_path: Path) -> None:
        """Shown to fail, on the artifact rather than on a fixture."""
        truncated = tmp_path / "descriptor.yaml"
        document = yaml.safe_load(DESCRIPTOR.read_text())
        document["commands"] = [{"name": "", "flags": document["commands"][0]["flags"][:1]}]
        document["contract"] = str(CLI_CONTRACT)
        truncated.write_text(yaml.safe_dump(document, sort_keys=False))

        result = run_generator("--check", "--out", str(truncated))
        assert result.returncode == 1
        assert "mismatch" in result.stderr or "drift" in result.stderr

    def test_an_empty_descriptor_fails_the_check(self, tmp_path: Path) -> None:
        empty = tmp_path / "descriptor.yaml"
        document = yaml.safe_load(DESCRIPTOR.read_text())
        document["commands"] = []
        empty.write_text(yaml.safe_dump(document, sort_keys=False))

        result = run_generator("--check", "--out", str(empty))
        assert result.returncode == 1
        assert "zero coverage units" in result.stderr
