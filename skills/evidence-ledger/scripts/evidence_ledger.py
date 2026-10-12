#!/usr/bin/env python3
"""Evidence ledger loader and deterministic validator.

An evidence ledger records a debugging investigation in two tiers:

- the **factual tier**: gathered, immutable ``facts``;
- the **derivative tier**: ``signals`` (variable-vs-control fact pairs) and ``hypotheses``
  that cite facts.

A disputed fact is never edited. The dispute is recorded as a ``reverify_request`` plus a
newly gathered replacement fact.

Python API:

- ``load_ledger(path)`` loads YAML or JSON. Unquoted YAML timestamps stay strings.
- ``validate_ledger(doc)`` checks schema conformance, then referential integrity.
- ``check_revision(previous, current)`` checks that recorded facts and reverify requests
  were neither edited nor removed.

CLI::

    evidence_ledger.py validate <ledger> [--previous <ledger>] [--json]

Exit codes: 0 valid, 1 violations, 2 usage or load error.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_VERSION = 1
# The skill's own install_assets copy. It is byte-identical to
# openspec/schemas/evidence-ledger.schema.json, and resolving it relative to this file
# works from the canonical tree and from installed runtime copies alike.
SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "install_assets"
    / "openspec"
    / "schemas"
    / "evidence-ledger.schema.json"
)

SINGLE_LEDGER_CODES: tuple[str, ...] = (
    "schema_violation",
    "duplicate_id",
    "unknown_fact_ref",
    "signal_role_mismatch",
    "unknown_hypothesis_ref",
    "self_component",
    "nested_component",
    "replacement_is_target",
    "invalid_timestamp",
    "time_window_inverted",
)
REVISION_CODES: tuple[str, ...] = (
    "ledger_id_changed",
    "fact_removed",
    "fact_mutated",
    "reverify_removed",
    "reverify_mutated",
)
VIOLATION_CODES: tuple[str, ...] = SINGLE_LEDGER_CODES + REVISION_CODES

COLLECTIONS: tuple[str, ...] = ("facts", "signals", "hypotheses", "reverify_requests")


@dataclass(frozen=True, order=True)
class Violation:
    """One finding. ``path`` is a JSON-pointer-style location in the ledger."""

    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


class LedgerLoadError(Exception):
    """The ledger file could not be read or parsed."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class _StringTimestampLoader(yaml.SafeLoader):
    """A SafeLoader that leaves ISO-8601 timestamps as strings (design D8)."""


_StringTimestampLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _parse_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_StringTimestampLoader)  # noqa: S506 - SafeLoader subclass


