"""Tests for skills/playwright-validator/scripts/runner.py.

Stubs subprocess.run so the tests do not depend on a real Playwright CLI.
"""

from __future__ import annotations

import json
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest

from auth_flow import MissingEnvVar
from runner import (
    EXIT_CLI_MISSING,
    PlaywrightFailure,
    PlaywrightRunResult,
    _enforce_local_bind,
    check_playwright_available,
    parse_playwright_json,
    run_playwright,
)


# ---------------------------------------------------------------------------
# Stub subprocess module
# ---------------------------------------------------------------------------


class _StubResult:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _make_runner_stub(behavior: dict[str, Any]) -> types.SimpleNamespace:
    """Build a stand-in for the ``subprocess`` module.

    ``behavior`` keys:
      - ``version_returncode``: int (default 0). What ``npx playwright --version`` returns.
      - ``test_results``: dict[str, dict] mapping browser -> {stdout, returncode}.
      - ``raise_for_browser``: dict[str, Exception] mapping browser -> exception to raise.
    """
    calls: list[list[str]] = []

    def run(  # noqa: PLR0913 — mirrors subprocess.run's signature
        cmd: list[str],
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        check: bool = False,
        cwd: str | None = None,
        env: Any = None,
    ) -> _StubResult:
        calls.append(list(cmd))
        # version probe
        if len(cmd) >= 3 and cmd[1] == "playwright" and cmd[2] == "--version":
            return _StubResult(
                stdout="1.40.0\n",
                returncode=behavior.get("version_returncode", 0),
            )
        # test invocation
        if len(cmd) >= 3 and cmd[1] == "playwright" and cmd[2] == "test":
            browser = "chromium"
            for arg in cmd:
                if arg.startswith("--browser="):
                    browser = arg.split("=", 1)[1]
            if behavior.get("raise_for_browser", {}).get(browser):
                raise behavior["raise_for_browser"][browser]
            res = behavior.get("test_results", {}).get(browser, {})
            return _StubResult(
                stdout=res.get("stdout", "{}"),
                returncode=res.get("returncode", 0),
            )
        return _StubResult(stdout="", returncode=0)

    stub = types.SimpleNamespace(
        run=run,
        TimeoutExpired=subprocess.TimeoutExpired,
        SubprocessError=subprocess.SubprocessError,
        calls=calls,
    )
    return stub


def _make_descriptor(**overrides: Any) -> dict[str, Any]:
    base = {
        "base_url": "http://127.0.0.1:8765",
        "browsers": ["chromium"],
        "selectors": {"x": "#x"},
        "lifecycle": {
            "startup_command": "python -m http.server 8765 --bind 127.0.0.1",
            "bind_address": "127.0.0.1",
        },
        "auth_flow": [],
        "env_vars_required": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# parse_playwright_json
# ---------------------------------------------------------------------------


def test_parse_passes_and_failures():
    payload = json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {
                            "title": "passing test",
                            "file": "x.spec.ts",
                            "tests": [
                                {"results": [{"status": "passed", "duration": 12}]}
                            ],
                        },
                        {
                            "title": "failing test",
                            "file": "x.spec.ts",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed",
                                            "duration": 5,
                                            "error": {"message": "boom"},
                                        }
                                    ]
                                }
                            ],
                        },
                    ]
                }
            ]
        }
    )
    failures, passed = parse_playwright_json(payload, browser="chromium")
    assert passed == 1
    assert len(failures) == 1
    assert failures[0].test_name == "failing test"
    assert failures[0].browser == "chromium"
    assert failures[0].error_message == "boom"


def test_parse_unparseable_yields_synthetic_failure():
    failures, passed = parse_playwright_json("not json", browser="firefox")
    assert passed == 0
    assert len(failures) == 1
    assert failures[0].browser == "firefox"
    assert "parse error" in failures[0].error_message


# ---------------------------------------------------------------------------
# check_playwright_available
# ---------------------------------------------------------------------------


