"""Deterministic validation of candidate-work stubs for /prioritize-proposals.

Candidate work reaches this skill as one of three historical shapes emitted by
the discovery generators (bug-scrub, improve-harness, explore-feature). ri-11
defines a single canonical shape — ``openspec/schemas/candidate-work.schema.json``
— and this module is the seam where prioritize-proposals refuses to rank input
that does not conform to it.

Pure + deterministic: no LLM calls, no network, no subprocess. Validation is
performed with ``jsonschema`` against the on-disk schema, and every failure is
reported with the JSON pointer to the offending field and a human-readable
message so the caller can fix the input.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

SCHEMA_FILENAME = "candidate-work.schema.json"


class CandidateWorkValidationError(ValueError):
    """Raised when a candidate-work stub does not conform to the schema.

    ``errors`` holds one formatted line per schema violation.
    """

    def __init__(self, errors: list[str], *, index: int | None = None) -> None:
        self.errors = errors
        self.index = index
        where = "" if index is None else f" (item #{index})"
        joined = "\n  - ".join(errors)
        super().__init__(
            f"candidate-work stub failed schema validation{where}:\n  - {joined}"
        )


def find_schema_path(start: Path | None = None) -> Path:
    """Locate ``openspec/schemas/candidate-work.schema.json`` by walking upward.

    Starts from this module's directory (or ``start``) and searches each
    ancestor for ``openspec/schemas/<SCHEMA_FILENAME>``. Raises FileNotFoundError
    if the schema cannot be located — validation is mandatory, so a missing
    schema is a hard error rather than a silent skip.
    """
    here = (start or Path(__file__)).resolve()
    for ancestor in (here, *here.parents):
        candidate = ancestor / "openspec" / "schemas" / SCHEMA_FILENAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"could not locate openspec/schemas/{SCHEMA_FILENAME} above {here}"
    )


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load and parse the canonical candidate-work JSON Schema."""
    path = schema_path or find_schema_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _format_error(exc: Any) -> str:
    """Turn a jsonschema ValidationError into a single readable line."""
    pointer = "/".join(str(p) for p in exc.absolute_path)
    location = f"$.{pointer}" if pointer else "$ (root)"
    return f"{location}: {exc.message}"


def validate_candidate_work(
    instance: Any,
    *,
    schema: dict[str, Any] | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    """Validate a single candidate-work stub against the canonical schema.

    Returns the instance unchanged on success. Raises
    :class:`CandidateWorkValidationError` listing every violation on failure so
    the caller sees all problems at once, not just the first.
    """
    import jsonschema

    active_schema = schema if schema is not None else load_schema()
    validator = jsonschema.Draft202012Validator(active_schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        raise CandidateWorkValidationError(
            [_format_error(e) for e in errors], index=index
        )
    return instance


def validate_candidate_work_batch(
    instances: Iterable[Any],
    *,
    schema: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Validate many stubs; fail closed on the first non-conforming item.

    The batch position is reported in the error so the caller can point at the
    offending entry in a candidate list.
    """
    active_schema = schema if schema is not None else load_schema()
    validated: list[dict[str, Any]] = []
    for i, instance in enumerate(instances):
        validated.append(
            validate_candidate_work(instance, schema=active_schema, index=i)
        )
    return validated


def load_candidate_work(path: Path, *, schema: dict[str, Any] | None = None) -> Any:
    """Read a JSON file of candidate work and validate it before returning.

    Accepts either a single stub object or a JSON array of stubs. Malformed JSON
    and schema violations both raise (JSONDecodeError / CandidateWorkValidationError).
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return validate_candidate_work_batch(raw, schema=schema)
    return validate_candidate_work(raw, schema=schema)


def _cli() -> int:
    """Validate a candidate-work JSON file; exit non-zero with errors on stderr."""
    import argparse
    import sys

    p = argparse.ArgumentParser(
        description="Validate candidate-work stub(s) against candidate-work.schema.json"
    )
    p.add_argument("path", help="Path to a candidate-work JSON file (object or array).")
    args = p.parse_args()

    try:
        result = load_candidate_work(Path(args.path))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {args.path} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    except CandidateWorkValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    count = len(result) if isinstance(result, list) else 1
    print(f"ok: {count} candidate-work stub(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
