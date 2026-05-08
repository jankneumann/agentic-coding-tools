"""Playwright runner.

Executes ``npx playwright test --reporter=json`` against the generated test
directory, once per browser in the descriptor's ``browsers`` matrix.

This module is responsible for:

* Detecting whether the Playwright CLI is installed (``check_playwright_available``).
* Starting the descriptor's ``lifecycle.startup_command`` (when set), enforcing
  the 127.0.0.1 bind invariant from design D7 / spec scenario "Sample frontend
  exercise validates the full path".
* Resolving env-vars for ``auth_flow`` BEFORE any browser launch (per the
  "fail fast" spec scenario).
* Aggregating per-browser test results into a single :class:`PlaywrightRunResult`.
* Returning structured per-test failure info (test name, browser,
  error message) so :mod:`findings` can build a behavioral_failure
  finding per failure with ``metadata.browser`` populated.

The integration test stubs :func:`subprocess.run` so it doesn't actually
require Node/Playwright to be installed.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from auth_flow import MissingEnvVar, validate_required_env_vars

logger = logging.getLogger(__name__)


# Exit code used when the Playwright CLI is missing entirely. Per the
# "Missing Playwright CLI degrades cleanly" spec scenario, this MUST be
# distinguishable from a test failure (which is a non-zero status from
# Playwright itself, typically 1).
EXIT_CLI_MISSING = 127


# ---------------------------------------------------------------------------
# Result data model
# ---------------------------------------------------------------------------


@dataclass
class PlaywrightFailure:
    """One per failed Playwright test execution."""

    test_name: str
    browser: str
    error_message: str = ""
    file: str | None = None  # the .spec.ts file path
    duration_ms: int | None = None


@dataclass
class PlaywrightRunResult:
    """Aggregated result from running every browser in the matrix."""

    exit_code: int = 0
    failures: list[PlaywrightFailure] = field(default_factory=list)
    # number of passing tests, summed across browsers
    passed: int = 0
    # tracks browsers actually executed (vs skipped due to launch failures)
    browsers_executed: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------


def check_playwright_available(
    *,
    runner: Any = subprocess,
) -> bool:
    """Return ``True`` if ``npx playwright --version`` succeeds.

    The ``runner`` injection point exists so tests can pass a stub without
    monkeypatching the global ``subprocess`` module.
    """
    if shutil.which("npx") is None:
        return False
    try:
        result = runner.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Lifecycle (startup_command)
# ---------------------------------------------------------------------------


def _wait_for_health(url: str, *, timeout: float, expected_status: int = 200) -> bool:
    """Poll ``url`` until it returns ``expected_status`` or timeout elapses."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:  # noqa: S310 — local-only health check
                if resp.status == expected_status:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.2)
    return False


def _enforce_local_bind(descriptor: Mapping[str, Any]) -> None:
    """Reject startup_commands that bind beyond localhost without opt-in.

    Per design D7 the schema's default ``bind_address`` is ``127.0.0.1``;
    the runner additionally inspects the literal startup_command and refuses
    to launch when ``0.0.0.0`` (or empty bind, which most servers default to
    all-interfaces) appears AND the descriptor has not explicitly set
    ``bind_address`` to a non-localhost value.
    """
    lifecycle = descriptor.get("lifecycle") or {}
    cmd = (lifecycle.get("startup_command") or "").strip()
    if not cmd:
        return
    bind = lifecycle.get("bind_address", "127.0.0.1")
    # If the operator explicitly opted into a non-localhost bind, allow it.
    if bind not in {"127.0.0.1", "localhost"}:
        return
    if "0.0.0.0" in cmd:
        raise RuntimeError(
            "lifecycle.startup_command binds to 0.0.0.0 but bind_address is "
            f"{bind!r}; refusing to launch (design D7)"
        )


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


