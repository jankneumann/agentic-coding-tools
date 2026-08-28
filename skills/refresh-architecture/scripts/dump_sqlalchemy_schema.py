#!/usr/bin/env python3
"""Emit `CREATE TABLE` DDL for a declared SQLAlchemy `MetaData` (D7).

A repository whose migrations are Python — Alembic, most commonly — has nothing
the SQL analyzers parse, so it gets no schema analysis at all. This dumper gives
it one from the source the ORM already declares: it imports the configured
`MetaData` and compiles every table in it to DDL, which the existing regex and
tree-sitter SQL analyzers then consume unchanged.

**No database connection, ever.** `CreateTable(...).compile(dialect=...)` is a
pure function of the declared metadata and a dialect object; no engine is
created and no driver is loaded. That is the whole reason this exists rather
than `alembic upgrade base:head --sql`, which was measured and rejected: offline
replay stops at the first migration that reads a query result inside
`upgrade()`, and 16 of 75 migrations in the first consumer do exactly that.

**What this is.** The *intended* schema. The *actual* schema is whatever the
migration chain produces, and the two agree only where the repository's own
tooling (`alembic check`) keeps them aligned. Nothing here claims otherwise.

Exit codes are the contract with `refresh_architecture.sh`:

* ``0``  — DDL written.
* ``3``  — inapplicable source: SQLAlchemy absent, target unimportable, target
           is not metadata, or the metadata declares no tables. The reason goes
           to stderr and the caller skips the stage. Nothing is written.
* ``1``  — the source was applicable and the dump failed anyway. That is a real
           failure and the caller fails the stage loudly.

The skip-versus-fail split is D5's, applied to a second inapplicable input: an
absent source has produced no analysis, and neither an error nor an empty
artifact is an honest record of that.

Usage::

    dump_sqlalchemy_schema.py --target app.models:Base --output out/0001_schema.sql
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import traceback
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_SKIP = 3


def _skip(message: str, *, detail: str | None = None) -> int:
    print(f"SKIP: {message}", file=sys.stderr)
    if detail:
        print(detail.rstrip(), file=sys.stderr)
    return EXIT_SKIP


def _resolve_metadata(target: str):
    """Import ``module:attr`` and return the `MetaData` it names.

    Accepts either a `MetaData` directly or anything carrying one as
    ``.metadata`` — declarative `Base` classes are what consumers actually hand
    over, and demanding ``Base.metadata`` would be a spelling trap for no gain.
    """
    from sqlalchemy import MetaData

    module_name, sep, attr_path = target.partition(":")
    if not module_name or not sep or not attr_path:
        raise ValueError(f"expected '<module>:<attribute>', got {target!r}")

    obj = importlib.import_module(module_name)
    for part in attr_path.split("."):
        obj = getattr(obj, part)

    if isinstance(obj, MetaData):
        return obj
    metadata = getattr(obj, "metadata", None)
    if isinstance(metadata, MetaData):
        return metadata
    raise TypeError(
        f"{target} resolved to {type(obj).__name__}, which is neither a MetaData "
        "nor an object declaring one as .metadata"
    )


def _render(metadata, dialect_name: str, target: str) -> str:
    """Compile every declared table to DDL, in dependency order.

    ``sorted_tables`` is topological then alphabetical, so the output is stable
    across runs — a producer whose bytes wobble would defeat the freshness
    check that consumes this pipeline — and foreign keys refer to tables that
    the file has already created.
    """
    from sqlalchemy.dialects import registry
    from sqlalchemy.schema import CreateTable

    dialect = registry.load(dialect_name)()
    header = (
        f"-- Generated from SQLAlchemy metadata: {target}\n"
        "-- Declared schema, not a migration. Do not apply to a database.\n\n"
    )
    statements = [
        str(CreateTable(table).compile(dialect=dialect)).strip() + ";"
        for table in metadata.sorted_tables
    ]
    return header + "\n\n".join(statements) + "\n"


def _write_atomically(path: Path, text: str) -> None:
    """Write whole or not at all.

    A truncated DDL file is worse than no file: the analyzer would parse it
    successfully and report a schema that is missing tables, with nothing in the
    output to say so.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit CREATE TABLE DDL from a declared SQLAlchemy MetaData."
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Import path of the metadata: '<module>:<attribute>' "
        "(e.g. app.models:Base or app.db:metadata)",
    )
    parser.add_argument(
        "--output", required=True, help="Path of the .sql file to write"
    )
    parser.add_argument(
        "--sys-path",
        action="append",
        default=None,
        help="Directory to prepend to sys.path before importing (repeatable; "
        "defaults to the current working directory)",
    )
    parser.add_argument(
        "--dialect",
        default="postgresql",
        help="SQLAlchemy dialect used to compile the DDL (default: postgresql)",
    )
    args = parser.parse_args(argv)

    for entry in reversed(args.sys_path or [os.getcwd()]):
        resolved = str(Path(entry).resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    try:
        import sqlalchemy  # noqa: F401
    except Exception as exc:  # ImportError, or a broken install
        return _skip(
            "SQLAlchemy is not importable by this interpreter "
            f"({sys.executable}): {exc!r}. It is an optional dependency; point "
            "SCHEMA_SOURCE_PYTHON at an interpreter that has it, or unset "
            "SCHEMA_SOURCE."
        )

    try:
        metadata = _resolve_metadata(args.target)
    except Exception as exc:
        return _skip(
            f"cannot import the schema target {args.target!r}: "
            f"{type(exc).__name__}: {exc}",
            detail=traceback.format_exc(),
        )

    if not metadata.tables:
        # Never emit a degenerate artifact. An empty DDL file analyses
        # "successfully" into zero tables, which is indistinguishable from a
        # real result and hides the misconfiguration that caused it.
        return _skip(
            f"{args.target} declares no tables — writing no DDL, because an "
            "empty schema file would be reported as a successful analysis of "
            "nothing. Check that the target imports the modules that define "
            "the models."
        )

    try:
        ddl = _render(metadata, args.dialect, args.target)
        _write_atomically(Path(args.output), ddl)
    except Exception:
        # Applicable input that failed to render is a real failure, not a skip.
        print(traceback.format_exc(), file=sys.stderr)
        print(
            f"ERROR: failed to compile DDL for {args.target} with dialect "
            f"{args.dialect}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    print(
        f"Wrote {len(metadata.tables)} table(s) from {args.target} to {args.output}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
