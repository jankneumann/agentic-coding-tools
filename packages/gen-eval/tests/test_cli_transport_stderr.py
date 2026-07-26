"""stderr is data, not a failure signal (UP-5).

Found by dogfooding: three scenarios in ``evaluation/scenarios/`` asserting
CLI failure paths (exit 2, 64, 1) were all classified ``error`` despite
producing exactly the expected exit codes.

Cause: ``CliClient`` assigned stderr to ``StepResult.error``, and
``Evaluator._execute_step`` short-circuits to ``status="error"`` on any
``result.error`` *before* comparing expectations. Any CLI that writes
diagnostics to stderr — which is every well-behaved CLI on a failure path —
was an unconditional error regardless of exit code.

The consequence was that ``ExpectBlock.exit_code`` could not assert a
non-zero exit, and ``ExpectBlock.error_contains`` was unreachable on the CLI
transport. Both fields exist specifically to assert failures.

``error`` is now reserved for the case where the command could not be run.
"""

from __future__ import annotations

import sys

from gen_eval.clients.base import StepContext
from gen_eval.clients.cli_client import CliClient
from gen_eval.models import ActionStep, ExpectBlock


def _context() -> StepContext:
    return StepContext(variables={}, timeout_seconds=30)


def _step(step_id: str, args: list[str]) -> ActionStep:
    return ActionStep(id=step_id, transport="cli", args=args)


class TestStderrIsNotATransportError:
    async def test_stderr_does_not_set_error(self) -> None:
        client = CliClient(command=sys.executable)
        result = await client.execute(
            _step("warn", ["-c", "import sys; sys.stderr.write('a warning\\n')"]),
            _context(),
        )
        assert result.error is None, (
            "stderr must not be reported as a transport error — the process ran"
        )
        assert result.exit_code == 0

    async def test_stderr_is_surfaced_in_the_body(self) -> None:
        """It must stay assertable, just not fatal."""
        client = CliClient(command=sys.executable)
        result = await client.execute(
            _step("warn", ["-c", "import sys; sys.stderr.write('deprecated flag\\n')"]),
            _context(),
        )
        assert result.body["stderr"] == "deprecated flag"

    async def test_no_stderr_key_when_stderr_is_empty(self) -> None:
        client = CliClient(command=sys.executable)
        result = await client.execute(
            _step("quiet", ["-c", "print('ok')"]), _context()
        )
        assert "stderr" not in result.body

    async def test_nonzero_exit_with_stderr_reports_the_exit_code(self) -> None:
        """The case the dogfood suite could not express.

        A CLI that fails *and* explains itself on stderr — the normal shape of
        a usage error — must still report its exit code for assertion.
        """
        client = CliClient(command=sys.executable)
        result = await client.execute(
            _step(
                "usage-error",
                ["-c", "import sys; sys.stderr.write('bad usage\\n'); sys.exit(64)"],
            ),
            _context(),
        )
        assert result.error is None
        assert result.exit_code == 64
        assert result.body["stderr"] == "bad usage"

    async def test_unrunnable_command_still_sets_error(self) -> None:
        """Negative control: a genuine transport failure must still be an error."""
        client = CliClient(command="definitely-not-a-real-binary-xyz")
        result = await client.execute(_step("missing", []), _context())
        assert result.error is not None
        assert result.exit_code is None


class TestExpectationsReachableOnCliTransport:
    """End-to-end: the evaluator must now compare rather than short-circuit."""

    async def test_exit_code_expectation_passes_despite_stderr(self) -> None:
        from gen_eval.clients.base import TransportClientRegistry
        from gen_eval.descriptor import InterfaceDescriptor, ServiceDescriptor
        from gen_eval.evaluator import Evaluator
        from gen_eval.models import Scenario

        registry = TransportClientRegistry()
        registry.register("cli", CliClient(command=sys.executable))
        descriptor = InterfaceDescriptor(
            project="p",
            version="1",
            services=[ServiceDescriptor(name="c", type="cli", command=sys.executable)],
        )
        evaluator = Evaluator(descriptor, registry)

        step = _step(
            "fails-loudly",
            ["-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(64)"],
        )
        step.expect = ExpectBlock(exit_code=64, error_contains="boom")

        verdict = await evaluator.evaluate(
            Scenario(
                id="s",
                name="cli failure path",
                description="asserts a non-zero exit and its stderr text",
                category="cli",
                interfaces=["cli:python"],
                steps=[step],
            )
        )
        assert verdict.status == "pass", (
            f"expected pass, got {verdict.status}: {verdict.failure_summary}"
        )
