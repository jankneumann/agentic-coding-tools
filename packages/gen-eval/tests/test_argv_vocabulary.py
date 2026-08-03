"""argv is not a flag list: ``--`` terminates, and ``-v`` names ``--verbose`` (task 4.15).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · a flag exercised by a scenario is recorded as covered

Design decisions: D10 (one coverage vocabulary shared by declared and tested).

Round-7 review, two independent findings about the same tokeniser. Both are
mis-readings of argv, and they fail in opposite directions:

**The terminator over-credits.** ``_is_flag`` classifies by shape, so every
token after a bare ``--`` that happens to start with a dash is recorded as an
exercised flag. ``['--mode', 'template-only', '--', '--descriptor']`` credits
``cli:--descriptor`` for a token the process passed through as a positional
value and never interpreted. Coverage then reports a flag as tested when
nothing tested it — the gate passes on evidence that does not exist.

**The alias under-credits.** ``coverage_units`` emits ``flag.name`` only, so a
declared ``--verbose`` with ``short: -v`` contributes exactly one unit. A step
invoking ``-v`` produces ``cli:-v``, misses the declared-membership filter, and
``cli:--verbose`` stays uncovered despite a real exercise. That is precisely
the vocabulary split D10 exists to close, reappearing one level below the
command name.

The declared-membership filter is why the second half is not self-correcting:
an unmatched token is silently dropped rather than reported, so the only
visible symptom is a coverage percentage that is quietly too low.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gen_eval.descriptor import FlagSpec, ToolCommandSpec, ToolDescriptor
from gen_eval.evaluator import Evaluator
from gen_eval.models import ActionStep

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
CLI_CONTRACT = (
    REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"
)


def identifiers(
    args: list[str],
    declared: set[str],
    aliases: dict[str, str] | None = None,
) -> list[str]:
    """Run one argv token list through the CLI tokeniser."""
    step = ActionStep(id="s1", transport="cli", args=args)
    return Evaluator._cli_identifiers(step, declared, aliases)


@pytest.fixture(scope="module")
def gen_eval_declared() -> set[str]:
    """gen-eval's own contracted coverage units — a flat, subcommand-less CLI."""
    return set(ToolDescriptor.from_contract(CLI_CONTRACT).all_interfaces())


def aliased_descriptor() -> ToolDescriptor:
    """A tool whose contract gives two of its flags a short spelling."""
    return ToolDescriptor(
        project="aliased",
        version="1",
        executable="aliased",
        services=[],
        commands=[
            ToolCommandSpec(
                name="",
                flags=[
                    FlagSpec(name="--verbose", short="-v", type="boolean"),
                    FlagSpec(name="--output", short="-o", type="path"),
                    FlagSpec(name="--quiet"),
                ],
            )
        ],
    )


class TestEndOfOptionsTerminator:
    """A bare ``--`` ends option parsing; everything after it is a value."""

    def test_a_dashed_token_after_the_terminator_is_not_credited(
        self, gen_eval_declared: set[str]
    ) -> None:
        """The over-crediting case: coverage claims a flag nothing exercised."""
        recorded = identifiers(
            ["--mode", "template-only", "--", "--descriptor"], gen_eval_declared
        )
        assert "cli:--descriptor" not in recorded, (
            "`--descriptor` after `--` is a positional value the process never "
            "interpreted as a flag; crediting it makes coverage report a gate "
            "that was never exercised"
        )

    def test_flags_before_the_terminator_are_still_credited(
        self, gen_eval_declared: set[str]
    ) -> None:
        """Rule 4 — the terminator ends scanning, it does not discard the scan."""
        recorded = identifiers(
            ["--mode", "template-only", "--", "--descriptor"], gen_eval_declared
        )
        assert "cli:--mode" in recorded

    def test_the_terminator_is_not_part_of_the_command_path(
        self, gen_eval_declared: set[str]
    ) -> None:
        """``--`` is not a flag by shape, so the command scan must stop on it too."""
        recorded = identifiers(["--", "lock", "status"], gen_eval_declared)
        assert not any(identifier.startswith("cli:--") for identifier in recorded), (
            f"the terminator leaked into the command path: {recorded}"
        )

    def test_a_second_terminator_is_also_just_a_value(
        self, gen_eval_declared: set[str]
    ) -> None:
        """Only the first ``--`` is special; a later one is ordinary text."""
        recorded = identifiers(
            ["--verbose", "--", "--", "--descriptor"], gen_eval_declared
        )
        assert recorded == ["cli:--verbose"]

    def test_an_equals_form_after_the_terminator_is_not_credited(
        self, gen_eval_declared: set[str]
    ) -> None:
        recorded = identifiers(["--", "--output-dir=/tmp/x"], gen_eval_declared)
        assert "cli:--output-dir" not in recorded


