"""``ExpectBlock.error_excludes`` — asserting a substring is ABSENT.

Round-8 finding H1. Three of the five scenarios in
``evaluation/scenarios/flag-surface.yaml`` credited a flag they did not
discriminate: run the same fixture with the flag removed and the assertion
still held. The cause was expressive rather than careless — the flags under
test (``--report-format json``, ``--no-services``) work by REMOVING output, and
``ExpectBlock`` could only assert presence. A suite that can only say "this
appeared" cannot exercise a flag whose whole effect is that something didn't.

So the primitive is the fix and the scenarios are the consumer. Both are tested
here: the mechanism below, and (in ``TestTheScenariosActuallyUseIt``) the fact
that the three rewritten scenarios still depend on it, so a future edit cannot
quietly restore the laundering by dropping the assertion.

Rule 4: the field defaults to ``None`` and every existing scenario omits it, so
nothing that passed before behaves differently.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from gen_eval.clients.base import TransportClientRegistry
from gen_eval.clients.cli_client import CliClient
from gen_eval.descriptor import InterfaceDescriptor, ServiceSpec
from gen_eval.evaluator import Evaluator
from gen_eval.models import ActionStep, ExpectBlock, Scenario

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
FLAG_SURFACE = PACKAGE_ROOT / "evaluation" / "scenarios" / "flag-surface.yaml"


def _evaluator() -> Evaluator:
    registry = TransportClientRegistry()
    registry.register("cli", CliClient(command=sys.executable))
    return Evaluator(
        InterfaceDescriptor(
            project="p",
            version="1",
            services=[ServiceSpec(name="c", type="cli", command=sys.executable)],
        ),
        registry,
    )


def _scenario(step: ActionStep) -> Scenario:
    return Scenario(
        id="s",
        name="error_excludes",
        description="asserts a substring is absent from stderr",
        category="cli",
        interfaces=["cli:python"],
        steps=[step],
    )


def _emit(text: str, *, exit_code: int = 0) -> ActionStep:
    """A step whose stderr is exactly ``text``."""
    return ActionStep(
        id="emit",
        transport="cli",
        args=[
            "-c",
            f"import sys; sys.stderr.write({text!r}); sys.exit({exit_code})",
        ],
    )


class TestTheMechanism:
    async def test_passes_when_the_substring_is_absent(self) -> None:
        step = _emit("wrote report.json\n")
        step.expect = ExpectBlock(exit_code=0, error_excludes="report.md")
        verdict = await _evaluator().evaluate(_scenario(step))
        assert verdict.status == "pass", verdict

    async def test_fails_when_the_substring_is_present(self) -> None:
        step = _emit("wrote report.json\nwrote report.md\n")
        step.expect = ExpectBlock(exit_code=0, error_excludes="report.md")
        verdict = await _evaluator().evaluate(_scenario(step))
        assert verdict.status != "pass", (
            "a forbidden substring was present and the step still passed — "
            "this is the assertion doing nothing, which is the defect the "
            "primitive exists to remove"
        )

    async def test_it_is_the_exact_opposite_of_error_contains(self) -> None:
        """Same haystacks, inverted verdict.

        If the two searched different places, ``error_excludes`` could report
        'absent' about a string ``error_contains`` would have found — a
        false green that is worse than no assertion.
        """
        text = "the needle is here\n"
        contains = _emit(text)
        contains.expect = ExpectBlock(exit_code=0, error_contains="needle")
        excludes = _emit(text)
        excludes.expect = ExpectBlock(exit_code=0, error_excludes="needle")

        assert (await _evaluator().evaluate(_scenario(contains))).status == "pass"
        assert (await _evaluator().evaluate(_scenario(excludes))).status != "pass"

    async def test_omitting_it_changes_nothing(self) -> None:
        """Rule 4: the field is inert unless set."""
        step = _emit("anything at all\n")
        step.expect = ExpectBlock(exit_code=0)
        assert (await _evaluator().evaluate(_scenario(step))).status == "pass"

    def test_it_defaults_to_none(self) -> None:
        assert ExpectBlock(exit_code=0).error_excludes is None


class TestTheScenariosActuallyUseIt:
    """The primitive is only worth having if the suite depends on it.

    These assert on the shipped scenario file rather than a fixture. A fixture
    written here would agree with whatever this test expects; only the real
    file can disagree — the same reason wp-resolver is told to drive the
    repository's own specs.
    """

    def _steps_by_scenario(self) -> dict[str, list[dict]]:
        document = yaml.safe_load(FLAG_SURFACE.read_text())
        return {entry["id"]: entry["steps"] for entry in document}

    def test_the_three_rewritten_scenarios_assert_an_absence(self) -> None:
        by_id = self._steps_by_scenario()
        for scenario_id in (
            "cli-report-format-json-writes-only-json",
            "cli-mode-rejects-an-unknown-value",
            "cli-no-services-skips-startup",
        ):
            assert scenario_id in by_id, (
                f"{scenario_id} is gone from {FLAG_SURFACE.name} — if it was "
                f"renamed, update this test rather than deleting the check"
            )
            expects = [step.get("expect") or {} for step in by_id[scenario_id]]
            assert any("error_excludes" in expect for expect in expects), (
                f"{scenario_id} no longer asserts an absence. Round-8 H1 found "
                f"this scenario passing with its flag removed; the absence "
                f"assertion is what fixed it."
            )

    def test_no_services_drives_the_failing_startup_fixture(self) -> None:
        """The fixture is the other half of the fix.

        Against ``no-scenarios-descriptor.yaml`` — which has no startup block —
        skipping startup and having none to skip are indistinguishable, so no
        assertion could discriminate the flag.
        """
        steps = self._steps_by_scenario()["cli-no-services-skips-startup"]
        args = [arg for step in steps for arg in step.get("args", [])]
        assert any("failing-startup-descriptor.yaml" in arg for arg in args), (
            "the --no-services scenario is back on a descriptor with nothing "
            "to start, which makes its assertion hold with the flag removed"
        )
        fixture = PACKAGE_ROOT / "evaluation" / "fixtures" / (
            "failing-startup-descriptor.yaml"
        )
        startup = yaml.safe_load(fixture.read_text())["startup"]
        assert startup["command"] == "false", (
            "the startup command must fail, or the two runs are identical"
        )
        assert startup["health_check"].startswith("file://"), (
            "the health check must PASS: --no-services skips the startup "
            "command but still runs the health check, so a failing one would "
            "sink both runs and re-hide the flag"
        )
