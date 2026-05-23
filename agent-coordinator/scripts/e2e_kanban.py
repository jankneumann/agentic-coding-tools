#!/usr/bin/env python3
"""End-to-end orchestrator for the kanban-viz transition test.

Two modes:

  local   (default)  Brings up Postgres + coordinator-api in Docker with
                     ephemeral API key + SSE signing key, waits for /health,
                     runs the vitest e2e suite against http://localhost:8081,
                     and tears the stack down. Hermetic: no leftover state.

  remote             Runs the vitest e2e against a URL you supply
                     (--url + --api-key). Use for staging / Railway smoke.
                     Requires --allow-nonlocal as a guard against accidental
                     prod runs, since the test mutates issues.

Usage:

    # Local Docker (the common path)
    python3 agent-coordinator/scripts/e2e_kanban.py
    python3 agent-coordinator/scripts/e2e_kanban.py --seed
    python3 agent-coordinator/scripts/e2e_kanban.py --keep-up    # skip teardown

    # Railway / staging
    python3 agent-coordinator/scripts/e2e_kanban.py \\
        --target remote \\
        --url https://coord.rotkohl.ai \\
        --api-key "$RAILWAY_COORDINATOR_KEY" \\
        --allow-nonlocal

Exit codes:
    0  all tests passed
    1  setup error (Docker unavailable, health probe timed out, missing args)
    2  tests ran but reported failure
"""

from __future__ import annotations

import argparse
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import FrameType

SCRIPT_DIR = Path(__file__).resolve().parent
COORD_DIR = SCRIPT_DIR.parent
REPO_DIR = COORD_DIR.parent
KANBAN_DIR = REPO_DIR / "apps" / "kanban-viz"

LOCAL_URL = "http://localhost:8081"
HEALTH_TIMEOUT_S = 60
HEALTH_POLL_INTERVAL_S = 2.0

# Globals so the signal handler can reach them.
_compose_brought_up: bool = False
_teardown_requested: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"[e2e-kanban] {msg}", flush=True)


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None,
         check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with the usual ergonomics; surface stderr on failure."""
    _log(f"$ {' '.join(cmd)}" + (f"  (cwd={cwd.name})" if cwd else ""))
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=full_env,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        if capture:
            sys.stderr.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def _ensure_docker() -> None:
    """Refuse to start if Docker / Compose plugin isn't available."""
    try:
        _run(["docker", "compose", "version"], capture=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        _log(f"ERROR: docker compose unavailable: {exc}")
        sys.exit(1)


def _wait_for_health(url: str, api_key: str, timeout_s: int = HEALTH_TIMEOUT_S) -> None:
    """Poll /health until 200 or timeout."""
    deadline = time.monotonic() + timeout_s
    last_err: str | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"{url.rstrip('/')}/health")
            req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    _log("coordinator-api /health → 200")
                    return
                last_err = f"status {resp.status}"
        except urllib.error.URLError as exc:
            last_err = str(exc.reason if hasattr(exc, "reason") else exc)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
        time.sleep(HEALTH_POLL_INTERVAL_S)
    _log(f"ERROR: /health did not return 200 within {timeout_s}s (last: {last_err})")
    sys.exit(1)


def _compose_env(api_key: str, sse_key: str) -> dict[str, str]:
    """Operator-facing env vars consumed by docker-compose.yml's coordinator-api."""
    return {
        "COORDINATOR_API_KEYS": api_key,
        "COORDINATOR_SSE_SIGNING_KEY": sse_key,
    }


def _compose_up(api_key: str, sse_key: str) -> None:
    global _compose_brought_up
    _ensure_docker()
    _log("Bringing up postgres + coordinator-api via Docker Compose...")
    _run(
        ["docker", "compose", "--profile", "api", "up", "-d", "--build"],
        cwd=COORD_DIR,
        env=_compose_env(api_key, sse_key),
    )
    _compose_brought_up = True


def _compose_down(remove_volumes: bool = True) -> None:
    """Tear the stack down. Always best-effort — never raise from here."""
    if not _compose_brought_up:
        return
    _log("Tearing down Docker stack...")
    args = ["docker", "compose", "--profile", "api", "down"]
    if remove_volumes:
        args.append("-v")
    try:
        _run(args, cwd=COORD_DIR, check=False)
    except Exception as exc:  # noqa: BLE001
        _log(f"warn: teardown raised {exc!r} — leaving stack as-is")


def _install_signal_handlers() -> None:
    def handler(signum: int, frame: FrameType | None) -> None:
        global _teardown_requested
        if _teardown_requested:
            _log("Second signal — exiting hard.")
            sys.exit(130)
        _teardown_requested = True
        _log(f"Received signal {signum} — tearing down...")
        _compose_down()
        sys.exit(130)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


