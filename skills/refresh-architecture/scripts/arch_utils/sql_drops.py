"""Removal semantics shared by both SQL schema analyzers.

A migration directory is a *sequence*, not an append-only set of ``CREATE``
statements. Read as the latter, the schema graph keeps describing objects that
were dropped: after migration 031 dropped ``memory_working`` and
``memory_procedural``, the regenerated graph still carried 27 references to
them, and nothing flagged it because the artifacts were internally consistent
(issue #386).

Two producers build that schema — ``analyze_postgres.py`` (regex) and
``analyze_sql_treesitter.py`` (CST, which overwrites the former's output with
an enriched version). Removal semantics live here rather than in either one so
the two cannot drift: a table that disappears from one analyzer's output but
survives in the other's is worse than neither handling drops at all.

Drops are matched on statement *text* rather than through the CST on purpose.
Their syntax is trivial, and the generic tree-sitter SQL grammar handles them
badly — ``DROP TABLE a, b CASCADE`` yields a partial ``ERROR`` node for the
second name, ``DROP INDEX public.idx`` truncates at the schema qualifier, and
``DROP TRIGGER x ON t`` does not parse at all. Text matching is both simpler
and more accurate for this statement class.

The applier is duck-typed over any object exposing the analyzers' shared
attribute names (``tables``, ``foreign_keys``, ``indexes``, ``triggers``,
``functions``), whose element dataclasses are field-compatible across both
modules.
"""

from __future__ import annotations

import re
from typing import Any, Protocol


class SchemaState(Protocol):
    """The mutable schema accumulated by an analyzer as it replays migrations."""

    tables: dict[str, Any]
    foreign_keys: list[Any]
    indexes: list[Any]
    triggers: list[Any]
    functions: list[Any]


# ---------------------------------------------------------------------------
# Identifier helpers
# ---------------------------------------------------------------------------

def strip_quotes(value: str) -> str:
    """Remove surrounding quotes from an identifier."""
    return value.strip().strip('"').strip("'")


def qualify(name: str, default_schema: str = "public") -> str:
    """Return a schema-qualified, lower-cased object name."""
    if "." in name:
        return name.lower()
    return f"{default_schema}.{name}".lower()


def strip_leading_comments(text: str) -> str:
    """Drop leading ``--`` lines and blank lines from a statement."""
    lines = text.split("\n")
    while lines:
        head = lines[0].strip()
        if head == "" or head.startswith("--"):
            lines.pop(0)
        else:
            break
    return "\n".join(lines).strip()


