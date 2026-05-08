"""CLI entry points for the autopilot per-phase dispatch helpers.

This script is the prose↔Python boundary between SKILL.md and the
in-process helpers in ``phase_agent.py``. SKILL.md shells out to:

    python3 runner.py build-dispatch --phase X --change-id Y
    python3 runner.py apply-outcome --change-id Y --phase X \\
                                    --outcome Z --handoff-id H

``build-dispatch`` prints a JSON object on stdout (``{prompt, model,
system_prompt, isolation, archetype}``) and writes a per-run resolution
cache file. The orchestrator passes ``prompt`` verbatim to
``Agent(...)`` — no string concatenation in prose (D2).

``apply-outcome`` updates ``loop-state.json`` with the new
``last_handoff_id`` / ``handoff_ids`` / ``phase_archetype`` (consuming
the cache file) and prints nothing on stdout.

Both subcommands exit zero on success and non-zero on validation /
configuration errors. They never raise unhandled exceptions: errors
are formatted as a one-line stderr message.

Spec: openspec/changes/wire-autopilot-phase-subagents/specs/skill-workflow/spec.md
Design decisions: D1, D3, D4.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Sibling-module import — allow running both as ``python runner.py`` and
# ``python -m skills.autopilot.scripts.runner``.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import phase_agent  # type: ignore[import-not-found]  # noqa: E402

logger = logging.getLogger("autopilot.runner")


def _cmd_build_dispatch(args: argparse.Namespace) -> int:
    try:
        result = phase_agent.build_phase_dispatch_kwargs(
            phase=args.phase,
            change_id=args.change_id,
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: build-dispatch failed: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


def _cmd_record_state_only_archetype(args: argparse.Namespace) -> int:
    """Record phase_archetype for a state-only phase (INIT or SUBMIT_PR).

    SKILL.md INIT/SUBMIT_PR sections shell to this so phase_archetype is
    populated for state-only phases the same way build-dispatch populates
    it for the 7 dispatching phases (closes IMPL_REVIEW finding R-001).
    """
    for name in ("change_id", "phase"):
        val = getattr(args, name, "")
        if not isinstance(val, str) or not val.strip():
            sys.stderr.write(f"runner: --{name.replace('_', '-')} must be a non-empty string\n")
            return 2
    try:
        phase_agent.record_state_only_archetype(
            change_id=args.change_id,
            phase=args.phase,
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: record-state-only-archetype failed: {exc}\n")
        return 1
    return 0


def _cmd_apply_outcome(args: argparse.Namespace) -> int:
    # Reject empty/whitespace-only IDs early. argparse only checks the
    # arg is present, not non-empty; phase_agent rejects deeper but the
    # CLI surface is the right place to fail fast.
    for name in ("change_id", "phase", "outcome", "handoff_id"):
        val = getattr(args, name, "")
        if not isinstance(val, str) or not val.strip():
            sys.stderr.write(f"runner: --{name.replace('_', '-')} must be a non-empty string\n")
            return 2
    try:
        phase_agent.apply_phase_outcome(
            change_id=args.change_id,
            phase=args.phase,
            outcome=args.outcome,
            handoff_id=args.handoff_id,
        )
    except ValueError as exc:
        sys.stderr.write(f"runner: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"runner: apply-outcome failed: {exc}\n")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner",
        description=(
            "Autopilot per-phase dispatch CLI. "
            "Subcommands: build-dispatch, apply-outcome."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bd = sub.add_parser(
        "build-dispatch",
        help="Resolve archetype, fold system_prompt into prompt, write cache, emit JSON.",
    )
    bd.add_argument("--phase", required=True, help="Phase id (e.g. IMPLEMENT).")
    bd.add_argument("--change-id", required=True, help="OpenSpec change identifier.")
    bd.set_defaults(func=_cmd_build_dispatch)

    ao = sub.add_parser(
        "apply-outcome",
        help="Update loop-state.json with handoff_id and consume the cache.",
    )
    ao.add_argument("--change-id", required=True)
    ao.add_argument("--phase", required=True)
    ao.add_argument("--outcome", required=True, help="Outcome string from the sub-agent.")
    ao.add_argument("--handoff-id", required=True)
    ao.set_defaults(func=_cmd_apply_outcome)

    rs = sub.add_parser(
        "record-state-only-archetype",
        help="Resolve archetype for INIT/SUBMIT_PR and write to loop-state.json.",
    )
    rs.add_argument("--change-id", required=True)
    rs.add_argument(
        "--phase",
        required=True,
        choices=["INIT", "SUBMIT_PR"],
        help="State-only phase id (INIT or SUBMIT_PR).",
    )
    rs.set_defaults(func=_cmd_record_state_only_archetype)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
