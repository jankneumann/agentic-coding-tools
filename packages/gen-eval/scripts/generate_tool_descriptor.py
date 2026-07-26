#!/usr/bin/env python3
"""Generate a tool descriptor from a CLI contract.

Usage::

    python scripts/generate_tool_descriptor.py                  # write in place
    python scripts/generate_tool_descriptor.py --out PATH       # write elsewhere
    python scripts/generate_tool_descriptor.py --check          # exit 1 on drift

Mirrors ``scripts/generate_contract_schemas.py``: the descriptor is a
checked-in, reviewable artifact rather than something computed at run time
(design D2). Deriving it in memory at load time would make the declared
surface depend on generator success during evaluation — which is exactly the
fail-open direction the contract-first design exists to prevent.

Three assertions run in order, and each fails closed (design D3):

1. the artifact declares a **non-zero number of coverage units**;
2. its coverage-unit count **equals the contract's**;
3. its content matches the checked-in copy byte for byte.

The coverage unit for a tool is the flag, positional, or *named* subcommand —
never the command. A flat CLI declares exactly one command with an empty name,
so a guard phrased in terms of commands counts 1, matches 1, and diffs clean
while the declared surface is empty. That is the vacuous pass this guard was
written against, and (1) is what catches it: (3) alone is satisfied by
"empty == empty", so both files can rot to nothing together and stay green.
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# Allow running straight from a checkout without installing the package.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PACKAGE_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from gen_eval.descriptor import (  # noqa: E402
    ExitCodeSpec,
    FlagSpec,
    PositionalSpec,
    ServiceSpec,
    ToolCommandSpec,
    ToolDescriptor,
)

_REPO_ROOT = _PACKAGE_ROOT.parent.parent

DEFAULT_CONTRACT = (
    _REPO_ROOT / "openspec" / "contracts" / "gen-eval-framework" / "cli" / "gen-eval.yaml"
)
DEFAULT_OUT = _PACKAGE_ROOT / "evaluation" / "descriptor.yaml"

_HEADER = """\
# GENERATED FILE — do not edit by hand.
#
# Derived from {contract} by scripts/generate_tool_descriptor.py.
# Edit the contract and regenerate:
#
#     python scripts/generate_tool_descriptor.py
#
# CI runs the same script with --check; an edit made here and not made in the
# contract fails that gate rather than silently becoming the source of truth.
"""


# ---------------------------------------------------------------------------
# Counting — deliberately two independent implementations
# ---------------------------------------------------------------------------


def contract_unit_count(document: dict[str, Any]) -> int:
    """Count coverage units straight from a raw contract document.

    Independent of :meth:`ToolDescriptor.all_interfaces`, which counts the
    *model*. Assertion (2) is only a gate while the two sides are computed
    separately — a single shared function would agree with itself even when
    derivation dropped every flag. Do not refactor these together.
    """
    total = 0
    for command in document.get("commands") or []:
        if command.get("name"):
            total += 1
        total += len(command.get("flags") or [])
        total += len(command.get("positionals") or [])
    return total


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _flag_payload(flag: FlagSpec) -> dict[str, Any]:
    # ``name`` and ``type`` are the flag's identity; everything else is
    # emitted only when it differs from the model default, so the artifact
    # stays readable as a diff.
    return {
        "name": flag.name,
        "type": flag.type,
        **flag.model_dump(mode="json", exclude_defaults=True),
    }


def _positional_payload(positional: PositionalSpec) -> dict[str, Any]:
    return {
        "name": positional.name,
        "type": positional.type,
        **positional.model_dump(mode="json", exclude_defaults=True),
    }


def _command_payload(command: ToolCommandSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": command.name,
        **command.model_dump(mode="json", exclude_defaults=True),
    }
    if command.flags:
        payload["flags"] = [_flag_payload(f) for f in command.flags]
    if command.positionals:
        payload["positionals"] = [_positional_payload(p) for p in command.positionals]
    return payload


def _service_payload(service: ServiceSpec) -> dict[str, Any]:
    return {"name": service.name, **service.model_dump(mode="json", exclude_defaults=True)}


def _exit_code_payload(exit_code: ExitCodeSpec) -> dict[str, Any]:
    return exit_code.model_dump(mode="json", exclude_none=True)


def render(descriptor: ToolDescriptor, contract: Path, out: Path) -> str:
    """Render the descriptor as the YAML text to be checked in.

    Path-valued fields are written relative to the descriptor's own directory:
    an absolute path in a checked-in artifact is drift on every machine but
    the one that generated it.
    """
    out_dir = out.resolve().parent
    relative_contract = os.path.relpath(contract.resolve(), out_dir)

    payload: dict[str, Any] = {
        "project": descriptor.project,
        "version": descriptor.version,
        "executable": descriptor.executable,
        "contract": relative_contract,
        "services": [_service_payload(s) for s in descriptor.services],
    }
    if descriptor.scenario_dirs:
        payload["scenario_dirs"] = [
            os.path.relpath(Path(d).resolve(), out_dir) for d in descriptor.scenario_dirs
        ]
    payload["commands"] = [_command_payload(c) for c in descriptor.commands]
    if descriptor.exit_codes:
        payload["exit_codes"] = [_exit_code_payload(e) for e in descriptor.exit_codes]

    body = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, width=100)
    return _HEADER.format(contract=relative_contract) + "\n" + body


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def _load_contract(path: Path) -> dict[str, Any]:
    with open(path) as f:
        document = yaml.safe_load(f)
    if not isinstance(document, dict):
        raise ValueError(f"Expected YAML mapping in {path}, got {type(document).__name__}")
    return document


def _fail(message: str) -> int:
    sys.stderr.write(f"{message}\n")
    return 1


def _check_units(units: list[str], expected: int, source: str) -> int | None:
    """Assertions (1) and (2). Returns an exit code, or None when both hold."""
    if not units:
        return _fail(
            f"{source} declares zero coverage units — refusing to treat an empty "
            f"declared surface as coverage. For a tool the coverage unit is the "
            f"flag, positional or named subcommand; a command declaring none of "
            f"them contributes nothing testable."
        )
    if len(units) != expected:
        return _fail(
            f"coverage unit count mismatch: {source} declares {len(units)}, "
            f"the contract declares {expected}"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the checked-in descriptor is empty, "
        "miscounted, or drifted from the contract",
    )
    parser.add_argument("--project", default=None, help="Override the derived project name")
    parser.add_argument("--descriptor-version", default=None, help="Override the version")
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        action="append",
        default=None,
        help="Scenario directory, relative to the descriptor (repeatable)",
    )
    args = parser.parse_args(argv)

    contract: Path = args.contract
    out: Path = args.out

    if not contract.is_file():
        return _fail(f"contract not found: {contract}")

    document = _load_contract(contract)
    expected = contract_unit_count(document)

    scenario_dirs = (
        [(out.resolve().parent / d).resolve() for d in args.scenario_dir]
        if args.scenario_dir
        else None
    )
    derived = ToolDescriptor.from_contract(
        contract,
        project=args.project,
        version=args.descriptor_version,
        scenario_dirs=scenario_dirs,
    )
    generated = render(derived, contract, out)

    if args.check:
        if not out.is_file():
            return _fail(
                f"no descriptor at {out} — a missing artifact is not an up-to-date one. "
                f"Run: python scripts/generate_tool_descriptor.py"
            )
        # Assertions (1) and (2) run against the CHECKED-IN copy, not against
        # what was just derived. Checking the fresh derivation would compare
        # the contract with itself and pass while the artifact on disk is
        # empty or truncated.
        checked_in = ToolDescriptor.from_yaml(out)
        failure = _check_units(checked_in.all_interfaces(), expected, "the checked-in descriptor")
        if failure is not None:
            return failure

        current = out.read_text(encoding="utf-8")
        if current != generated:
            sys.stderr.write(f"drift: {out}\n")
            sys.stderr.writelines(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    generated.splitlines(keepends=True),
                    fromfile=f"{out.name} (checked in)",
                    tofile=f"{out.name} (generated)",
                )
            )
            sys.stderr.write(
                "\nThe descriptor is out of date. Run: python scripts/generate_tool_descriptor.py\n"
            )
            return 1

        print(f"tool descriptor up to date ({expected} coverage units)")
        return 0

    failure = _check_units(derived.all_interfaces(), expected, "the derived descriptor")
    if failure is not None:
        # Nothing is written. A degenerate artifact left on disk would make
        # the byte-identity assertion compare empty against empty forever.
        return failure

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generated, encoding="utf-8")
    print(f"wrote {out} ({expected} coverage units)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
