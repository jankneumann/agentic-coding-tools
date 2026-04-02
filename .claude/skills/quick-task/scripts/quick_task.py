"""Quick-task dispatch: delegate ad-hoc tasks to any configured vendor.

Design Decisions:
  D3: Uses a dedicated 'quick' dispatch_mode (read-write, no worktree).
  D4: Returns vendor stdout as freeform text, not structured findings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dispatch an ad-hoc task to a configured vendor CLI.",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Task prompt (joined with spaces)",
    )
    parser.add_argument(
        "--vendor",
        default=None,
        help="Dispatch to a specific vendor type (e.g., codex, claude, gemini)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory for dispatch (default: current directory)",
    )
    return parser.parse_args(argv)


def check_complexity(prompt: str) -> str | None:
    """Return a warning message if the prompt looks too complex for quick dispatch."""
    words = prompt.split()
    if len(words) > 500:
        return (
            f"Warning: prompt has {len(words)} words (>500). "
            "Consider using /plan-feature for larger tasks."
        )
    # Count file path references (patterns like src/foo.py, ./bar, /baz/qux)
    file_refs = re.findall(r'(?:^|\s)[./]?(?:\w+/)+\w+\.\w+', prompt)
    if len(file_refs) > 5:
        return (
            f"Warning: prompt references {len(file_refs)} files (>5). "
            "Consider using /plan-feature for larger tasks."
        )
    return None


def discover_and_dispatch(
    prompt: str,
    vendor: str | None = None,
    timeout: int = 300,
    cwd: Path | None = None,
) -> tuple[bool, str]:
    """Discover vendors and dispatch the task.

    Returns (success, output) tuple.
    """
    # Import review_dispatcher from parallel-infrastructure
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "parallel-infrastructure" / "scripts"
    sys.path.insert(0, str(scripts_dir))

    try:
        from review_dispatcher import ReviewOrchestrator
    except ImportError as exc:
        return False, f"Failed to import ReviewOrchestrator: {exc}"

    # Try coordinator first, then agents.yaml fallback
    orch = ReviewOrchestrator.from_coordinator()
    if not orch.adapters and not orch.sdk_adapters:
        orch = ReviewOrchestrator.from_agents_yaml()

    if not orch.adapters and not orch.sdk_adapters:
        return False, "No vendors configured. Check agents.yaml or coordinator setup."

    # Discover vendors with quick dispatch mode
    reviewers = orch.discover_reviewers(dispatch_mode="quick")
    available = [r for r in reviewers if r.available]

    if vendor:
        available = [r for r in available if vendor.lower() in r.vendor.lower()]
        if not available:
            return False, f"Vendor '{vendor}' not available for quick dispatch."

    if not available:
        return False, "No vendors available with 'quick' dispatch mode."

    # Dispatch to first available vendor
    results = orch.dispatch_and_wait(
        review_type="quick",
        dispatch_mode="quick",
        prompt=prompt,
        cwd=cwd or Path.cwd(),
        timeout_seconds=timeout,
    )

    if not results:
        return False, "Dispatch returned no results."

    # Return first result's raw output
    result = results[0]
    if result.success:
        # For quick-task, we want the raw findings/output, not parsed JSON
        if result.findings:
            import json
            return True, json.dumps(result.findings, indent=2)
        return True, f"[{result.vendor}] Task completed (no structured output returned)."
    else:
        return False, f"[{result.vendor}] Error: {result.error or 'Unknown error'}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    prompt = " ".join(args.prompt) if args.prompt else ""

    if not prompt.strip():
        print("Error: No task prompt provided.", file=sys.stderr)
        print("Usage: quick_task.py 'Fix the bug in src/main.py'", file=sys.stderr)
        return 1

    # Complexity check
    warning = check_complexity(prompt)
    if warning:
        print(f"\u26a0 {warning}", file=sys.stderr)
        print("Proceeding anyway...\n", file=sys.stderr)

    # Dispatch
    success, output = discover_and_dispatch(
        prompt=prompt,
        vendor=args.vendor,
        timeout=args.timeout,
        cwd=Path(args.cwd),
    )

    print(output)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
