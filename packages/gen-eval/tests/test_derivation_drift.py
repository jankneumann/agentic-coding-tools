"""The tool-descriptor drift guard's three fail-closed assertions (task 1.5).

Spec scenarios:
  - gen-eval-framework.descriptor-derivation-drift-guard
      · drift between contract and checked-in descriptor fails
      · an empty derived descriptor fails rather than passing trivially
      · operation count mismatch fails
      · a tool contract declaring commands but no coverage units fails

Design decisions: D2 (derivation produces checked-in artifacts), D3 (every
guard fails closed, counting the archetype's own coverage unit).

**Every assertion here is proven to fail on a deliberately broken fixture.**
A guard exercised only against good input is decoration: it cannot tell you
whether it would have caught the thing it exists to catch. The four fixtures
are the ones D3 names:

``empty``
    A contract declaring no commands at all. Derives nothing.
``one_command_zero_flags``
    The case that motivated D3. ``[{"name": ""}]`` declares one command, so a
    guard phrased in terms of *commands* counts 1, matches 1, and diffs clean
    — while the derived surface is empty. Counting coverage units instead is
    the fix, and this fixture is what proves the fix took.
``count_mismatch``
    A checked-in descriptor with fewer units than its contract.
``drifted``
    A checked-in descriptor with the *same* unit count but different content.
    Only the byte-identity assertion catches this one.

The negative controls matter as much: a fresh artifact must pass, or these
tests would be satisfied by a guard that fails on everything.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from gen_eval.descriptor import ToolDescriptor

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
GENERATOR = PACKAGE_ROOT / "scripts" / "generate_tool_descriptor.py"

GOOD_CONTRACT: dict[str, Any] = {
    "contract_version": "1",
    "tool": {"name": "widget", "executable": "widget", "description": "A widget."},
    "commands": [
        {
            "name": "",
            "description": "Flat CLI.",
            "flags": [
                {"name": "--input", "type": "path", "required": True},
                {"name": "--mode", "type": "enum", "choices": ["fast", "slow"]},
                {"name": "--verbose", "type": "boolean"},
            ],
        }
    ],
    "exit_codes": [{"code": 0, "meaning": "ok"}, {"code": 2, "meaning": "usage"}],
}

EMPTY_CONTRACT: dict[str, Any] = {
    "contract_version": "1",
    "tool": {"name": "widget", "executable": "widget"},
    "commands": [],
}

#: One command, zero flags — the vacuous pass D3 was written against.
ONE_COMMAND_ZERO_FLAGS_CONTRACT: dict[str, Any] = {
    "contract_version": "1",
    "tool": {"name": "widget", "executable": "widget"},
    "commands": [{"name": "", "description": "Declares nothing testable."}],
}


def write_contract(directory: Path, contract: dict[str, Any]) -> Path:
    path = directory / "cli.yaml"
    path.write_text(yaml.safe_dump(contract, sort_keys=False))
    return path


def run_generator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GENERATOR), *(str(a) for a in args)],
        cwd=str(PACKAGE_ROOT),
        capture_output=True,
        text=True,
    )


@pytest.fixture
def generated(tmp_path: Path) -> tuple[Path, Path]:
    """A contract and a freshly generated, in-sync descriptor beside it."""
    contract = write_contract(tmp_path, GOOD_CONTRACT)
    out = tmp_path / "descriptor.yaml"
    result = run_generator("--contract", contract, "--out", out)
    assert result.returncode == 0, result.stderr
    return contract, out


# ---------------------------------------------------------------------------
# The generator itself
# ---------------------------------------------------------------------------


class TestGeneration:
    def test_writes_a_loadable_descriptor(self, generated: tuple[Path, Path]) -> None:
        _, out = generated
        descriptor = ToolDescriptor.from_yaml(out)
        assert sorted(descriptor.all_interfaces()) == [
            "cli:--input",
            "cli:--mode",
            "cli:--verbose",
        ]

    def test_is_deterministic(self, generated: tuple[Path, Path]) -> None:
        """Regeneration must be byte-stable, or --check reports permanent drift."""
        contract, out = generated
        first = out.read_text()
        assert run_generator("--contract", contract, "--out", out).returncode == 0
        assert out.read_text() == first

    def test_records_the_contract_as_a_relative_path(self, generated: tuple[Path, Path]) -> None:
        """An absolute path in a checked-in artifact is drift on every machine."""
        contract, out = generated
        raw = yaml.safe_load(out.read_text())
        assert not Path(raw["contract"]).is_absolute()
        # Relative is not enough — it has to point back at the real contract.
        assert ToolDescriptor.from_yaml(out).contract == contract.resolve()

    def test_check_passes_on_a_fresh_artifact(self, generated: tuple[Path, Path]) -> None:
        """Negative control: the guard is satisfiable."""
        contract, out = generated
        result = run_generator("--contract", contract, "--out", out, "--check")
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# D3, assertion 1 — non-emptiness
# ---------------------------------------------------------------------------


class TestNonEmptinessAssertion:
    def test_empty_contract_fails_generation(self, tmp_path: Path) -> None:
        contract = write_contract(tmp_path, EMPTY_CONTRACT)
        out = tmp_path / "descriptor.yaml"
        result = run_generator("--contract", contract, "--out", out)
        assert result.returncode != 0
        assert "zero coverage units" in result.stderr

    def test_empty_contract_writes_nothing(self, tmp_path: Path) -> None:
        """Refusing to write is what keeps ``--check`` from passing later.

        A generator that emits a degenerate artifact and *then* reports the
        problem leaves an empty file checked in, after which the byte-identity
        assertion compares empty against empty and goes green forever.
        """
        contract = write_contract(tmp_path, EMPTY_CONTRACT)
        out = tmp_path / "descriptor.yaml"
        run_generator("--contract", contract, "--out", out)
        assert not out.exists()

    def test_one_command_zero_flags_fails(self, tmp_path: Path) -> None:
        """D3's motivating case: 1 command, 0 units, empty declared surface."""
        contract = write_contract(tmp_path, ONE_COMMAND_ZERO_FLAGS_CONTRACT)
        out = tmp_path / "descriptor.yaml"
        result = run_generator("--contract", contract, "--out", out)
        assert result.returncode != 0
        assert "zero coverage units" in result.stderr

    def test_one_command_zero_flags_is_not_rescued_by_counting_commands(
        self, tmp_path: Path
    ) -> None:
        """The guard must not report the command count as a coverage count.

        This is the whole of D3: 1 == 1 is true and irrelevant.
        """
        contract = write_contract(tmp_path, ONE_COMMAND_ZERO_FLAGS_CONTRACT)
        out = tmp_path / "descriptor.yaml"
        result = run_generator("--contract", contract, "--out", out)
        assert result.returncode != 0
        assert "up to date" not in result.stdout

    def test_empty_checked_in_copy_fails_check_rather_than_matching_an_empty_contract(
        self, tmp_path: Path
    ) -> None:
        """Why assertion 3 alone is not enough — "empty == empty" must not pass.

        Both files can rot to nothing together and a pure diff stays green.
        """
        contract = write_contract(tmp_path, EMPTY_CONTRACT)
        out = tmp_path / "descriptor.yaml"
        out.write_text(
            yaml.safe_dump(
                {
                    "project": "widget",
                    "version": "1",
                    "executable": "widget",
                    "contract": "cli.yaml",
                    "services": [],
                    "commands": [],
                },
                sort_keys=False,
            )
        )
        result = run_generator("--contract", contract, "--out", out, "--check")
        assert result.returncode != 0
        assert "zero coverage units" in result.stderr


