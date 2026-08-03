"""``--min-coverage 0.8`` must not silently mean 0.8% (task 4.19).

Spec scenarios:
  - gen-eval-framework.operation-and-surface-coverage-model
      · a coverage floor below the measured coverage fails the run

Design decisions: D10 (coverage vocabulary — including the unit it is
counted in).

Round-7 review, found by two vendors. ``--fail-threshold`` is a rate in
``[0, 1]`` and ``--min-coverage`` is a percent in ``[0, 100]``, so the two
flags read the same digits differently. Someone who writes ``0.8`` for the
second, meaning the same thing ``0.8`` means for the first, gets a legal 0.8%
floor.

The direction is what makes this worth a gate rather than a doc fix. A too-low
floor **passes** — a suite covering 29% of the declared surface satisfies a
0.8% floor and the run exits 0. The operator sees a green build and believes a
coverage gate is enforcing something. That is the failure mode the flag exists
to prevent, reproduced by the flag itself.

The range check already installed catches only the opposite mistake (``800``
for basis points), which fails closed and is therefore the harmless one. So the
protection ran in the direction that did not need it.

``(0, 1)`` is safe to reject because nothing legitimate lives there. Coverage
is denominated in operations, so the smallest non-zero value a run can report
is ``100/N``; a floor under 1% cannot distinguish any two outcomes. Someone who
genuinely wants "any coverage at all" writes ``1``, and someone who wants no
floor writes ``0`` — both still accepted.
"""

from __future__ import annotations

import pytest

from gen_eval.__main__ import DEFAULT_MIN_COVERAGE, parse_args


def parse(value: str) -> float:
    args = parse_args(["--descriptor", "d.yaml", "--min-coverage", value])
    return float(args.min_coverage)


class TestTheAmbiguousBandIsRejected:
    """A value in ``(0, 1)`` is a rate someone typed into a percent flag."""

    @pytest.mark.parametrize("value", ["0.8", "0.5", "0.95", "0.01"])
    def test_a_rate_shaped_value_is_a_usage_error(self, value: str) -> None:
        with pytest.raises(SystemExit):
            parse(value)

    def test_the_message_names_both_readings(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The operator must see which number to type, not just that 0.8 is bad."""
        with pytest.raises(SystemExit):
            parse("0.8")
        message = capsys.readouterr().err
        assert "0.8" in message
        assert "80" in message

    def test_the_message_says_how_to_ask_for_no_floor(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            parse("0.8")
        assert "0" in capsys.readouterr().err


class TestTheBoundariesStayUsable:
    """Rule 4 — every value that had a meaning keeps it."""

    def test_zero_is_still_no_floor(self) -> None:
        assert parse("0") == DEFAULT_MIN_COVERAGE

    def test_one_percent_is_accepted(self) -> None:
        """The nearest legitimate expression of "any coverage at all"."""
        assert parse("1") == 1.0

    def test_a_normal_percentage_is_accepted(self) -> None:
        assert parse("80") == 80.0

    def test_a_fractional_percentage_above_one_is_accepted(self) -> None:
        """``29.4`` is a real coverage reading, not a confused rate."""
        assert parse("29.4") == 29.4

    def test_one_hundred_is_accepted(self) -> None:
        assert parse("100") == 100.0


class TestTheExistingChecksAreIntact:
    """Rule 4 — the range and type checks predate this and must survive."""

    @pytest.mark.parametrize("value", ["101", "-1", "800"])
    def test_an_out_of_range_value_is_still_a_usage_error(self, value: str) -> None:
        with pytest.raises(SystemExit):
            parse(value)

    def test_a_non_numeric_value_is_still_a_usage_error(self) -> None:
        with pytest.raises(SystemExit):
            parse("eighty")

    def test_fail_threshold_is_untouched(self) -> None:
        """It genuinely is a rate; 0.8 there means what the author wrote."""
        args = parse_args(["--descriptor", "d.yaml", "--fail-threshold", "0.8"])
        assert args.fail_threshold == 0.8
