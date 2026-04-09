"""Client for the refresh-architecture RPC service (wp-integration task 5.8a).

Wraps the three RPC methods defined in
``contracts/internal/refresh-architecture-rpc.yaml``:

- ``is_graph_stale(max_age_hours=6)`` — non-blocking freshness probe
- ``trigger_refresh(reason, caller)`` — idempotent spawn
- ``get_refresh_status(refresh_id)`` — poll by refresh_id

Transport is subprocess-style: the client shells out to
``python3 -m rpc_server <method> <json_args>`` and parses the JSON result
printed to stdout. This matches the server's CLI entrypoint in
``skills/refresh-architecture/scripts/rpc_server.py``.

## Failure-mode contract

Per the RPC contract (section "Failure modes"), this client NEVER raises on
transport errors. Instead, each method returns a :class:`RefreshClientUnavailable`
sentinel with a human-readable reason. Callers (``compose_train``) MUST treat
this as a signal to fall back to the "full test suite" path. The coordinator
MUST NOT block merge-train progress on refresh-architecture availability.

Callable results:

- Success → ``dict[str, Any]`` matching the contract's output shape
- Failure → :class:`RefreshClientUnavailable` instance (``not isinstance(..., dict)``)

## Timeouts

Per-method timeouts enforce the contract's non-blocking guarantee:

- ``is_graph_stale`` — 30s (reads file mtime + light JSON parse)
- ``trigger_refresh`` — 10s (spawns subprocess, returns immediately)
- ``get_refresh_status`` — 5s (reads in-memory state)

A timeout is indistinguishable from "subprocess alive but stuck" from the
coordinator's perspective — both degrade to the full-suite fallback.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshClientUnavailable:
    """Sentinel returned when the RPC subsystem is unreachable.

    Callers MUST check ``isinstance(result, RefreshClientUnavailable)`` before
    treating the result as a success dict. Per the contract, this is the ONLY
    failure signal — the client never raises on transport errors.
    """

    reason: str

    def __repr__(self) -> str:
        return f"RefreshClientUnavailable(reason={self.reason!r})"


# ---------------------------------------------------------------------------
# Runner protocol
# ---------------------------------------------------------------------------


class _Runner(Protocol):
    """Callable matching ``subprocess.run``'s signature used by this client.

    Parameterized as a protocol so tests can inject a fake without monkeypatching
    ``subprocess.run`` globally.
    """

    def __call__(
        self,
        cmd: list[str],
        *,
        timeout: float,
        capture_output: bool = True,
        text: bool = True,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]: ...


Runner = Callable[..., subprocess.CompletedProcess[str]]


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


#: Per-method timeouts in seconds, per the RPC contract.
DEFAULT_METHOD_TIMEOUTS: dict[str, float] = {
    "is_graph_stale": 30.0,
    "trigger_refresh": 10.0,
    "get_refresh_status": 5.0,
}

#: Connection timeout kept for future transports (socket-based, HTTP).
#: The subprocess transport has no connect phase, so this is currently unused
#: but declared to satisfy the contract.
DEFAULT_CONNECTION_TIMEOUT_S: float = 5.0

DEFAULT_RPC_MODULE = "rpc_server"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class RefreshRpcClient:
    """Failure-tolerant client for the refresh-architecture RPC service.

    All three methods follow the same pattern:
        1. Serialize kwargs to JSON
        2. Spawn ``python3 -m <rpc_module> <method> <json>`` via the runner
        3. On any transport error → return RefreshClientUnavailable
        4. On success → parse stdout JSON and return the dict
    """

    def __init__(
        self,
        runner: Runner | None = None,
        rpc_module: str = DEFAULT_RPC_MODULE,
        python_executable: str = "python3",
        timeouts: dict[str, float] | None = None,
    ) -> None:
        self._runner: Runner = runner or subprocess.run
        self._rpc_module = rpc_module
        self._python_executable = python_executable
        self._timeouts = dict(DEFAULT_METHOD_TIMEOUTS)
        if timeouts:
            self._timeouts.update(timeouts)

    # ---- public methods ----

    def is_graph_stale(
        self,
        max_age_hours: int | None = None,
    ) -> dict[str, Any] | RefreshClientUnavailable:
        """Check whether the architecture graph is older than ``max_age_hours``.

        Non-blocking: returns immediately from the graph file mtime on the
        server side.
        """
        kwargs: dict[str, Any] = {}
        if max_age_hours is not None:
            kwargs["max_age_hours"] = max_age_hours
        return self._invoke("is_graph_stale", kwargs)

    def trigger_refresh(
        self,
        reason: str,
        caller: str,
    ) -> dict[str, Any] | RefreshClientUnavailable:
        """Trigger an async graph refresh. Idempotent while one is in flight."""
        return self._invoke(
            "trigger_refresh", {"reason": reason, "caller": caller}
        )

    def get_refresh_status(
        self,
        refresh_id: str,
    ) -> dict[str, Any] | RefreshClientUnavailable:
        """Poll the status of a refresh started via :meth:`trigger_refresh`."""
        return self._invoke("get_refresh_status", {"refresh_id": refresh_id})

    # ---- internal ----

    def _invoke(
        self,
        method: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any] | RefreshClientUnavailable:
        """Run one RPC method, returning a sentinel on any failure."""
        timeout = self._timeouts.get(method, 30.0)
        cmd = [
            self._python_executable,
            "-m",
            self._rpc_module,
            method,
            json.dumps(kwargs),
        ]
        try:
            result = self._runner(
                cmd,
                timeout=timeout,
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "refresh_rpc_client.%s timed out after %ss", method, timeout
            )
            return RefreshClientUnavailable(
                reason=f"subprocess timeout after {timeout}s"
            )
        except FileNotFoundError as exc:
            logger.warning(
                "refresh_rpc_client.%s: python/module not found: %s",
                method,
                exc,
            )
            return RefreshClientUnavailable(reason=f"file not found: {exc}")
        except OSError as exc:  # pragma: no cover — defensive
            logger.warning("refresh_rpc_client.%s OS error: %s", method, exc)
            return RefreshClientUnavailable(reason=f"OS error: {exc}")

        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-200:]
            logger.warning(
                "refresh_rpc_client.%s nonzero exit=%s stderr=%r",
                method,
                result.returncode,
                stderr_tail,
            )
            return RefreshClientUnavailable(
                reason=f"nonzero exit {result.returncode}: {stderr_tail}"
            )

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            logger.warning(
                "refresh_rpc_client.%s failed to parse JSON: %s (stdout=%r)",
                method,
                exc,
                result.stdout[:200],
            )
            return RefreshClientUnavailable(
                reason=f"JSON parse error: {exc}"
            )

        if not isinstance(parsed, dict):
            return RefreshClientUnavailable(
                reason=f"expected dict, got {type(parsed).__name__}"
            )
        return parsed


# ---------------------------------------------------------------------------
# compute_affected_tests (task 5.4)
# ---------------------------------------------------------------------------


#: Resolved default path to ``skills/refresh-architecture/scripts/affected_tests.py``.
#: Computed relative to this module so the monorepo layout stays portable
#: without requiring an env var or config file.
DEFAULT_AFFECTED_TESTS_SCRIPT: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "refresh-architecture"
    / "scripts"
    / "affected_tests.py"
)

#: Timeout for the affected_tests.py shell-out. The BFS walks a modest graph
#: (<10k nodes by construction — see D10) so 30s is a comfortable ceiling
#: that still lets us fall back to the full suite if something goes wrong.
DEFAULT_AFFECTED_TESTS_TIMEOUT_S: float = 30.0


def compute_affected_tests(
    changed_files: list[str],
    *,
    runner: Runner | None = None,
    script_path: Path | str | None = None,
    timeout: float = DEFAULT_AFFECTED_TESTS_TIMEOUT_S,
    python_executable: str = "python3",
) -> list[str] | None:
    """Shell out to ``affected_tests.py`` and parse the returned test list.

    This is the bridge between the merge-train engine (which only knows about
    changed files) and the refresh-architecture graph (which knows which tests
    cover which source nodes). The underlying script is the source of truth —
    we just adapt its CLI output to a Python return value.

    Args:
        changed_files: Repo-relative paths of files that changed in this
            merge-train candidate. An empty list returns ``[]`` immediately
            without invoking the script (argparse would otherwise reject it).
        runner: Injected subprocess runner. Defaults to :func:`subprocess.run`.
            Tests inject a fake to avoid spawning real processes.
        script_path: Override for the affected_tests.py script location.
            Defaults to :data:`DEFAULT_AFFECTED_TESTS_SCRIPT`.
        timeout: Seconds before the subprocess is killed. On timeout we return
            ``None`` (full-suite fallback) — merge-train progress is never
            blocked on this computation.
        python_executable: Python interpreter to invoke. Defaults to
            ``python3``; tests or deployments can override.

    Returns:
        * ``list[str]`` — test file paths covering ``changed_files`` (may be
          empty if the files are uncovered).
        * ``None`` — the graph is missing/stale/bound-exceeded (script printed
          ``ALL``) OR any transport error occurred. Callers MUST run the full
          test suite in this case.

    The failure-mode contract mirrors :class:`RefreshRpcClient`: this function
    NEVER raises on transport errors. Every failure mode degrades to ``None``
    so the merge train can proceed with a conservative full-suite run.
    """
    if not changed_files:
        return []

    _runner: Runner = runner if runner is not None else subprocess.run
    script = Path(script_path) if script_path is not None else DEFAULT_AFFECTED_TESTS_SCRIPT
    cmd: list[str] = [python_executable, str(script), *changed_files]

    try:
        result = _runner(
            cmd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "compute_affected_tests: timed out after %ss — full-suite fallback",
            timeout,
        )
        return None
    except FileNotFoundError as exc:
        logger.warning(
            "compute_affected_tests: script/interpreter not found: %s", exc
        )
        return None
    except OSError as exc:  # pragma: no cover — defensive
        logger.warning("compute_affected_tests: OS error: %s", exc)
        return None

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-200:]
        logger.warning(
            "compute_affected_tests: nonzero exit=%s stderr=%r",
            result.returncode,
            stderr_tail,
        )
        return None

    stdout = (result.stdout or "").strip()
    if stdout == "ALL":
        # Graph stale / missing / traversal-bound exceeded — script is telling
        # us explicitly to run the full suite.
        return None
    if not stdout:
        return []
    return [line for line in stdout.splitlines() if line.strip()]