def _split_names(raw: str) -> list[str]:
    """Split a comma-separated object list from a DROP statement."""
    return [strip_quotes(part) for part in raw.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# Statement patterns
# ---------------------------------------------------------------------------

_DROP_TABLE_RE = re.compile(
    r"(?i)^DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<names>.+?)"
    r"(?:\s+(?:CASCADE|RESTRICT))?\s*;?\s*$",
    re.DOTALL,
)

_DROP_INDEX_RE = re.compile(
    r"(?i)^DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?(?P<names>.+?)"
    r"(?:\s+(?:CASCADE|RESTRICT))?\s*;?\s*$",
    re.DOTALL,
)

_DROP_TRIGGER_RE = re.compile(
    r"(?i)^DROP\s+TRIGGER\s+(?:IF\s+EXISTS\s+)?(?P<name>\S+)\s+ON\s+(?P<table>\S+?)"
    r"(?:\s+(?:CASCADE|RESTRICT))?\s*;?\s*$",
    re.DOTALL,
)

_DROP_FUNCTION_RE = re.compile(
    r"(?i)^DROP\s+(?:FUNCTION|PROCEDURE)\s+(?:IF\s+EXISTS\s+)?(?P<name>[^\s(;]+)",
)

_ALTER_TABLE_RE = re.compile(r"(?i)^ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\S+)\s+(.+)$", re.DOTALL)

_ALTER_DROP_COLUMN_RE = re.compile(
    r"(?i)\bDROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(\"[^\"]+\"|[\w$]+)",
)

_ALTER_DROP_CONSTRAINT_RE = re.compile(
    r"(?i)\bDROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?(\"[^\"]+\"|[\w$]+)",
)

_HAS_DROP_ACTION_RE = re.compile(r"(?i)\bDROP\s+(?:COLUMN|CONSTRAINT)\b")
_HAS_ADD_ACTION_RE = re.compile(r"(?i)\bADD\s+(?:COLUMN|CONSTRAINT)\b")


# ---------------------------------------------------------------------------
# Appliers
# ---------------------------------------------------------------------------

def drop_table(state: SchemaState, qualified: str) -> None:
    """Remove a table and everything Postgres would drop along with it.

    Indexes and triggers on the table go with it, and so do foreign keys in
    *both* directions: an FK pointing at a dropped table cannot survive either
    — that is precisely why Postgres refuses the DROP without ``CASCADE``.
    """
    state.tables.pop(qualified, None)
    state.foreign_keys = [
        fk
        for fk in state.foreign_keys
        if fk.from_table != qualified and fk.to_table != qualified
    ]
    state.indexes = [idx for idx in state.indexes if idx.table != qualified]
    state.triggers = [tr for tr in state.triggers if tr.table != qualified]


def drop_index(state: SchemaState, names: list[str]) -> None:
    """Remove indexes by name.

    Index names are stored bare (``CREATE INDEX`` takes an unqualified name —
    the schema comes from the table) but a ``DROP INDEX`` may qualify them, so
    only the last segment is compared.
    """
    targets = {name.rsplit(".", 1)[-1].lower() for name in names}
    state.indexes = [idx for idx in state.indexes if idx.name.lower() not in targets]


def drop_trigger(state: SchemaState, name: str, table: str) -> None:
    """Remove a trigger.

    A trigger name is unique per table, not per schema — the migrations reuse
    ``trg_*_notify`` across tables — so both parts must match.
    """
    lowered = name.lower()
    state.triggers = [
        tr
        for tr in state.triggers
        if not (tr.name.lower() == lowered and tr.table == table)
    ]


def drop_function(state: SchemaState, name: str) -> None:
    """Remove a stored function by qualified name.

    Overloads are not modelled (output keys on the name alone), so the
    argument list in the DROP is deliberately ignored.
    """
    state.functions = [fn for fn in state.functions if fn.name != name]


def drop_column(state: SchemaState, table_name: str, column: str) -> None:
    """Remove a column, plus the FK and indexes that cannot outlive it."""
    table = state.tables.get(table_name)
    if table is not None:
        table.columns = [c for c in table.columns if c.name != column]
        table.primary_key = [c for c in table.primary_key if c != column]
    state.foreign_keys = [
        fk
        for fk in state.foreign_keys
        if not (fk.from_table == table_name and column in fk.from_columns)
    ]
    state.indexes = [
        idx
        for idx in state.indexes
        if not (idx.table == table_name and column in idx.columns)
    ]


def drop_constraint(state: SchemaState, table_name: str, constraint: str) -> None:
    """Remove a named constraint.

    CHECK/UNIQUE constraints are not modelled; only foreign keys are, so this
    is a no-op unless the named constraint is a tracked FK.
    """
    state.foreign_keys = [
        fk
        for fk in state.foreign_keys
        if not (fk.from_table == table_name and fk.constraint_name == constraint)
    ]


def apply_alter_table_drops(state: SchemaState, table_name: str, actions: str) -> None:
    """Apply every ``DROP COLUMN`` / ``DROP CONSTRAINT`` action in *actions*."""
    for match in _ALTER_DROP_COLUMN_RE.finditer(actions):
        drop_column(state, table_name, strip_quotes(match.group(1)))
    for match in _ALTER_DROP_CONSTRAINT_RE.finditer(actions):
        drop_constraint(state, table_name, strip_quotes(match.group(1)))


def apply_drop_statement(state: SchemaState, stmt: str) -> bool:
    """Apply any removals *stmt* performs.

    Returns ``True`` when the statement was a pure removal and needs no further
    parsing, ``False`` when the caller should keep parsing it — either because
    it was not a removal at all, or because it is an ``ALTER TABLE`` whose ADD
    actions the caller still has to handle.
    """
    text = strip_leading_comments(stmt.strip())
    if not text:
        return False

    match = _DROP_TABLE_RE.match(text)
    if match:
        for name in _split_names(match.group("names")):
            drop_table(state, qualify(name))
        return True

    match = _DROP_INDEX_RE.match(text)
    if match:
        drop_index(state, _split_names(match.group("names")))
        return True

    match = _DROP_TRIGGER_RE.match(text)
    if match:
        drop_trigger(
            state,
            strip_quotes(match.group("name")),
            qualify(strip_quotes(match.group("table"))),
        )
        return True

    match = _DROP_FUNCTION_RE.match(text)
    if match:
        name = strip_quotes(match.group("name"))
        drop_function(state, name if "." in name else f"public.{name}")
        return True

    match = _ALTER_TABLE_RE.match(text)
    if match:
        actions = match.group(2).strip().rstrip(";").strip()
        if _HAS_DROP_ACTION_RE.search(actions):
            apply_alter_table_drops(
                state, qualify(strip_quotes(match.group(1))), actions
            )
            # Fall through when the same statement also adds something, so the
            # caller's ADD paths still see it.
            return not _HAS_ADD_ACTION_RE.search(actions)

    return False