def load_ledger(path: str | Path) -> Any:
    """Load a ledger from YAML (.yaml/.yml) or JSON (.json; other suffixes: JSON, then YAML)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LedgerLoadError(f"cannot read {path}: {exc}") from exc
    suffix = path.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            return _parse_yaml(text)
        if suffix == ".json":
            return json.loads(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return _parse_yaml(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise LedgerLoadError(f"cannot parse {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Single-ledger validation
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _pointer(parts: Any) -> str:
    return "".join(f"/{p}" for p in parts) or "/"


def _schema_violations(doc: Any) -> list[Violation]:
    found = [
        Violation(_pointer(err.absolute_path), "schema_violation", err.message)
        for err in _validator().iter_errors(doc)
    ]
    return sorted(set(found))


def _parse_ts(value: str) -> datetime | None:
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _semantic_violations(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    facts = doc.get("facts", [])
    signals = doc.get("signals", [])
    hypotheses = doc.get("hypotheses", [])
    requests = doc.get("reverify_requests", [])

    # One id namespace per ledger (D4).
    seen: dict[str, str] = {}
    for collection in COLLECTIONS:
        for index, entry in enumerate(doc.get(collection, [])):
            entry_id = entry["id"]
            here = f"/{collection}/{index}/id"
            if entry_id in seen:
                out.append(
                    Violation(
                        here, "duplicate_id", f"id {entry_id!r} already used at {seen[entry_id]}"
                    )
                )
            else:
                seen[entry_id] = here

    fact_roles = {f["id"]: f["role"] for f in facts}
    composite = {h["id"] for h in hypotheses if h.get("components")}
    hypothesis_ids = {h["id"] for h in hypotheses}
    other_ids = {
        e["id"] for c in ("signals", "hypotheses", "reverify_requests") for e in doc.get(c, [])
    }

    def fact_ref(where: str, ref: str) -> bool:
        if ref in fact_roles:
            return True
        detail = " (it is not a fact)" if ref in other_ids else ""
        out.append(Violation(where, "unknown_fact_ref", f"{ref!r} is not a recorded fact{detail}"))
        return False

    for index, fact in enumerate(facts):
        window = fact["time_window"]
        parsed: dict[str, datetime | None] = {}
        for bound in ("start", "end"):
            parsed[bound] = _parse_ts(window[bound])
            if parsed[bound] is None:
                out.append(
                    Violation(
                        f"/facts/{index}/time_window/{bound}",
                        "invalid_timestamp",
                        f"{window[bound]!r} is not an ISO-8601 timestamp",
                    )
                )
        start, end = parsed["start"], parsed["end"]
        if start is not None and end is not None and start > end:
            out.append(
                Violation(
                    f"/facts/{index}/time_window",
                    "time_window_inverted",
                    f"start {window['start']} is after end {window['end']}",
                )
            )

    if "created_at" in doc and _parse_ts(doc["created_at"]) is None:
        out.append(
            Violation(
                "/created_at",
                "invalid_timestamp",
                f"{doc['created_at']!r} is not an ISO-8601 timestamp",
            )
        )

    for index, signal in enumerate(signals):
        for field, role in (("variable_fact", "variable"), ("control_fact", "control")):
            where = f"/signals/{index}/{field}"
            ref = signal[field]
            if fact_ref(where, ref) and fact_roles[ref] != role:
                out.append(
                    Violation(
                        where,
                        "signal_role_mismatch",
                        f"{field} {ref!r} has role {fact_roles[ref]!r}, expected {role!r}",
                    )
                )

    for index, hypothesis in enumerate(hypotheses):
        for cite_index, ref in enumerate(hypothesis["cites"]):
            fact_ref(f"/hypotheses/{index}/cites/{cite_index}", ref)
        for comp_index, ref in enumerate(hypothesis.get("components", [])):
            where = f"/hypotheses/{index}/components/{comp_index}"
            if ref == hypothesis["id"]:
                out.append(
                    Violation(where, "self_component", f"{ref!r} lists itself as a component")
                )
            elif ref not in hypothesis_ids:
                out.append(
                    Violation(
                        where,
                        "unknown_hypothesis_ref",
                        f"{ref!r} is not a hypothesis in this ledger",
                    )
                )
            elif ref in composite:
                out.append(
                    Violation(
                        where,
                        "nested_component",
                        f"{ref!r} is itself composite; components nest one level only",
                    )
                )

    for index, request in enumerate(requests):
        fact_ref(f"/reverify_requests/{index}/fact_id", request["fact_id"])
        replacement = request.get("replacement_fact")
        if replacement is None:
            continue
        where = f"/reverify_requests/{index}/replacement_fact"
        if replacement == request["fact_id"]:
            out.append(
                Violation(
                    where,
                    "replacement_is_target",
                    f"replacement {replacement!r} is the disputed fact itself",
                )
            )
        else:
            fact_ref(where, replacement)

    return sorted(set(out))


def validate_ledger(doc: Any) -> list[Violation]:
    """Return every violation in ``doc``, sorted by (path, code, message).

    The semantic checks run only when the schema passes, because they rely on its shape.
    """
    schema_errors = _schema_violations(doc)
    if schema_errors:
        return schema_errors
    return _semantic_violations(doc)


# ---------------------------------------------------------------------------
# Revision immutability
# ---------------------------------------------------------------------------


def _canonical(entry: Any) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _by_id(doc: Any, collection: str) -> dict[str, Any]:
    if not isinstance(doc, dict):
        return {}
    entries = doc.get(collection) or []
    return {e["id"]: e for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    keys = set(before) | set(after)
    return sorted(k for k in keys if _canonical(before.get(k)) != _canonical(after.get(k)))


def check_revision(previous: Any, current: Any) -> list[Violation]:
    """Reject a revision that edits or removes a recorded fact or reverify request."""
    out: list[Violation] = []
    prev_id = previous.get("ledger_id") if isinstance(previous, dict) else None
    curr_id = current.get("ledger_id") if isinstance(current, dict) else None
    if prev_id != curr_id:
        out.append(
            Violation(
                "/ledger_id",
                "ledger_id_changed",
                f"ledger_id changed from {prev_id!r} to {curr_id!r}",
            )
        )

    for collection, removed, mutated, noun in (
        ("facts", "fact_removed", "fact_mutated", "fact"),
        ("reverify_requests", "reverify_removed", "reverify_mutated", "reverify request"),
    ):
        before = _by_id(previous, collection)
        after = _by_id(current, collection)
        for entry_id, old in before.items():
            where = f"/{collection}/{entry_id}"
            if entry_id not in after:
                out.append(Violation(where, removed, f"recorded {noun} {entry_id!r} was removed"))
                continue
            new = after[entry_id]
            if _canonical(old) != _canonical(new):
                fields = ", ".join(_changed_fields(old, new))
                hint = (
                    " (dispute it with a reverify_request plus a new fact)"
                    if noun == "fact"
                    else ""
                )
                out.append(
                    Violation(
                        where,
                        mutated,
                        f"recorded {noun} {entry_id!r} edited in place: {fields}{hint}",
                    )
                )
    return sorted(set(out))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence_ledger.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a ledger (and optionally a revision).")
    validate.add_argument("ledger", type=Path, help="Ledger file (.yaml, .yml or .json).")
    validate.add_argument(
        "--previous",
        type=Path,
        default=None,
        help="Previous revision; enables the immutability check.",
    )
    validate.add_argument("--json", action="store_true", help="Print a JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        current = load_ledger(args.ledger)
        previous = load_ledger(args.previous) if args.previous is not None else None
    except LedgerLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    violations = validate_ledger(current)
    if previous is not None:
        violations = sorted(set(violations) | set(check_revision(previous, current)))

    if args.json:
        report = {"valid": not violations, "violations": [v.to_dict() for v in violations]}
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for v in violations:
            print(f"{v.code}\t{v.path}\t{v.message}")
    return 1 if violations else 0


__all__ = [
    "COLLECTIONS",
    "REVISION_CODES",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "SINGLE_LEDGER_CODES",
    "VIOLATION_CODES",
    "LedgerLoadError",
    "Violation",
    "check_revision",
    "load_ledger",
    "main",
    "validate_ledger",
]


if __name__ == "__main__":
    sys.exit(main())