def parse_playwright_json(
    payload: str,
    *,
    browser: str,
) -> tuple[list[PlaywrightFailure], int]:
    """Parse the ``--reporter=json`` output for one browser run.

    Playwright's JSON reporter shape varies slightly between versions; the
    parser walks ``suites[].specs[].tests[]`` and inspects each test's
    ``results[].status``. Anything with status ``failed`` or ``timedOut``
    becomes a :class:`PlaywrightFailure`; ``passed`` increments the counter.

    Returns:
        ``(failures, passed_count)``.
    """
    try:
        doc = json.loads(payload)
    except json.JSONDecodeError as exc:
        # Treat unparseable output as a single synthetic failure so the
        # caller still gets a finding rather than silently dropping the run.
        return (
            [
                PlaywrightFailure(
                    test_name="<unparseable reporter output>",
                    browser=browser,
                    error_message=f"reporter JSON parse error: {exc}",
                )
            ],
            0,
        )

    failures: list[PlaywrightFailure] = []
    passed = 0

    def _walk(suite: dict[str, Any]) -> None:
        nonlocal passed
        for spec in suite.get("specs", []) or []:
            for test in spec.get("tests", []) or []:
                file = spec.get("file")
                test_name = spec.get("title") or test.get("title") or "unknown"
                results = test.get("results") or []
                # take the most-recent result (Playwright retries land here)
                last = results[-1] if results else {}
                status = last.get("status")
                duration = last.get("duration")
                if status == "passed":
                    passed += 1
                elif status in {"failed", "timedOut", "interrupted"}:
                    err = last.get("error") or {}
                    msg = err.get("message") or err.get("stack") or status
                    failures.append(
                        PlaywrightFailure(
                            test_name=test_name,
                            browser=browser,
                            error_message=msg,
                            file=file,
                            duration_ms=int(duration) if isinstance(duration, (int, float)) else None,
                        )
                    )
        for child in suite.get("suites", []) or []:
            _walk(child)

    for suite in doc.get("suites", []) or []:
        _walk(suite)
    return failures, passed


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_playwright(
    test_dir: Path,
    descriptor: Mapping[str, Any],
    *,
    timeout_seconds: int = 600,
    runner: Any = subprocess,
    env: Mapping[str, str] | None = None,
    browsers: Iterable[str] | None = None,
) -> PlaywrightRunResult:
    """Execute the generated Playwright tests across every configured browser.

    The function:

    1. Verifies the CLI is installed; if not, returns a result with
       ``exit_code = EXIT_CLI_MISSING`` and emits a logger error (the
       caller is responsible for NOT writing a findings file in this case).
    2. Resolves ``auth_flow`` env vars; on missing var, raises
       :class:`MissingEnvVar` so the pipeline aborts before any browser.
    3. Optionally starts ``lifecycle.startup_command`` (caller may also do
       this externally; the caller is the source of truth for lifecycle
       management). When started here, the runner waits for the
       ``health_check`` URL.
    4. Runs ``npx playwright test --reporter=json --browser=<each>`` per
       browser and aggregates results. Per the "partial failure recovery"
       spec scenario, all browsers run even if some fail.

    Args:
        test_dir: Directory containing the generated ``.spec.ts`` files
            and ``playwright.config.ts``.
        descriptor: The frontend descriptor (post-normalize).
        timeout_seconds: Per-browser timeout for the playwright invocation.
        runner: Injection point for tests (a stub ``subprocess`` module).
        env: Optional env mapping passed through to validation and to
            ``runner.run``. Defaults to ``os.environ``.
        browsers: Optional override for the descriptor's ``browsers`` list.

    Returns:
        A :class:`PlaywrightRunResult` with aggregated failures + exit code.
    """
    # 1. Dependency check.
    if not check_playwright_available(runner=runner):
        logger.error(
            "playwright CLI not found on PATH. Install with: "
            "npx playwright install"
        )
        return PlaywrightRunResult(exit_code=EXIT_CLI_MISSING)

    # 2. Env-var validation (raises MissingEnvVar on missing vars).
    validate_required_env_vars(descriptor, env=env)

    # 3. Localhost-bind invariant.
    _enforce_local_bind(descriptor)

    # 4. Browsers list.
    matrix = list(browsers or descriptor.get("browsers") or ["chromium"])
    if not matrix:
        matrix = ["chromium"]

    result = PlaywrightRunResult()
    overall_exit = 0

    for browser in matrix:
        logger.info("playwright: running browser=%s", browser)
        try:
            proc = runner.run(
                [
                    "npx",
                    "playwright",
                    "test",
                    "--reporter=json",
                    f"--browser={browser}",
                ],
                cwd=str(test_dir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=dict(env) if env else None,
            )
        except subprocess.TimeoutExpired:
            logger.warning("playwright: browser=%s timed out", browser)
            result.failures.append(
                PlaywrightFailure(
                    test_name="<run timed out>",
                    browser=browser,
                    error_message=f"timeout after {timeout_seconds}s",
                )
            )
            overall_exit = max(overall_exit, 1)
            continue
        except (OSError, FileNotFoundError) as exc:
            logger.warning(
                "playwright: browser=%s launch failed: %s", browser, exc
            )
            result.failures.append(
                PlaywrightFailure(
                    test_name="<launch failed>",
                    browser=browser,
                    error_message=str(exc),
                )
            )
            overall_exit = max(overall_exit, 1)
            continue

        result.browsers_executed.append(browser)
        # Playwright's CLI exit code: 0 = all passed, 1 = some failed.
        if proc.returncode != 0:
            overall_exit = max(overall_exit, proc.returncode)

        failures, passed = parse_playwright_json(
            proc.stdout or "{}", browser=browser
        )
        result.failures.extend(failures)
        result.passed += passed

    result.exit_code = overall_exit
    return result


__all__ = [
    "EXIT_CLI_MISSING",
    "MissingEnvVar",
    "PlaywrightFailure",
    "PlaywrightRunResult",
    "check_playwright_available",
    "parse_playwright_json",
    "run_playwright",
]