def test_check_returns_true_when_version_succeeds(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr("runner.shutil.which", lambda _: "/usr/bin/npx")
    stub = _make_runner_stub({"version_returncode": 0})
    assert check_playwright_available(runner=stub) is True


def test_check_returns_false_when_no_npx(monkeypatch):
    monkeypatch.setattr("runner.shutil.which", lambda _: None)
    stub = _make_runner_stub({})
    assert check_playwright_available(runner=stub) is False


# ---------------------------------------------------------------------------
# run_playwright — happy path
# ---------------------------------------------------------------------------


def test_run_playwright_aggregates_per_browser(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("runner.shutil.which", lambda _: "/usr/bin/npx")
    pass_payload = json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {
                            "title": "t1",
                            "file": "x.spec.ts",
                            "tests": [{"results": [{"status": "passed"}]}],
                        }
                    ]
                }
            ]
        }
    )
    fail_payload = json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {
                            "title": "t2",
                            "file": "x.spec.ts",
                            "tests": [
                                {
                                    "results": [
                                        {"status": "failed", "error": {"message": "boom"}}
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    )
    stub = _make_runner_stub(
        {
            "test_results": {
                "chromium": {"stdout": pass_payload, "returncode": 0},
                "firefox": {"stdout": fail_payload, "returncode": 1},
            }
        }
    )
    descriptor = _make_descriptor(browsers=["chromium", "firefox"])
    result = run_playwright(tmp_path, descriptor, runner=stub)
    assert isinstance(result, PlaywrightRunResult)
    assert result.exit_code == 1
    assert result.passed == 1
    assert len(result.failures) == 1
    assert result.failures[0].browser == "firefox"
    assert result.browsers_executed == ["chromium", "firefox"]
    # Verify the constructed CLI args.
    test_calls = [c for c in stub.calls if "test" in c]
    assert len(test_calls) == 2
    assert any("--browser=chromium" in c for c in test_calls)
    assert any("--browser=firefox" in c for c in test_calls)
    assert all("--reporter=json" in c for c in test_calls)


def test_run_playwright_partial_failure_completes_all_browsers(tmp_path: Path, monkeypatch):
    """Per spec scenario 'Playwright pipeline partial failure recovery'."""
    monkeypatch.setattr("runner.shutil.which", lambda _: "/usr/bin/npx")
    fail_payload = json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {
                            "title": f"t{i}",
                            "file": "x.spec.ts",
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed" if i < 3 else "passed",
                                            "error": {"message": "boom"} if i < 3 else None,
                                        }
                                    ]
                                }
                            ],
                        }
                        for i in range(5)
                    ]
                }
            ]
        }
    )
    stub = _make_runner_stub(
        {
            "test_results": {
                "chromium": {"stdout": fail_payload, "returncode": 1},
                "firefox": {"stdout": fail_payload, "returncode": 1},
            }
        }
    )
    descriptor = _make_descriptor(browsers=["chromium", "firefox"])
    result = run_playwright(tmp_path, descriptor, runner=stub)
    assert result.exit_code == 1
    # 3 failures per browser × 2 browsers = 6 failures; 2 browsers × 2 passes = 4 passed.
    assert len(result.failures) == 6
    assert result.passed == 4
    # Every finding should have its browser tagged.
    browsers = {f.browser for f in result.failures}
    assert browsers == {"chromium", "firefox"}


# ---------------------------------------------------------------------------
# run_playwright — degraded paths
# ---------------------------------------------------------------------------


def test_run_playwright_missing_cli_returns_exit_127(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("runner.shutil.which", lambda _: None)
    stub = _make_runner_stub({})
    descriptor = _make_descriptor()
    result = run_playwright(tmp_path, descriptor, runner=stub)
    assert result.exit_code == EXIT_CLI_MISSING
    # No browsers should have been invoked.
    assert result.browsers_executed == []
    test_calls = [c for c in stub.calls if "test" in c]
    assert test_calls == []


def test_run_playwright_missing_env_var_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("runner.shutil.which", lambda _: "/usr/bin/npx")
    stub = _make_runner_stub({"version_returncode": 0})
    descriptor = _make_descriptor(
        env_vars_required=["MISSING_VAR"],
        auth_flow=[],
    )
    with pytest.raises(MissingEnvVar) as exc:
        run_playwright(tmp_path, descriptor, runner=stub, env={})
    assert exc.value.var_name == "MISSING_VAR"
    # And no browser invocations occurred (fail-fast invariant).
    test_calls = [c for c in stub.calls if "test" in c]
    assert test_calls == []


def test_run_playwright_missing_auth_flow_var_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("runner.shutil.which", lambda _: "/usr/bin/npx")
    stub = _make_runner_stub({"version_returncode": 0})
    descriptor = _make_descriptor(
        auth_flow=[{"action": "fill", "selector": "#u", "value": "${MISSING_VAR}"}],
    )
    with pytest.raises(MissingEnvVar):
        run_playwright(tmp_path, descriptor, runner=stub, env={})


def test_run_playwright_browser_launch_failure_continues(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("runner.shutil.which", lambda _: "/usr/bin/npx")
    pass_payload = json.dumps({"suites": []})
    stub = _make_runner_stub(
        {
            "test_results": {"firefox": {"stdout": pass_payload, "returncode": 0}},
            "raise_for_browser": {"chromium": OSError("browser binary not installed")},
        }
    )
    descriptor = _make_descriptor(browsers=["chromium", "firefox"])
    result = run_playwright(tmp_path, descriptor, runner=stub)
    assert result.exit_code == 1  # chromium failed
    # firefox executed, chromium did not appear in browsers_executed
    assert "firefox" in result.browsers_executed
    assert "chromium" not in result.browsers_executed
    # The chromium launch failure surfaced as a finding.
    chromium_failures = [f for f in result.failures if f.browser == "chromium"]
    assert len(chromium_failures) == 1
    assert "<launch failed>" in chromium_failures[0].test_name


def test_enforce_local_bind_rejects_zero_zero_zero_zero():
    descriptor = {
        "lifecycle": {
            "startup_command": "python -m http.server 8000 --bind 0.0.0.0",
            "bind_address": "127.0.0.1",
        }
    }
    with pytest.raises(RuntimeError) as exc:
        _enforce_local_bind(descriptor)
    assert "0.0.0.0" in str(exc.value)


def test_enforce_local_bind_allows_explicit_opt_in():
    descriptor = {
        "lifecycle": {
            "startup_command": "python -m http.server 8000 --bind 0.0.0.0",
            "bind_address": "10.0.0.1",
        }
    }
    # Should NOT raise — operator opted in explicitly.
    _enforce_local_bind(descriptor)