# ---------------------------------------------------------------------------
# Vitest invocation
# ---------------------------------------------------------------------------


def _run_vitest(api_url: str, api_key: str) -> int:
    """Run the e2e.integration suite. Returns the vitest exit code."""
    if not KANBAN_DIR.is_dir():
        _log(f"ERROR: kanban-viz dir not found at {KANBAN_DIR}")
        return 1

    # Ensure node_modules exist — npm install is idempotent if up to date.
    if not (KANBAN_DIR / "node_modules").is_dir():
        _log("node_modules missing — running npm install...")
        _run(["npm", "install"], cwd=KANBAN_DIR)

    _log(f"Running vitest e2e suite against {api_url}...")
    result = subprocess.run(
        ["npm", "test", "--", "--run", "e2e.integration"],
        cwd=str(KANBAN_DIR),
        env={
            **os.environ,
            "VITE_COORDINATOR_URL": api_url,
            "VITE_API_KEY": api_key,
        },
        check=False,
    )
    return result.returncode


def _run_seed(api_url: str, api_key: str) -> None:
    """Optional pre-test seed so the operator can also smoke the browser path."""
    seeder = SCRIPT_DIR / "seed_kanban_board.py"
    _log("Seeding demo data so the browser path is browsable...")
    _run(
        [sys.executable, str(seeder),
         "--api-url", api_url, "--api-key", api_key],
        check=False,
    )


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


def run_local(args: argparse.Namespace) -> int:
    # Ephemeral per-run keys. Never persist; never log.
    api_key = secrets.token_hex(16)
    sse_key = secrets.token_hex(32)

    _install_signal_handlers()

    try:
        _compose_up(api_key, sse_key)
        _wait_for_health(LOCAL_URL, api_key, timeout_s=args.health_timeout)
        if args.seed:
            _run_seed(LOCAL_URL, api_key)
        rc = _run_vitest(LOCAL_URL, api_key)
        return rc
    finally:
        if args.keep_up:
            _log(f"--keep-up set — stack still running. API key: {api_key}")
            _log("Tear down manually: cd agent-coordinator && docker compose --profile api down -v")
        else:
            _compose_down(remove_volumes=not args.keep_volumes)


def run_remote(args: argparse.Namespace) -> int:
    if not args.url:
        _log("ERROR: --url required for --target remote")
        return 1
    if not args.api_key:
        # Allow pulling from env to keep keys out of `ps`.
        args.api_key = os.environ.get("E2E_API_KEY") or os.environ.get("COORDINATION_API_KEY")
    if not args.api_key:
        _log("ERROR: --api-key (or E2E_API_KEY env) required for --target remote")
        return 1

    is_localhost = args.url.startswith(("http://localhost", "http://127.0.0.1"))
    if not is_localhost and not args.allow_nonlocal:
        _log("ERROR: --url is non-localhost. The vitest test creates and "
             "closes issues — pass --allow-nonlocal to confirm this is "
             "intended (and that the target is a staging environment, not "
             "production).")
        return 1

    _wait_for_health(args.url, args.api_key, timeout_s=args.health_timeout)
    if args.seed:
        if not args.allow_nonlocal and not is_localhost:
            _log("Refusing to seed against a non-local URL without --allow-nonlocal")
            return 1
        _run_seed(args.url, args.api_key)
    return _run_vitest(args.url, args.api_key)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        choices=("local", "remote"),
        default="local",
        help="local: docker-orchestrated (default); remote: run against a URL you supply",
    )
    parser.add_argument("--url", help="Base URL of an already-running coordinator (remote only)")
    parser.add_argument("--api-key", help="API key (remote only; or set E2E_API_KEY in env)")
    parser.add_argument(
        "--allow-nonlocal",
        action="store_true",
        help=(
            "Required when --url is not localhost. Confirms the test mutates "
            "issues and the target is a staging URL, not production."
        ),
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help=(
            "Run seed_kanban_board.py against the target before running "
            "vitest (handy for the browser smoke)."
        ),
    )
    parser.add_argument(
        "--keep-up",
        action="store_true",
        help=(
            "(local only) Don't tear down after the test — leave the stack "
            "for browser inspection."
        ),
    )
    parser.add_argument(
        "--keep-volumes",
        action="store_true",
        help="(local only) Keep postgres volume on teardown (default: docker compose down -v).",
    )
    parser.add_argument(
        "--health-timeout",
        type=int,
        default=HEALTH_TIMEOUT_S,
        help=f"Seconds to wait for /health=200 before giving up (default: {HEALTH_TIMEOUT_S})",
    )
    args = parser.parse_args()

    if args.target == "local":
        rc = run_local(args)
    else:
        rc = run_remote(args)
    # Normalize: anything non-zero from vitest is a test failure (exit 2),
    # anything else is a setup error (exit 1).
    return 0 if rc == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
