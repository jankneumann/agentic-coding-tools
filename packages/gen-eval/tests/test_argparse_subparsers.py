"""``verify_argparse`` must descend into subcommands (task 4.17).

Spec scenarios:
  - gen-eval-framework.implemented-surface-subset-verification
      · an uncontracted flag is reported

Design decisions: D1 (the contract is the source; introspection only verifies).

Round-7 review. ``_SubParsersAction`` carries no ``option_strings``, so
``_action_name`` returns None for it and the loop skips it — along with every
parser it contains. On a subcommand-structured CLI the verifier therefore
inspects the top-level flags and nothing else, and an undocumented ``--force``
on a subcommand is invisible to it.

The failure is quiet in the way D1 exists to prevent. The verifier reports no
violations, which is indistinguishable from a program whose surface matches its
contract exactly. A gate that cannot fail on the construct it is pointed at is
not a weaker gate — it is decoration.

The scoping matters as much as the descent: a flag found under ``acquire``
belongs to ``cli:acquire --force``, not to ``cli:--force``. Reporting it
unscoped would name an element the contract could never declare, so a correct
contract could not silence it.
"""

from __future__ import annotations

import argparse

from gen_eval.descriptor import FlagSpec, ToolCommandSpec, ToolDescriptor
from gen_eval.verify import verify_argparse


def contracted(*commands: ToolCommandSpec) -> ToolDescriptor:
    """A tool descriptor declaring exactly the given commands."""
    return ToolDescriptor(
        project="lockd",
        version="1",
        executable="lockd",
        services=[],
        commands=list(commands),
    )


def parser_with_subcommands(*, extra_sub_flag: bool = False) -> argparse.ArgumentParser:
    """A two-level CLI: global flags, then ``acquire`` / ``release``."""
    parser = argparse.ArgumentParser(prog="lockd")
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("--ttl", type=int)
    if extra_sub_flag:
        acquire.add_argument("--force", action="store_true")

    release = subparsers.add_parser("release")
    release.add_argument("--all", action="store_true")
    return parser


def full_contract() -> ToolDescriptor:
    """The contract that matches :func:`parser_with_subcommands` exactly."""
    return contracted(
        ToolCommandSpec(name="", flags=[FlagSpec(name="--verbose", type="boolean")]),
        ToolCommandSpec(name="acquire", flags=[FlagSpec(name="--ttl", type="integer")]),
        ToolCommandSpec(name="release", flags=[FlagSpec(name="--all", type="boolean")]),
    )


class TestSubcommandFlagsAreInspected:
    """The construct the verifier was blind to."""

    def test_an_uncontracted_subcommand_flag_is_reported(self) -> None:
        violations = verify_argparse(
            parser_with_subcommands(extra_sub_flag=True), full_contract()
        )
        assert [v.element for v in violations] == ["cli:acquire --force"], (
            "an undocumented flag on a subcommand is undocumented surface; a "
            "verifier that skips _SubParsersAction cannot see any of it"
        )

    def test_the_flag_is_scoped_to_its_subcommand(self) -> None:
        """``cli:--force`` is an element the contract could never declare."""
        violations = verify_argparse(
            parser_with_subcommands(extra_sub_flag=True), full_contract()
        )
        assert "cli:--force" not in {v.element for v in violations}

    def test_a_fully_contracted_parser_is_silent(self) -> None:
        """Descending must not turn contracted subcommand flags into excess."""
        assert verify_argparse(parser_with_subcommands(), full_contract()) == []

    def test_every_subparser_is_visited_not_just_the_first(self) -> None:
        parser = parser_with_subcommands()
        # Contract omits `release` entirely — both its flags are now excess.
        partial = contracted(
            ToolCommandSpec(name="", flags=[FlagSpec(name="--verbose", type="boolean")]),
            ToolCommandSpec(
                name="acquire", flags=[FlagSpec(name="--ttl", type="integer")]
            ),
        )
        assert [v.element for v in verify_argparse(parser, partial)] == [
            "cli:release --all"
        ]

    def test_a_nested_subparser_joins_its_command_path(self) -> None:
        """Two levels of subcommand produce ``cli:lock acquire --ttl``."""
        parser = argparse.ArgumentParser(prog="lockd")
        outer = parser.add_subparsers()
        lock = outer.add_parser("lock")
        inner = lock.add_subparsers()
        acquire = inner.add_parser("acquire")
        acquire.add_argument("--ttl", type=int)

        violations = verify_argparse(parser, contracted())
        assert [v.element for v in violations] == ["cli:lock acquire --ttl"]

    def test_an_explicit_command_prefixes_the_descent(self) -> None:
        """The ``command=`` argument still scopes everything below it."""
        violations = verify_argparse(
            parser_with_subcommands(), contracted(), command="lockd"
        )
        assert "cli:lockd acquire --ttl" in {v.element for v in violations}


class TestTheDescentDoesNotInventElements:
    """Descending adds reach, not noise."""

    def test_the_subparsers_action_is_not_itself_an_element(self) -> None:
        """``_SubParsersAction`` is a container, not a flag."""
        violations = verify_argparse(parser_with_subcommands(), contracted())
        assert all(v.element != "cli:" for v in violations)
        assert all("None" not in v.element for v in violations)

    def test_a_subparsers_help_action_is_skipped(self) -> None:
        """Every sub-parser installs its own ``-h``; none of them is surface."""
        violations = verify_argparse(parser_with_subcommands(), contracted())
        assert all("--help" not in v.element for v in violations)

    def test_an_aliased_subcommand_is_reported_once(self) -> None:
        """Aliases are spellings of one command, as ``--quiet -q`` is of one flag."""
        parser = argparse.ArgumentParser(prog="lockd")
        subparsers = parser.add_subparsers()
        acquire = subparsers.add_parser("acquire", aliases=["acq"])
        acquire.add_argument("--ttl", type=int)

        violations = verify_argparse(parser, contracted())
        assert [v.element for v in violations] == ["cli:acquire --ttl"]

    def test_top_level_flags_are_unchanged(self) -> None:
        """Rule 4 — a flat parser behaves exactly as before."""
        parser = argparse.ArgumentParser(prog="flat")
        parser.add_argument("--verbose", action="store_true")
        assert [v.element for v in verify_argparse(parser, contracted())] == [
            "cli:--verbose"
        ]

    def test_a_parser_with_no_subparsers_is_unchanged(self) -> None:
        parser = argparse.ArgumentParser(prog="flat")
        parser.add_argument("--ttl", type=int)
        descriptor = contracted(
            ToolCommandSpec(name="", flags=[FlagSpec(name="--ttl", type="integer")])
        )
        assert verify_argparse(parser, descriptor) == []


class TestRecursionIsBounded:
    """A parser graph is not guaranteed to be a tree."""

    def test_a_self_referential_parser_does_not_recurse_forever(self) -> None:
        """Hand-built parsers can contain a cycle; the verifier must terminate."""
        parser = argparse.ArgumentParser(prog="cyclic")
        subparsers = parser.add_subparsers()
        child = subparsers.add_parser("child")
        child.add_argument("--flag", action="store_true")
        # Point the child's own choices back at its parent.
        child_subparsers = child.add_subparsers()
        child_subparsers._name_parser_map["loop"] = parser

        violations = verify_argparse(parser, contracted())
        assert "cli:child --flag" in {v.element for v in violations}
