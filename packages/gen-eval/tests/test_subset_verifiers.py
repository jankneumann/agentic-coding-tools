"""The implementation exposes no surface its contract omits (task 4.1).

Spec scenarios:
  - gen-eval-framework.implemented-surface-subset-verification
      · undocumented CLI flag is reported
      · verification distinguishes excess from omission

Design decisions: D1 (the contract is the source; introspection only verifies).

D1 makes the contract the declared surface and forbids introspection from
*populating* it. That leaves one job introspection is still needed for, and it
runs in one direction only: the implementation must be a **subset** of the
contract. Excess is a contract violation — a flag users can reach that nothing
documents. Omission is not: a contracted flag the parser never grew is a
coverage gap, reported by the coverage model, and reporting it here as well
would mean the same defect arrives twice under two names.

That asymmetry is the whole design, so the negative control matters as much as
the positive one: a parser missing a contracted flag must produce **zero**
violations here.

``--help`` is the standing case for exclusions. argparse installs it; the
application never declares it; the contract deliberately omits it (see the
header of ``openspec/contracts/gen-eval-framework/cli/gen-eval.yaml``). A
verifier that reported it would be wrong on every argparse program ever
written.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from gen_eval.descriptor import ToolDescriptor
from gen_eval.verify import Violation, verify_argparse

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_CONTRACT = REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"

CONTRACT_TEXT = """\
contract_version: "1"
tool:
  name: widget
  executable: widget
commands:
  - name: ""
    flags:
      - name: --input
        type: path
        required: true
      - name: --dry-run
        type: boolean
      - name: --verbose
        short: -v
        type: boolean
"""


@pytest.fixture(scope="module")
def widget(tmp_path_factory: pytest.TempPathFactory) -> ToolDescriptor:
    path = tmp_path_factory.mktemp("contract") / "widget.yaml"
    path.write_text(CONTRACT_TEXT)
    return ToolDescriptor.from_contract(path)


@pytest.fixture(scope="module")
def gen_eval_tool() -> ToolDescriptor:
    return ToolDescriptor.from_contract(CLI_CONTRACT)


def conformant_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="widget")
    parser.add_argument("--input", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def elements(violations: list[Violation]) -> set[str]:
    return {violation.element for violation in violations}


# ---------------------------------------------------------------------------
# Excess
# ---------------------------------------------------------------------------


class TestUndocumentedFlagIsReported:
    def test_an_undocumented_flag_produces_a_violation(self, widget: ToolDescriptor) -> None:
        parser = conformant_parser()
        parser.add_argument("--force", action="store_true")
        assert elements(verify_argparse(parser, widget)) == {"cli:--force"}

    def test_the_violation_names_the_flag(self, widget: ToolDescriptor) -> None:
        """An operator has to be able to act on it without re-deriving anything."""
        parser = conformant_parser()
        parser.add_argument("--force", action="store_true")
        (violation,) = verify_argparse(parser, widget)
        assert "--force" in violation.message
        assert violation.surface == "cli"

    def test_every_undocumented_flag_is_reported_not_just_the_first(
        self, widget: ToolDescriptor
    ) -> None:
        parser = conformant_parser()
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--retry", type=int)
        assert elements(verify_argparse(parser, widget)) == {"cli:--force", "cli:--retry"}

    def test_an_undocumented_short_flag_is_reported_under_its_long_name(
        self, widget: ToolDescriptor
    ) -> None:
        """One action is one flag however many spellings it has."""
        parser = conformant_parser()
        parser.add_argument("--quiet", "-q", action="store_true")
        assert elements(verify_argparse(parser, widget)) == {"cli:--quiet"}


# ---------------------------------------------------------------------------
# Not excess
# ---------------------------------------------------------------------------


class TestConformantImplementationIsSilent:
    def test_a_conformant_parser_reports_nothing(self, widget: ToolDescriptor) -> None:
        assert verify_argparse(conformant_parser(), widget) == []

    def test_the_argparse_supplied_help_flag_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        """argparse installs --help; the application never declared it.

        Reporting it would make the verifier wrong on every argparse program,
        and it is why the gen-eval contract documents the omission rather than
        contracting a flag it does not own.
        """
        assert "cli:--help" not in elements(verify_argparse(conformant_parser(), widget))

    def test_an_argparse_version_action_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        parser = conformant_parser()
        parser.add_argument("--version", action="version", version="1.0")
        assert verify_argparse(parser, widget) == []

    def test_a_positional_argument_is_not_reported_as_a_flag(
        self, widget: ToolDescriptor
    ) -> None:
        """A positional has no option strings; it is a different coverage unit."""
        parser = conformant_parser()
        parser.add_argument("target")
        assert elements(verify_argparse(parser, widget)) == set()


class TestOmissionIsCoveragesJob:
    """The asymmetry D1 rests on, asserted as a negative control."""

    def test_a_contracted_flag_the_parser_lacks_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        parser = argparse.ArgumentParser(prog="widget")
        parser.add_argument("--input", required=True)
        assert verify_argparse(parser, widget) == []

    def test_a_parser_declaring_nothing_at_all_is_not_a_violation(
        self, widget: ToolDescriptor
    ) -> None:
        """Zero violations, three uncovered units. Two different reports."""
        assert verify_argparse(argparse.ArgumentParser(prog="widget"), widget) == []

    def test_excess_and_omission_together_report_only_the_excess(
        self, widget: ToolDescriptor
    ) -> None:
        parser = argparse.ArgumentParser(prog="widget")
        parser.add_argument("--input", required=True)
        parser.add_argument("--force", action="store_true")
        assert elements(verify_argparse(parser, widget)) == {"cli:--force"}


# ---------------------------------------------------------------------------
# Against the real contract
# ---------------------------------------------------------------------------


class TestAgainstGenEvalsOwnContract:
    """The surface this change owns end to end (task 4.7 wires it into CI)."""

    def test_a_parser_matching_the_contract_is_silent(
        self, gen_eval_tool: ToolDescriptor
    ) -> None:
        parser = argparse.ArgumentParser(prog="gen-eval")
        for unit in gen_eval_tool.all_interfaces():
            parser.add_argument(unit.removeprefix("cli:"), action="store_true")
        assert verify_argparse(parser, gen_eval_tool) == []

    def test_adding_one_uncontracted_flag_turns_it_red(
        self, gen_eval_tool: ToolDescriptor
    ) -> None:
        """The gate must be shown to fail, not merely to pass."""
        parser = argparse.ArgumentParser(prog="gen-eval")
        for unit in gen_eval_tool.all_interfaces():
            parser.add_argument(unit.removeprefix("cli:"), action="store_true")
        parser.add_argument("--undeclared", action="store_true")
        assert elements(verify_argparse(parser, gen_eval_tool)) == {"cli:--undeclared"}
