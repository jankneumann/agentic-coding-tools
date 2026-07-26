"""Tested identifiers share a vocabulary with the declared surface (task 3.5).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · a flag exercised by a scenario is recorded as covered

Design decisions: D10 (coverage vocabulary), D4 (operation × surface).

Coverage is a set intersection. If the declared surface and the tested set are
drawn from different vocabularies the intersection is empty and the framework
reports 0% while the suite exercises everything — a number that looks like a
finding but measures only the naming mismatch.

gen-eval's own dogfood is exactly that case today. ``_extract_interfaces``
requires ``step.command`` to be truthy for a CLI step, and every one of
gen-eval's scenarios uses ``args: [...]`` with no ``command``. It yields the
empty list for all of them. That is why this module drives the **real**
scenario files rather than a synthetic step: a synthetic ``command`` step
passes today and would have proved nothing.

The declared vocabulary for a flat tool is the flag — ``cli:--descriptor`` —
because such a program has no subcommands to name. See the tool contract at
``openspec/contracts/gen-eval-framework/cli/gen-eval.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gen_eval.__main__ import DEFAULT_MIN_COVERAGE, exit_decision, parse_args
from gen_eval.descriptor import ToolDescriptor
from gen_eval.evaluator import Evaluator
from gen_eval.models import ActionStep, Scenario
from gen_eval.reports import GenEvalReport

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
SCENARIO_DIR = PACKAGE_ROOT / "evaluation" / "scenarios"
CLI_CONTRACT = REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"


def load_dogfood_scenarios() -> list[Scenario]:
    """The real dogfood scenarios, loaded the way the generator loads them."""
    scenarios: list[Scenario] = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for item in data if isinstance(data, list) else [data]:
            scenarios.append(Scenario(**item))
    return scenarios


@pytest.fixture(scope="module")
def declared() -> set[str]:
    """gen-eval's contracted coverage units, from its own CLI contract."""
    return set(ToolDescriptor.from_contract(CLI_CONTRACT).all_interfaces())


@pytest.fixture(scope="module")
def dogfood() -> list[Scenario]:
    scenarios = load_dogfood_scenarios()
    assert scenarios, f"no dogfood scenarios found under {SCENARIO_DIR}"
    return scenarios


@pytest.fixture(scope="module")
def dogfood_steps(dogfood: list[Scenario]) -> list[ActionStep]:
    return [step for scenario in dogfood for step in scenario.steps]


def extracted(steps: list[ActionStep], declared: set[str]) -> list[str]:
    return Evaluator._extract_interfaces(steps, declared=declared)


# ---------------------------------------------------------------------------
# The premise
# ---------------------------------------------------------------------------


class TestTheRealScenariosUseTheArgsForm:
    """Pin the premise. If this stops holding, the defect below is gone too."""

    def test_every_dogfood_cli_step_uses_args_not_command(
        self, dogfood_steps: list[ActionStep]
    ) -> None:
        cli_steps = [s for s in dogfood_steps if s.transport == "cli"]
        assert cli_steps, "dogfood must exercise the CLI transport"
        assert all(step.command is None for step in cli_steps)

    def test_the_contract_declares_flag_level_units(self, declared: set[str]) -> None:
        """A flat CLI's units are its flags. Nothing else is nameable."""
        assert "cli:--descriptor" in declared
        assert declared, "the tool contract must declare a non-empty surface"


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


class TestArgsOnlyStepsProduceTestedIdentifiers:
    def test_the_real_dogfood_steps_produce_a_non_empty_tested_set(
        self, dogfood_steps: list[ActionStep], declared: set[str]
    ) -> None:
        """The headline: eight real steps, zero identifiers, 0% coverage."""
        assert extracted(dogfood_steps, declared) != []

    @pytest.mark.parametrize(
        "flag",
        [
            "--descriptor",
            "--print-contract-version",
            "--fail-threshold",
            "--output-dir",
            "--openspec-change",
        ],
    )
    def test_each_flag_the_dogfood_exercises_is_recorded(
        self, dogfood_steps: list[ActionStep], declared: set[str], flag: str
    ) -> None:
        assert f"cli:{flag}" in extracted(dogfood_steps, declared)

    def test_every_tested_identifier_is_drawn_from_the_declared_vocabulary(
        self, dogfood_steps: list[ActionStep], declared: set[str]
    ) -> None:
        """D10 stated directly: the intersection is what coverage measures."""
        assert set(extracted(dogfood_steps, declared)) <= declared

    def test_argument_values_are_not_mistaken_for_interfaces(
        self, dogfood_steps: list[ActionStep], declared: set[str]
    ) -> None:
        """``--descriptor unused.yaml`` exercises one flag, not two things."""
        identifiers = extracted(dogfood_steps, declared)
        for value in ("unused.yaml", "../etc/passwd", "some-change-id"):
            assert not [i for i in identifiers if value in i]

    def test_an_uncontracted_flag_is_not_recorded(
        self, dogfood_steps: list[ActionStep], declared: set[str]
    ) -> None:
        """``--help`` is argparse's, not the application's, and is not contracted.

        Emitting it would put an identifier in the tested set that the declared
        surface can never contain, which is the vocabulary mismatch this task
        exists to close — in the opposite direction.
        """
        assert "cli:--help" not in extracted(dogfood_steps, declared)


