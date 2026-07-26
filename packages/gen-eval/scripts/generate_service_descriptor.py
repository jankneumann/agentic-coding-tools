#!/usr/bin/env python3
"""Generate a service descriptor from an OpenAPI contract.

Usage::

    python scripts/generate_service_descriptor.py --contract C --out D
    python scripts/generate_service_descriptor.py --contract C --out D --check

The tool-descriptor generator's sibling, with one difference that is not
cosmetic: **the service archetype's coverage unit is the operation**, while
the tool archetype's is the flag, positional or named subcommand (design D3).
Counting interfaces here instead would inflate the number — one operation
exposed on HTTP, MCP and CLI is one unit with three surface entries, not
three units — and a guard that counts the wrong thing agrees with itself
while the artifact rots.

The same three assertions run in order, each failing closed (D3):

1. the artifact declares a **non-zero number of operations**;
2. its operation count **equals the contract's**;
3. its content matches the checked-in copy byte for byte.

``--contract`` and ``--out`` are required rather than defaulted. This repo
has no service contract yet — issue #288 tracks that the coordinator declares
38 endpoints against 82 route decorators — and a default pointing at a
fixture would make the guard look wired up while guarding nothing real.
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

from gen_eval.service_descriptor import (  # noqa: E402
    OperationSpec,
    ServiceDescriptor,
)

#: Spelled out here rather than imported from the model, so the contract-side
#: count below stays an independent reading. See ``contract_operation_count``.
_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

_HEADER = """\
# GENERATED FILE — do not edit by hand.
#
# Derived from {contract} by scripts/generate_service_descriptor.py.
# Edit the contract and regenerate:
#
#     python scripts/generate_service_descriptor.py --contract <c> --out <d>
#
# CI runs the same script with --check; an edit made here and not made in the
# contract fails that gate rather than silently becoming the source of truth.
"""


def contract_operation_count(document: dict[str, Any]) -> int:
    """Count operations straight from a raw OpenAPI document.

    Independent of :meth:`ServiceDescriptor.coverage_unit_count`, which counts
    the model. Assertion (2) is only a gate while the two sides are computed
    separately — one shared function would agree with itself even when
    extraction dropped half the paths. Do not refactor these together.
    """
    return sum(
        1
        for item in (document.get("paths") or {}).values()
        if isinstance(item, dict)
        for method in item
        if method.lower() in _HTTP_METHODS
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _operation_payload(operation: OperationSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation_id": operation.operation_id,
        "method": operation.method,
        "path": operation.path,
        **operation.model_dump(mode="json", exclude_defaults=True),
    }
    # Parameters and the request body are inputs to the MCP projection, not
    # part of the declared surface. Keeping them out keeps the reviewable
    # artifact about coverage rather than restating the contract.
    payload.pop("parameters", None)
    payload.pop("request_body", None)
    return payload


def render(descriptor: ServiceDescriptor, contract: Path, out: Path) -> str:
    out_dir = out.resolve().parent
    relative_contract = os.path.relpath(contract.resolve(), out_dir)

    payload: dict[str, Any] = {
        "project": descriptor.project,
        "version": descriptor.version,
        "contract": relative_contract,
        "services": [
            {"name": s.name, **s.model_dump(mode="json", exclude_defaults=True)}
            for s in descriptor.services
        ],
    }
    if descriptor.scenario_dirs:
        payload["scenario_dirs"] = [
            os.path.relpath(Path(d).resolve(), out_dir) for d in descriptor.scenario_dirs
        ]
    payload["operations"] = [_operation_payload(op) for op in descriptor.operations]
    if descriptor.mcp_resources:
        payload["mcp_resources"] = list(descriptor.mcp_resources)
    if descriptor.mcp_prompts:
        payload["mcp_prompts"] = list(descriptor.mcp_prompts)

    body = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, width=100)
    return _HEADER.format(contract=relative_contract) + "\n" + body


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def _fail(message: str) -> int:
    sys.stderr.write(f"{message}\n")
    return 1


def _check_operations(count: int, expected: int, source: str) -> int | None:
    """Assertions (1) and (2). Returns an exit code, or None when both hold."""
    if count == 0:
        return _fail(
            f"{source} declares zero operations — refusing to treat an empty "
            f"declared surface as coverage. For a service the coverage unit is "
            f"the operation."
        )
    if count != expected:
        return _fail(
            f"operation count mismatch: {source} declares {count}, the contract declares {expected}"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the checked-in descriptor is empty, "
        "miscounted, or drifted from the contract",
    )
    parser.add_argument("--project", default=None)
    parser.add_argument("--descriptor-version", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--scenario-dir", type=Path, action="append", default=None)
    args = parser.parse_args(argv)

    contract: Path = args.contract
    out: Path = args.out

    if not contract.is_file():
        return _fail(f"contract not found: {contract}")

    with open(contract) as f:
        document = yaml.safe_load(f)
    if not isinstance(document, dict):
        return _fail(f"expected a YAML mapping in {contract}")
    expected = contract_operation_count(document)

    scenario_dirs = (
        [(out.resolve().parent / d).resolve() for d in args.scenario_dir]
        if args.scenario_dir
        else None
    )
    derived = ServiceDescriptor.from_contract(
        contract,
        project=args.project,
        version=args.descriptor_version,
        base_url=args.base_url,
        scenario_dirs=scenario_dirs,
    )
    generated = render(derived, contract, out)

    if args.check:
        if not out.is_file():
            return _fail(f"no descriptor at {out} — a missing artifact is not an up-to-date one.")
        # Assertions (1) and (2) run against the CHECKED-IN copy. Checking the
        # fresh derivation would compare the contract with itself and pass
        # while the artifact on disk is empty or truncated.
        checked_in = ServiceDescriptor.from_yaml(out)
        failure = _check_operations(
            checked_in.coverage_unit_count(), expected, "the checked-in descriptor"
        )
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
            sys.stderr.write("\nThe descriptor is out of date. Regenerate it.\n")
            return 1

        print(f"service descriptor up to date ({expected} operations)")
        return 0

    failure = _check_operations(derived.coverage_unit_count(), expected, "the derived descriptor")
    if failure is not None:
        # Nothing is written: a degenerate artifact on disk makes the
        # byte-identity assertion compare empty against empty from then on.
        return failure

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generated, encoding="utf-8")
    print(f"wrote {out} ({expected} operations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