class TestShortFlagsCreditTheirLongUnit:
    """A contract that declares ``short`` declares one unit with two spellings."""

    def test_the_descriptor_publishes_the_alias_map(self) -> None:
        """The map lives with the contract, not in the tokeniser (D10)."""
        assert aliased_descriptor().coverage_aliases() == {
            "cli:-v": "cli:--verbose",
            "cli:-o": "cli:--output",
        }

    def test_a_short_flag_credits_the_long_unit(self) -> None:
        """The under-crediting case: a real exercise that coverage cannot see."""
        descriptor = aliased_descriptor()
        declared = set(descriptor.all_interfaces())
        recorded = identifiers(["-v"], declared, descriptor.coverage_aliases())
        assert recorded == ["cli:--verbose"], (
            "`-v` is the declared short spelling of `--verbose`; recording "
            "`cli:-v` splits one unit into two vocabularies and leaves the "
            "declared one permanently uncovered"
        )

    def test_the_long_spelling_is_unchanged(self) -> None:
        """Rule 4 — aliasing adds a spelling, it does not move the unit."""
        descriptor = aliased_descriptor()
        declared = set(descriptor.all_interfaces())
        assert identifiers(["--verbose"], declared, descriptor.coverage_aliases()) == [
            "cli:--verbose"
        ]

    def test_an_undeclared_short_flag_credits_nothing(self) -> None:
        """The membership filter still decides; the alias map only translates."""
        descriptor = aliased_descriptor()
        declared = set(descriptor.all_interfaces())
        assert identifiers(["-z"], declared, descriptor.coverage_aliases()) == []

    def test_a_flag_without_a_short_spelling_contributes_no_alias(self) -> None:
        """``--quiet`` declares no short form, so no ``cli:-q`` may appear."""
        assert "cli:-q" not in aliased_descriptor().coverage_aliases()

    def test_a_short_flag_is_scoped_to_its_command(self) -> None:
        """Subcommand flags alias within their command, not globally."""
        descriptor = ToolDescriptor(
            project="scoped",
            version="1",
            executable="scoped",
            services=[],
            commands=[
                ToolCommandSpec(
                    name="lock acquire",
                    flags=[FlagSpec(name="--ttl", short="-t", type="integer")],
                )
            ],
        )
        declared = set(descriptor.all_interfaces())
        assert descriptor.coverage_aliases() == {
            "cli:lock acquire -t": "cli:lock acquire --ttl"
        }
        recorded = identifiers(
            ["lock", "acquire", "-t", "30"], declared, descriptor.coverage_aliases()
        )
        assert "cli:lock acquire --ttl" in recorded

    def test_a_short_flag_after_the_terminator_is_not_credited(self) -> None:
        """Both fixes compose: aliasing must not resurrect a terminated token."""
        descriptor = aliased_descriptor()
        declared = set(descriptor.all_interfaces())
        recorded = identifiers(["--", "-v"], declared, descriptor.coverage_aliases())
        assert recorded == []


class TestAliasesAreOptional:
    """Rule 4 — callers that pass no map keep today's behaviour exactly."""

    def test_omitting_the_map_is_the_current_behaviour(
        self, gen_eval_declared: set[str]
    ) -> None:
        step = ActionStep(id="s1", transport="cli", args=["--verbose"])
        assert Evaluator._cli_identifiers(step, gen_eval_declared) == ["cli:--verbose"]

    def test_a_descriptor_with_no_short_flags_publishes_an_empty_map(self) -> None:
        """gen-eval's own contract declares none, so the map must be empty."""
        assert ToolDescriptor.from_contract(CLI_CONTRACT).coverage_aliases() == {}

    def test_the_base_descriptor_publishes_an_empty_map(self) -> None:
        """Non-tool archetypes have no flags; the API must still exist."""
        from gen_eval.descriptor import InterfaceDescriptor

        assert (
            InterfaceDescriptor(project="p", version="1", services=[]).coverage_aliases()
            == {}
        )