# ---------------------------------------------------------------------------
# Shape of the extraction
# ---------------------------------------------------------------------------


class TestExtractionShape:
    def test_a_subcommand_and_its_flag_are_both_recorded(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", args=["lock", "acquire", "--ttl", "5"])]
        units = {"cli:lock acquire", "cli:lock acquire --ttl"}
        assert set(extracted(steps, units)) == units

    def test_an_inline_flag_value_is_split_on_the_equals_sign(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", args=["--fail-threshold=0.5"])]
        assert extracted(steps, {"cli:--fail-threshold"}) == ["cli:--fail-threshold"]

    def test_a_short_flag_is_recorded(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", args=["-v"])]
        assert extracted(steps, {"cli:-v"}) == ["cli:-v"]

    def test_a_negative_number_is_a_value_not_a_flag(self) -> None:
        """``-1`` starts with a dash and is not an interface."""
        steps = [ActionStep(id="s1", transport="cli", args=["--offset", "-1"])]
        assert extracted(steps, {"cli:--offset"}) == ["cli:--offset"]

    def test_the_command_form_yields_the_same_identifiers_as_the_args_form(self) -> None:
        """Two spellings of one invocation must not measure differently."""
        units = {"cli:lock acquire", "cli:lock acquire --ttl"}
        as_command = [ActionStep(id="s1", transport="cli", command="lock acquire --ttl 5")]
        as_args = [ActionStep(id="s2", transport="cli", args=["lock", "acquire", "--ttl", "5"])]
        assert extracted(as_command, units) == extracted(as_args, units)

    def test_identifiers_are_deduplicated_across_steps(self, declared: set[str]) -> None:
        steps = [
            ActionStep(id="s1", transport="cli", args=["--descriptor", "a.yaml"]),
            ActionStep(id="s2", transport="cli", args=["--descriptor", "b.yaml"]),
        ]
        assert extracted(steps, declared) == ["cli:--descriptor"]


# ---------------------------------------------------------------------------
# Safe default, and the surfaces that already matched
# ---------------------------------------------------------------------------


class TestDeclaredSurfaceIsRequiredToNameFlags:
    """Rule 4 — the new parameter defaults to today's behaviour.

    With no declared surface there is nothing for a flag identifier to match,
    so emitting one produces a key that no coverage computation can ever use.
    The filter is not a convenience: it is the reason the emitted vocabulary
    is guaranteed to be a subset of the declared one.
    """

    def test_without_a_declared_surface_the_legacy_command_identifier_is_unchanged(
        self,
    ) -> None:
        steps = [ActionStep(id="s1", transport="cli", command="lock status --file-path x")]
        assert Evaluator._extract_interfaces(steps) == ["cli:lock status"]

    def test_without_a_declared_surface_no_flag_identifiers_are_emitted(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", args=["--descriptor", "x.yaml"])]
        assert Evaluator._extract_interfaces(steps) == []

    def test_a_flag_absent_from_the_declared_surface_is_not_emitted(self) -> None:
        steps = [ActionStep(id="s1", transport="cli", args=["--invented"])]
        assert extracted(steps, {"cli:--descriptor"}) == []


class TestOtherTransportsAlreadyShareTheVocabulary:
    """Regression guard. HTTP and MCP steps already emit declared elements.

    The service archetype's declared elements are ``"METHOD /path"`` and
    ``"mcp:<tool>"`` — the same strings extraction has always produced — so
    D10 is already satisfied there and this change must not disturb it.
    """

    def test_an_http_step_emits_the_declared_element(self) -> None:
        steps = [ActionStep(id="s1", transport="http", method="POST", endpoint="/locks/acquire")]
        assert extracted(steps, {"POST /locks/acquire"}) == ["POST /locks/acquire"]

    def test_an_mcp_step_emits_the_bound_element(self) -> None:
        """Two operations bind to ``check_locks``; the tool is what was tested."""
        steps: list[ActionStep] = [ActionStep(id="s1", transport="mcp", tool="check_locks")]
        assert extracted(steps, {"mcp:check_locks"}) == ["mcp:check_locks"]

    def test_http_and_mcp_are_not_filtered_by_the_declared_surface(self) -> None:
        """An undeclared endpoint is a finding, not something to drop.

        Only flag identifiers are filtered, because only they are synthesised
        from tokens that may be values. An HTTP path a scenario actually
        called is evidence either way.
        """
        steps = [ActionStep(id="s1", transport="http", method="GET", endpoint="/undocumented")]
        assert extracted(steps, {"POST /locks/acquire"}) == ["GET /undocumented"]


# ---------------------------------------------------------------------------
# The coverage threshold (task 3.7)
# ---------------------------------------------------------------------------


def report_with(pass_rate: float, coverage_pct: float, total: int = 4) -> GenEvalReport:
    """A report carrying only the two numbers the exit gate reads."""
    return GenEvalReport(
        total_scenarios=total,
        passed=total,
        failed=0,
        errors=0,
        skipped=0,
        pass_rate=pass_rate,
        coverage_pct=coverage_pct,
        duration_seconds=1.0,
        budget_exhausted=False,
        verdicts=[],
        per_interface={},
        per_category={},
        unevaluated_interfaces=[],
        cost_summary={},
        iterations_completed=1,
    )


class TestMinCoverageGate:
    """D10 — a coverage floor that fails a run on its own.

    Today ``__main__`` exits on ``report.pass_rate`` alone, and ``make
    dogfood`` passes ``--fail-threshold 1.0``, which is a pass rate. The spec's
    coverage floor therefore has no enforcement mechanism at all: a suite that
    exercises one flag out of sixteen and passes exits 0.

    The two gates are independent by construction. A pass rate says the
    scenarios that ran got the right answers; coverage says how much of the
    declared surface ran at all. A suite can be perfect at one and empty at the
    other, which is precisely the vacuous-success shape the dogfood exists to
    catch.
    """

    def test_coverage_below_the_threshold_fails_a_fully_passing_run(self) -> None:
        """The headline claim. Pass rate 100%, coverage 30%, exit 1."""
        code, _ = exit_decision(report_with(1.0, 30.0), fail_threshold=0.95, min_coverage=80.0)
        assert code == 1

    def test_the_failure_names_coverage_rather_than_the_pass_rate(self) -> None:
        """An operator reading `FAIL (100.0% < 95.0%)` would chase the wrong gate."""
        _, message = exit_decision(report_with(1.0, 30.0), fail_threshold=0.95, min_coverage=80.0)
        assert "coverage" in message.lower()

    def test_coverage_exactly_at_the_threshold_passes(self) -> None:
        code, _ = exit_decision(report_with(1.0, 80.0), fail_threshold=0.95, min_coverage=80.0)
        assert code == 0

    def test_coverage_above_the_threshold_passes(self) -> None:
        code, _ = exit_decision(report_with(1.0, 95.0), fail_threshold=0.95, min_coverage=80.0)
        assert code == 0

    def test_the_pass_rate_gate_still_fails_on_its_own(self) -> None:
        """Negative control in the other direction: coverage complete, answers wrong."""
        code, message = exit_decision(
            report_with(0.5, 100.0), fail_threshold=0.95, min_coverage=80.0
        )
        assert code == 1
        assert "pass rate" in message.lower()

    def test_both_gates_failing_reports_both(self) -> None:
        """Fixing the one named is not enough; the operator needs both."""
        _, message = exit_decision(report_with(0.5, 30.0), fail_threshold=0.95, min_coverage=80.0)
        assert "coverage" in message.lower()
        assert "pass rate" in message.lower()

    def test_a_zero_scenario_run_still_fails_regardless(self) -> None:
        """UP-3's guard survives. Vacuous success is not reachable through it."""
        code, message = exit_decision(
            report_with(0.0, 100.0, total=0), fail_threshold=0.0, min_coverage=0.0
        )
        assert code == 1
        assert "no scenarios" in message.lower()

    def test_the_default_threshold_gates_nothing(self) -> None:
        """Rule 4 — a run that passes today must keep passing.

        gen-eval's own dogfood reports 0% coverage on the branch before task
        5.3 lands. A default floor above zero would fail every consumer's
        existing pipeline the moment they upgraded.
        """
        code, _ = exit_decision(
            report_with(1.0, 0.0), fail_threshold=0.95, min_coverage=DEFAULT_MIN_COVERAGE
        )
        assert code == 0

    def test_the_default_is_zero(self) -> None:
        assert DEFAULT_MIN_COVERAGE == 0.0


class TestMinCoverageFlag:
    def test_the_flag_is_accepted_and_parsed_as_a_percentage(self) -> None:
        args = parse_args(["--descriptor", "d.yaml", "--min-coverage", "80"])
        assert args.min_coverage == 80.0

    def test_the_flag_defaults_to_the_no_op_threshold(self) -> None:
        args = parse_args(["--descriptor", "d.yaml"])
        assert args.min_coverage == DEFAULT_MIN_COVERAGE

    @pytest.mark.parametrize("value", ["101", "-1"])
    def test_a_value_outside_the_percentage_range_is_a_usage_error(self, value: str) -> None:
        """The flag is a percentage, not a rate. Out-of-range is caught loudly.

        The other confusion — ``--min-coverage 0.8`` meaning 80% — is caught
        separately, because it fails *open*. See
        ``tests/test_min_coverage_units.py`` (task 4.19).
        """
        with pytest.raises(SystemExit):
            parse_args(["--descriptor", "d.yaml", "--min-coverage", value])

    def test_the_flag_is_declared_in_the_cli_contract(self, declared: set[str]) -> None:
        """A flag argparse accepts and the contract omits is undocumented surface."""
        assert "cli:--min-coverage" in declared
