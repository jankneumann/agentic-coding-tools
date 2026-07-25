#!/usr/bin/env python3
"""Generate the versioned JSON Schema contract under ``src/gen_eval/contracts/``.

Writes four artifacts:

    interface-descriptor.schema.json   from descriptor.InterfaceDescriptor
    scenario.schema.json               from models.Scenario
    eval-report.schema.json            from reports.GenEvalReport
    VERSION                            from contracts.CONTRACT_VERSION

Usage::

    python scripts/generate_contract_schemas.py            # write in place
    python scripts/generate_contract_schemas.py --out DIR  # write elsewhere
    python scripts/generate_contract_schemas.py --check    # exit 1 on drift

``--check`` is what the drift guard in ``tests/test_contract_schemas.py``
asserts; it is also safe to wire into CI directly.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

# Allow running straight from a checkout without installing the package.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from gen_eval.contracts import CONTRACT_VERSION, SCHEMA_FILENAMES  # noqa: E402
from gen_eval.descriptor import InterfaceDescriptor  # noqa: E402
from gen_eval.models import Scenario  # noqa: E402
from gen_eval.reports import GenEvalReport  # noqa: E402

DEFAULT_OUT = _SRC / "gen_eval" / "contracts"

_BASE_ID = (
    "https://raw.githubusercontent.com/jankneumann/agentic-coding-tools"
    "/main/packages/gen-eval/src/gen_eval/contracts"
)

_TITLES = {
    "interface-descriptor": "gen-eval interface descriptor",
    "scenario": "gen-eval scenario",
    "eval-report": "gen-eval report",
}


def _build(name: str, model: Any, mode: str) -> dict[str, Any]:
    """Render one model's JSON Schema with contract metadata attached.

    ``mode`` selects pydantic's validation vs serialization view. The report
    is generated in ``serialization`` mode so that computed fields (notably
    ``VisibilityBreakdown.pass_rate``) appear — that view is what
    ``generate_json_report`` actually emits. Descriptor and scenario are
    generated in ``validation`` mode because consumers author those by hand
    and validate them on the way *in*.
    """
    schema: dict[str, Any] = model.model_json_schema(mode=mode)

    # Front-matter keys first, then whatever pydantic produced. Ordering is
    # cosmetic but keeps the checked-in diffs readable.
    header: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{_BASE_ID}/{SCHEMA_FILENAMES[name]}",
        "title": _TITLES[name],
        "x-gen-eval-contract-version": CONTRACT_VERSION,
    }
    # pydantic emits its own "title"; ours is the more useful one.
    schema.pop("title", None)
    header.update(schema)
    return header


def render() -> dict[str, str]:
    """Return ``{filename: file content}`` for every generated artifact."""
    out: dict[str, str] = {
        SCHEMA_FILENAMES["interface-descriptor"]: _dump(
            _build("interface-descriptor", InterfaceDescriptor, "validation")
        ),
        SCHEMA_FILENAMES["scenario"]: _dump(_build("scenario", Scenario, "validation")),
        SCHEMA_FILENAMES["eval-report"]: _dump(
            _build("eval-report", GenEvalReport, "serialization")
        ),
        "VERSION": f"{CONTRACT_VERSION}\n",
    }
    return out


def _dump(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the checked-in files differ from generated output",
    )
    args = parser.parse_args(argv)

    artifacts = render()
    out_dir: Path = args.out

    if args.check:
        drifted: list[str] = []
        for filename, content in artifacts.items():
            path = out_dir / filename
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != content:
                drifted.append(filename)
                sys.stderr.write(f"drift: {path}\n")
                sys.stderr.writelines(
                    difflib.unified_diff(
                        current.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile=f"{filename} (checked in)",
                        tofile=f"{filename} (generated)",
                    )
                )
        if drifted:
            sys.stderr.write(
                f"\n{len(drifted)} contract artifact(s) out of date. "
                f"Run: python scripts/generate_contract_schemas.py\n"
            )
            return 1
        print(f"contract artifacts up to date (version {CONTRACT_VERSION})")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in artifacts.items():
        (out_dir / filename).write_text(content, encoding="utf-8")
        print(f"wrote {out_dir / filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