# ---------------------------------------------------------------------------
# D3, assertion 2 — the counts must agree
# ---------------------------------------------------------------------------


class TestCountAssertion:
    def test_count_mismatch_fails(self, generated: tuple[Path, Path]) -> None:
        contract, out = generated
        document = yaml.safe_load(out.read_text())
        document["commands"][0]["flags"] = document["commands"][0]["flags"][:2]
        out.write_text(yaml.safe_dump(document, sort_keys=False))

        result = run_generator("--contract", contract, "--out", out, "--check")
        assert result.returncode != 0

    def test_count_mismatch_reports_both_counts(self, generated: tuple[Path, Path]) -> None:
        """The spec requires both numbers; "counts differ" does not locate anything."""
        contract, out = generated
        document = yaml.safe_load(out.read_text())
        document["commands"][0]["flags"] = document["commands"][0]["flags"][:2]
        out.write_text(yaml.safe_dump(document, sort_keys=False))

        stderr = run_generator("--contract", contract, "--out", out, "--check").stderr
        assert "2" in stderr and "3" in stderr

    def test_count_mismatch_is_caught_before_the_diff(self, generated: tuple[Path, Path]) -> None:
        """Ordering matters: a count mismatch must not be reported as mere drift.

        Both are true of the same file; the count is the more specific failure
        and the one that says the artifact is structurally wrong rather than
        stale.
        """
        contract, out = generated
        document = yaml.safe_load(out.read_text())
        document["commands"][0]["flags"] = document["commands"][0]["flags"][:2]
        out.write_text(yaml.safe_dump(document, sort_keys=False))

        stderr = run_generator("--contract", contract, "--out", out, "--check").stderr
        assert "coverage unit" in stderr


# ---------------------------------------------------------------------------
# D3, assertion 3 — byte identity
# ---------------------------------------------------------------------------


class TestByteIdentityAssertion:
    def test_drifted_content_with_a_matching_count_fails(
        self, generated: tuple[Path, Path]
    ) -> None:
        """Renaming a flag keeps the count; only the diff catches it."""
        contract, out = generated
        document = yaml.safe_load(out.read_text())
        document["commands"][0]["flags"][0]["name"] = "--renamed"
        out.write_text(yaml.safe_dump(document, sort_keys=False))

        result = run_generator("--contract", contract, "--out", out, "--check")
        assert result.returncode != 0
        assert "drift" in result.stderr.lower()

    def test_drifted_contract_fails_until_the_descriptor_is_regenerated(
        self, generated: tuple[Path, Path]
    ) -> None:
        """The direction that actually happens: the contract moves first."""
        contract, out = generated
        document = yaml.safe_load(contract.read_text())
        document["commands"][0]["flags"].append({"name": "--added", "type": "boolean"})
        contract.write_text(yaml.safe_dump(document, sort_keys=False))

        assert run_generator("--contract", contract, "--out", out, "--check").returncode != 0

        assert run_generator("--contract", contract, "--out", out).returncode == 0
        assert run_generator("--contract", contract, "--out", out, "--check").returncode == 0

    def test_a_missing_artifact_fails_rather_than_being_treated_as_up_to_date(
        self, tmp_path: Path
    ) -> None:
        contract = write_contract(tmp_path, GOOD_CONTRACT)
        result = run_generator("--contract", contract, "--out", tmp_path / "absent.yaml", "--check")
        assert result.returncode != 0
