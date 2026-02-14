#!/usr/bin/env python3
"""Postgres schema analyzer.

Extracts table definitions, FK relationships, indexes, stored functions,
and triggers from SQL migration files.  Constructs a cumulative schema by
parsing numbered migration files in order.

Usage:
    python scripts/analyze_postgres.py <migrations_directory> \
        [--live] [--output .architecture/postgres_analysis.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("analyze_postgres")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    default: str | None = None


@dataclass
class Table:
    name: str
    schema: str = "public"
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    file: str = ""
    line: int = 0


@dataclass
class ForeignKey:
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    constraint_name: str = ""
    on_delete: str = "NO ACTION"


@dataclass
class Index:
    name: str
    table: str
    columns: list[str]
    unique: bool = False


@dataclass
class StoredFunction:
    name: str
    file: str = ""
    line: int = 0
    language: str = "plpgsql"


@dataclass
class Trigger:
    name: str
    table: str
    event: str = ""
    timing: str = ""
    function: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIGRATION_NUM_RE = re.compile(r"^(\d+)")


def _sort_key(path: Path) -> tuple[int, str]:
    """Sort migration files by leading number, then alphabetically."""
    m = _MIGRATION_NUM_RE.match(path.name)
    return (int(m.group(1)) if m else 999999, path.name)


def _qualify(name: str, default_schema: str = "public") -> str:
    """Return schema-qualified table name."""
    if "." in name:
        return name.lower()
    return f"{default_schema}.{name}".lower()


def _strip_quotes(s: str) -> str:
    """Remove surrounding double-quotes from an identifier."""
    return s.strip().strip('"').strip("'")


def _parse_column_type(raw: str) -> tuple[str, bool, str | None]:
    """Parse a column definition fragment and return (type, nullable, default)."""
    raw = raw.strip()
    # Remove trailing comma
    raw = raw.rstrip(",").strip()

    nullable = True
    default = None

    # Extract DEFAULT value: handle function calls like NOW(), gen_random_uuid(),
    # quoted strings like '{}', type casts like '...'::JSONB, and simple literals.
    # The value is everything after DEFAULT until we hit a keyword boundary or end.
    default_match = re.search(
        r"\bDEFAULT\s+((?:'[^']*'(?:::\w+)?|\w+\([^)]*\)(?:::\w+)?|[^\s,]+))",
        raw,
        re.IGNORECASE,
    )
    if default_match:
        default = default_match.group(1).strip().rstrip(",").strip()

    # Determine nullability
    if re.search(r"\bNOT\s+NULL\b", raw, re.IGNORECASE):
        nullable = False
    if re.search(r"\bPRIMARY\s+KEY\b", raw, re.IGNORECASE):
        nullable = False

    # Extract the base type: everything up to the first keyword
    type_match = re.match(
        r"^([\w\s\[\]()]+?)(?:\s+(?:PRIMARY|NOT|NULL|DEFAULT|CHECK|REFERENCES|UNIQUE|GENERATED)\b|$)",
        raw,
        re.IGNORECASE,
    )
    col_type = type_match.group(1).strip() if type_match else raw.split()[0] if raw.split() else "unknown"
    # Collapse whitespace in type
    col_type = re.sub(r"\s+", " ", col_type).strip()

    return col_type, nullable, default


# ---------------------------------------------------------------------------
# SQL statement splitter
# ---------------------------------------------------------------------------

def _split_statements(sql: str) -> list[tuple[str, int]]:
    """Split SQL text into individual statements, respecting dollar-quoted
    strings, standard quotes, and block comments.  Returns (statement, line_number)
    tuples where line_number is 1-based."""
    statements: list[tuple[str, int]] = []
    current: list[str] = []
    line_start = 1
    i = 0
    chars = sql
    length = len(chars)
    line = 1

    while i < length:
        ch = chars[i]

        # Track newlines for line numbering
        if ch == "\n":
            line += 1

        # -- line comment
        if ch == "-" and i + 1 < length and chars[i + 1] == "-":
            end = chars.find("\n", i)
            if end == -1:
                end = length
            comment = chars[i:end]
            current.append(comment)
            i = end
            continue

        # /* block comment */
        if ch == "/" and i + 1 < length and chars[i + 1] == "*":
            end = chars.find("*/", i + 2)
            if end == -1:
                end = length
            else:
                end += 2
            block = chars[i:end]
            current.append(block)
            # Count newlines inside block comment
            line += block.count("\n")
            i = end
            continue

        # Dollar-quoted string  $tag$ ... $tag$
        if ch == "$":
            tag_match = re.match(r"\$(\w*)\$", chars[i:])
            if tag_match:
                tag = tag_match.group(0)  # e.g. $$ or $tag$
                end_pos = chars.find(tag, i + len(tag))
                if end_pos == -1:
                    # Unterminated dollar-quote, consume rest
                    fragment = chars[i:]
                    current.append(fragment)
                    line += fragment.count("\n")
                    i = length
                    continue
                end_pos += len(tag)
                fragment = chars[i:end_pos]
                current.append(fragment)
                line += fragment.count("\n")
                i = end_pos
                continue

        # Single-quoted string
        if ch == "'":
            j = i + 1
            while j < length:
                if chars[j] == "'" and j + 1 < length and chars[j + 1] == "'":
                    j += 2  # escaped quote
                elif chars[j] == "'":
                    j += 1
                    break
                else:
                    if chars[j] == "\n":
                        line += 1
                    j += 1
            else:
                j = length
            current.append(chars[i:j])
            i = j
            continue

        # Statement terminator
        if ch == ";":
            current.append(";")
            stmt_text = "".join(current).strip()
            if stmt_text and stmt_text != ";":
                statements.append((stmt_text, line_start))
            current = []
            line_start = line
            i += 1
            continue

        current.append(ch)
        i += 1

    # Remaining text (no trailing semicolon)
    remaining = "".join(current).strip()
    if remaining:
        statements.append((remaining, line_start))

    return statements


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SchemaParser:
    """Regex-based SQL migration parser."""

    def __init__(self) -> None:
        self.tables: dict[str, Table] = {}
        self.foreign_keys: list[ForeignKey] = []
        self.indexes: list[Index] = []
        self.functions: list[StoredFunction] = []
        self.triggers: list[Trigger] = []
        self._warnings: list[str] = []

    # -- public API ---------------------------------------------------------

    def parse_file(self, path: Path) -> None:
        """Parse a single migration file."""
        text = path.read_text(encoding="utf-8")
        filename = path.name
        stmts = _split_statements(text)

        for stmt, line_no in stmts:
            self._parse_statement(stmt, filename, line_no)

    # -- dispatchers --------------------------------------------------------

    @staticmethod
    def _strip_leading_comments(text: str) -> str:
        """Strip leading line comments and blank lines from a statement."""
        lines = text.split("\n")
        while lines:
            stripped_line = lines[0].strip()
            if stripped_line == "" or stripped_line.startswith("--"):
                lines.pop(0)
            else:
                break
        return "\n".join(lines).strip()

    def _parse_statement(self, stmt: str, filename: str, line: int) -> None:
        """Dispatch a single SQL statement to the appropriate handler."""
        # Strip leading comments so regex dispatch works on the SQL keyword
        stripped = self._strip_leading_comments(stmt.strip())
        upper = stripped.upper()

        try:
            if re.match(r"(?i)^CREATE\s+(TABLE|TABLE\s+IF\s+NOT\s+EXISTS)\b", stripped):
                self._parse_create_table(stripped, filename, line)
            elif re.match(r"(?i)^ALTER\s+TABLE\b", stripped):
                self._parse_alter_table(stripped, filename, line)
            elif re.match(r"(?i)^CREATE\s+(UNIQUE\s+)?INDEX\b", stripped):
                self._parse_create_index(stripped, filename, line)
            elif re.match(r"(?i)^CREATE\s+(OR\s+REPLACE\s+)?FUNCTION\b", stripped):
                self._parse_create_function(stripped, filename, line)
            elif re.match(r"(?i)^CREATE\s+TRIGGER\b", stripped):
                self._parse_create_trigger(stripped, filename, line)
            elif re.match(r"(?i)^DROP\s+TRIGGER\b", stripped):
                pass  # informational, nothing to extract
            elif re.match(r"(?i)^(DO\s*\$|CREATE\s+SCHEMA|CREATE\s+ROLE|GRANT|ALTER\s+DEFAULT|CREATE\s+POLICY|CREATE\s+PUBLICATION|ALTER\s+PUBLICATION|CREATE\s+TYPE|CREATE\s+OR\s+REPLACE\s+VIEW)\b", stripped):
                pass  # intentionally skipped, not part of required output
            else:
                # Unknown statement type - skip silently for common SQL
                if upper.startswith(("INSERT", "UPDATE", "DELETE", "SELECT", "SET", "COMMENT", "REVOKE", "REASSIGN", "NOTIFY", "LISTEN")):
                    pass
                else:
                    logger.debug("Skipping unrecognized statement in %s:%d: %.80s...", filename, line, stripped)
        except Exception as exc:
            logger.warning(
                "Could not parse statement in %s:%d – %s: %.120s",
                filename,
                line,
                exc,
                stripped,
            )

    # -- CREATE TABLE -------------------------------------------------------

    _CREATE_TABLE_RE = re.compile(
        r"(?i)^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\S+)\s*\((.*)\)\s*;?\s*$",
        re.DOTALL,
    )

    def _parse_create_table(self, stmt: str, filename: str, line: int) -> None:
        m = self._CREATE_TABLE_RE.match(stmt)
        if not m:
            logger.warning("Could not parse CREATE TABLE in %s:%d", filename, line)
            return

        raw_name = _strip_quotes(m.group(1))
        qualified = _qualify(raw_name)
        body = m.group(2)

        schema_part = qualified.rsplit(".", 1)[0] if "." in qualified else "public"
        table = Table(
            name=qualified,
            schema=schema_part,
            file=filename,
            line=line,
        )

        # Split body into segments, respecting parentheses depth
        segments = self._split_table_body(body)

        for seg in segments:
            seg_stripped = seg.strip()
            seg_upper = seg_stripped.upper()

            # Table-level PRIMARY KEY
            pk_match = re.match(
                r"(?i)^PRIMARY\s+KEY\s*\(([^)]+)\)",
                seg_stripped,
            )
            if pk_match:
                table.primary_key = [
                    _strip_quotes(c.strip())
                    for c in pk_match.group(1).split(",")
                ]
                continue

            # Table-level UNIQUE constraint
            if re.match(r"(?i)^UNIQUE\s*\(", seg_stripped):
                continue  # skip, not required in output

            # Table-level CONSTRAINT ... FOREIGN KEY
            fk_match = re.match(
                r"(?i)^(?:CONSTRAINT\s+(\S+)\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+(\S+)\s*\(([^)]+)\)(.*)$",
                seg_stripped,
                re.DOTALL,
            )
            if fk_match:
                constraint_name = _strip_quotes(fk_match.group(1)) if fk_match.group(1) else ""
                from_cols = [_strip_quotes(c.strip()) for c in fk_match.group(2).split(",")]
                to_table = _qualify(_strip_quotes(fk_match.group(3)))
                to_cols = [_strip_quotes(c.strip()) for c in fk_match.group(4).split(",")]
                on_delete = "NO ACTION"
                od_match = re.search(r"(?i)ON\s+DELETE\s+(\w+(?:\s+\w+)?)", fk_match.group(5))
                if od_match:
                    on_delete = od_match.group(1).upper()
                self.foreign_keys.append(ForeignKey(
                    from_table=qualified,
                    from_columns=from_cols,
                    to_table=to_table,
                    to_columns=to_cols,
                    constraint_name=constraint_name,
                    on_delete=on_delete,
                ))
                continue

            # Table-level CHECK constraint
            if re.match(r"(?i)^(?:CONSTRAINT\s+\S+\s+)?CHECK\s*\(", seg_stripped):
                continue

            # Column definition
            col = self._parse_column_def(seg_stripped, qualified)
            if col:
                table.columns.append(col)
                # Check for inline PRIMARY KEY
                if re.search(r"\bPRIMARY\s+KEY\b", seg_stripped, re.IGNORECASE):
                    if col.name not in table.primary_key:
                        table.primary_key.append(col.name)

        self.tables[qualified] = table

    def _split_table_body(self, body: str) -> list[str]:
        """Split CREATE TABLE body by commas, respecting parentheses depth,
        dollar/single-quoted strings, and line comments."""
        segments: list[str] = []
        current: list[str] = []
        depth = 0
        i = 0
        chars = body
        length = len(chars)

        while i < length:
            ch = chars[i]

            # Line comment: skip to end of line (do not include in output)
            if ch == "-" and i + 1 < length and chars[i + 1] == "-":
                end = chars.find("\n", i)
                if end == -1:
                    i = length
                else:
                    i = end + 1
                continue

            # Single-quoted string
            if ch == "'" and depth == 0:
                j = i + 1
                while j < length:
                    if chars[j] == "'" and j + 1 < length and chars[j + 1] == "'":
                        j += 2
                    elif chars[j] == "'":
                        j += 1
                        break
                    else:
                        j += 1
                else:
                    j = length
                current.append(chars[i:j])
                i = j
                continue

            # Dollar-quoted string
            if ch == "$":
                tag_match = re.match(r"\$(\w*)\$", chars[i:])
                if tag_match:
                    tag = tag_match.group(0)
                    end_pos = chars.find(tag, i + len(tag))
                    if end_pos == -1:
                        current.append(chars[i:])
                        i = length
                        continue
                    end_pos += len(tag)
                    current.append(chars[i:end_pos])
                    i = end_pos
                    continue

            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1

            if ch == "," and depth == 0:
                segments.append("".join(current))
                current = []
                i += 1
                continue

            current.append(ch)
            i += 1

        if current:
            segments.append("".join(current))

        return segments

    def _parse_column_def(self, seg: str, table_name: str) -> Column | None:
        """Parse a single column definition segment."""
        seg = seg.strip()
        if not seg:
            return None

        # Must start with an identifier (column name)
        # Column name can be a bare word or double-quoted
        col_match = re.match(r'^("(?:[^"]+)"|[a-zA-Z_]\w*)\s+(.*)', seg, re.DOTALL)
        if not col_match:
            return None

        col_name = _strip_quotes(col_match.group(1))
        rest = col_match.group(2).strip()

        # Skip if this looks like a constraint keyword rather than a type
        if rest.upper().startswith(("FOREIGN", "PRIMARY", "UNIQUE", "CHECK", "CONSTRAINT", "EXCLUDE")):
            return None

        col_type, nullable, default = _parse_column_type(rest)

        # Detect inline REFERENCES (inline FK)
        ref_match = re.search(
            r"\bREFERENCES\s+(\S+)\s*\(([^)]+)\)\s*(.*)",
            rest,
            re.IGNORECASE | re.DOTALL,
        )
        if ref_match:
            to_table = _qualify(_strip_quotes(ref_match.group(1)))
            to_cols = [_strip_quotes(c.strip()) for c in ref_match.group(2).split(",")]
            on_delete = "NO ACTION"
            od_match = re.search(r"(?i)ON\s+DELETE\s+(\w+(?:\s+\w+)?)", ref_match.group(3))
            if od_match:
                on_delete = od_match.group(1).upper()
            self.foreign_keys.append(ForeignKey(
                from_table=table_name,
                from_columns=[col_name],
                to_table=to_table,
                to_columns=to_cols,
                constraint_name="",
                on_delete=on_delete,
            ))

        return Column(name=col_name, type=col_type, nullable=nullable, default=default)

    # -- ALTER TABLE --------------------------------------------------------

    _ALTER_ADD_COLUMN_RE = re.compile(
        r"(?i)^ALTER\s+TABLE\s+(\S+)\s+(.+)$",
        re.DOTALL,
    )

    def _parse_alter_table(self, stmt: str, filename: str, line: int) -> None:
        m = self._ALTER_ADD_COLUMN_RE.match(stmt)
        if not m:
            return

        raw_name = _strip_quotes(m.group(1))
        qualified = _qualify(raw_name)
        actions = m.group(2).strip().rstrip(";").strip()

        # ALTER TABLE ... ENABLE ROW LEVEL SECURITY  (skip)
        if re.match(r"(?i)ENABLE\s+ROW\s+LEVEL\s+SECURITY", actions):
            return

        # ALTER TABLE ... DISABLE TRIGGER  (skip)
        if re.match(r"(?i)(ENABLE|DISABLE)\s+TRIGGER", actions):
            return

        # Handle ADD COLUMN (possibly multiple in one statement)
        # Pattern: ADD COLUMN col_name type ..., ADD COLUMN col_name type ...
        add_col_segments = re.split(r"(?i),\s*ADD\s+COLUMN\s+", actions)
        first_is_add_column = re.match(r"(?i)ADD\s+COLUMN\s+", add_col_segments[0])

        if first_is_add_column:
            # Strip the leading ADD COLUMN from the first segment
            add_col_segments[0] = re.sub(r"(?i)^ADD\s+COLUMN\s+", "", add_col_segments[0])

            table = self.tables.get(qualified)
            if not table:
                # Table was created in a prior migration we haven't seen,
                # or in a different schema; create a stub
                schema_part = qualified.rsplit(".", 1)[0] if "." in qualified else "public"
                table = Table(
                    name=qualified,
                    schema=schema_part,
                    file=filename,
                    line=line,
                )
                self.tables[qualified] = table

            for seg in add_col_segments:
                col = self._parse_column_def(seg.strip().rstrip(",").strip(), qualified)
                if col:
                    # Avoid duplicates when re-running
                    existing_names = {c.name for c in table.columns}
                    if col.name not in existing_names:
                        table.columns.append(col)
            return

        # Handle ADD CONSTRAINT ... FOREIGN KEY
        fk_match = re.match(
            r"(?i)ADD\s+CONSTRAINT\s+(\S+)\s+FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+(\S+)\s*\(([^)]+)\)(.*)",
            actions,
            re.DOTALL,
        )
        if fk_match:
            constraint_name = _strip_quotes(fk_match.group(1))
            from_cols = [_strip_quotes(c.strip()) for c in fk_match.group(2).split(",")]
            to_table = _qualify(_strip_quotes(fk_match.group(3)))
            to_cols = [_strip_quotes(c.strip()) for c in fk_match.group(4).split(",")]
            on_delete = "NO ACTION"
            od_match = re.search(r"(?i)ON\s+DELETE\s+(\w+(?:\s+\w+)?)", fk_match.group(5))
            if od_match:
                on_delete = od_match.group(1).upper()
            self.foreign_keys.append(ForeignKey(
                from_table=qualified,
                from_columns=from_cols,
                to_table=to_table,
                to_columns=to_cols,
                constraint_name=constraint_name,
                on_delete=on_delete,
            ))
            return

        # Other ALTER TABLE forms we skip silently
        logger.debug("Skipping ALTER TABLE action in %s:%d: %.80s", filename, line, actions)

    # -- CREATE INDEX -------------------------------------------------------

    _CREATE_INDEX_RE = re.compile(
        r"(?i)^CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>\S+)\s+ON\s+(?P<table>\S+)"
        r"(?:\s+USING\s+\w+)?"
        r"\s*\((?P<cols>[^)]+)\)",
        re.DOTALL,
    )

    def _parse_create_index(self, stmt: str, filename: str, line: int) -> None:
        m = self._CREATE_INDEX_RE.match(stmt)
        if not m:
            logger.warning("Could not parse CREATE INDEX in %s:%d", filename, line)
            return

        idx_name = _strip_quotes(m.group("name"))
        table_name = _qualify(_strip_quotes(m.group("table")))
        unique = m.group("unique") is not None
        raw_cols = m.group("cols")

        # Parse columns: handle expressions like (col1, col2) and functional exprs
        columns: list[str] = []
        for part in raw_cols.split(","):
            part = part.strip()
            if part:
                # For functional indexes, keep the expression; for simple ones, strip quotes
                columns.append(_strip_quotes(part) if re.match(r"^[\w\"]+$", part) else part.strip())

        self.indexes.append(Index(
            name=idx_name,
            table=table_name,
            columns=columns,
            unique=unique,
        ))

    # -- CREATE FUNCTION ----------------------------------------------------

    _CREATE_FUNC_RE = re.compile(
        r"(?i)^CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\S+)\s*\(",
    )

    _FUNC_LANGUAGE_RE = re.compile(
        r"(?i)\bLANGUAGE\s+(\w+)",
    )

    def _parse_create_function(self, stmt: str, filename: str, line: int) -> None:
        m = self._CREATE_FUNC_RE.match(stmt)
        if not m:
            logger.warning("Could not parse CREATE FUNCTION in %s:%d", filename, line)
            return

        func_name = _strip_quotes(m.group(1))
        # Qualify function name if it has a schema prefix
        if "." not in func_name:
            func_name = f"public.{func_name}"

        lang_match = self._FUNC_LANGUAGE_RE.search(stmt)
        language = lang_match.group(1).lower() if lang_match else "unknown"

        # Check for duplicate (CREATE OR REPLACE): update in place
        for existing in self.functions:
            if existing.name == func_name:
                existing.file = filename
                existing.line = line
                existing.language = language
                return

        self.functions.append(StoredFunction(
            name=func_name,
            file=filename,
            line=line,
            language=language,
        ))

    # -- CREATE TRIGGER -----------------------------------------------------

    _CREATE_TRIGGER_RE = re.compile(
        r"(?i)^CREATE\s+TRIGGER\s+(\S+)\s+"
        r"(BEFORE|AFTER|INSTEAD\s+OF)\s+"
        r"([\w\s]+?)\s+ON\s+(\S+)\s+"
        r".*?EXECUTE\s+(?:FUNCTION|PROCEDURE)\s+(\S+)",
        re.DOTALL,
    )

    def _parse_create_trigger(self, stmt: str, filename: str, line: int) -> None:
        m = self._CREATE_TRIGGER_RE.match(stmt)
        if not m:
            logger.warning("Could not parse CREATE TRIGGER in %s:%d", filename, line)
            return

        trigger_name = _strip_quotes(m.group(1))
        timing = m.group(2).strip().upper()
        events_raw = m.group(3).strip().upper()
        table_name = _qualify(_strip_quotes(m.group(4)))
        func_name = m.group(5).strip().rstrip(";").rstrip("()").strip()

        # Normalize events: "UPDATE OR DELETE" -> "UPDATE|DELETE"
        events = "|".join(
            e.strip() for e in re.split(r"\s+OR\s+", events_raw) if e.strip()
        )

        self.triggers.append(Trigger(
            name=trigger_name,
            table=table_name,
            event=events,
            timing=timing,
            function=func_name,
        ))

    # -- output -------------------------------------------------------------

    def build_output(self) -> dict[str, Any]:
        """Build the final JSON-serializable output dictionary."""
        tables_out = []
        for t in self.tables.values():
            tables_out.append({
                "name": t.name,
                "schema": t.schema,
                "columns": [
                    {
                        "name": c.name,
                        "type": c.type,
                        "nullable": c.nullable,
                        "default": c.default,
                    }
                    for c in t.columns
                ],
                "primary_key": t.primary_key,
                "file": t.file,
                "line": t.line,
            })

        fks_out = [
            {
                "from_table": fk.from_table,
                "from_columns": fk.from_columns,
                "to_table": fk.to_table,
                "to_columns": fk.to_columns,
                "constraint_name": fk.constraint_name,
                "on_delete": fk.on_delete,
            }
            for fk in self.foreign_keys
        ]

        indexes_out = [
            {
                "name": idx.name,
                "table": idx.table,
                "columns": idx.columns,
                "unique": idx.unique,
            }
            for idx in self.indexes
        ]

        functions_out = [
            {
                "name": fn.name,
                "file": fn.file,
                "line": fn.line,
                "language": fn.language,
            }
            for fn in self.functions
        ]

        triggers_out = [
            {
                "name": tr.name,
                "table": tr.table,
                "event": tr.event,
                "timing": tr.timing,
                "function": tr.function,
            }
            for tr in self.triggers
        ]

        # Build FK graph
        fk_graph = [
            {
                "from": fk.from_table,
                "to": fk.to_table,
                "columns": fk.from_columns,
            }
            for fk in self.foreign_keys
        ]

        # Summary
        total_columns = sum(len(t.columns) for t in self.tables.values())
        ref_counter: Counter[str] = Counter()
        for fk in self.foreign_keys:
            ref_counter[fk.to_table] += 1
        most_referenced = [
            {"table": tbl, "references": count}
            for tbl, count in ref_counter.most_common(10)
        ]
        widest = sorted(
            [{"table": t.name, "column_count": len(t.columns)} for t in self.tables.values()],
            key=lambda x: x["column_count"],
            reverse=True,
        )[:10]

        summary = {
            "total_tables": len(self.tables),
            "total_columns": total_columns,
            "total_foreign_keys": len(self.foreign_keys),
            "total_indexes": len(self.indexes),
            "most_referenced_tables": most_referenced,
            "widest_tables": widest,
        }

        return {
            "tables": tables_out,
            "foreign_keys": fks_out,
            "indexes": indexes_out,
            "stored_functions": functions_out,
            "triggers": triggers_out,
            "fk_graph": fk_graph,
            "summary": summary,
        }


# ---------------------------------------------------------------------------
# Live database mode
# ---------------------------------------------------------------------------

def _query_live_db(dsn: str | None = None) -> dict[str, Any]:
    """Query a live Postgres database for schema information.

    Uses psycopg2 if available.  Falls back gracefully if not installed.
    Connection parameters come from the DSN string or standard PG* env vars.
    """
    try:
        import psycopg2  # type: ignore[import-untyped]
        import psycopg2.extras  # type: ignore[import-untyped]
    except ImportError:
        logger.error(
            "psycopg2 is not installed. Install it with: pip install psycopg2-binary"
        )
        sys.exit(1)

    connect_kwargs: dict[str, Any] = {}
    if dsn:
        connect_kwargs["dsn"] = dsn
    # Otherwise psycopg2 reads PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

    conn = psycopg2.connect(**connect_kwargs)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Tables & columns
        cur.execute("""
            SELECT
                c.table_schema,
                c.table_name,
                c.column_name,
                c.data_type,
                c.udt_name,
                c.is_nullable,
                c.column_default
            FROM information_schema.columns c
            JOIN information_schema.tables t
                ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE t.table_type = 'BASE TABLE'
              AND c.table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """)

        tables_dict: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            qualified = f"{row['table_schema']}.{row['table_name']}"
            if qualified not in tables_dict:
                tables_dict[qualified] = {
                    "name": qualified,
                    "schema": row["table_schema"],
                    "columns": [],
                    "primary_key": [],
                    "file": "(live database)",
                    "line": 0,
                }
            tables_dict[qualified]["columns"].append({
                "name": row["column_name"],
                "type": row["udt_name"] or row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
            })

        # Primary keys
        cur.execute("""
            SELECT
                tc.table_schema || '.' || tc.table_name AS qualified_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY kcu.ordinal_position
        """)
        for row in cur.fetchall():
            qn = row["qualified_name"]
            if qn in tables_dict:
                tables_dict[qn]["primary_key"].append(row["column_name"])

        # Foreign keys
        cur.execute("""
            SELECT
                tc.constraint_name,
                tc.table_schema || '.' || tc.table_name AS from_table,
                kcu.column_name AS from_column,
                ccu.table_schema || '.' || ccu.table_name AS to_table,
                ccu.column_name AS to_column,
                rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
                AND tc.table_schema = rc.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
        """)
        fk_map: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            key = row["constraint_name"]
            if key not in fk_map:
                fk_map[key] = {
                    "from_table": row["from_table"],
                    "from_columns": [],
                    "to_table": row["to_table"],
                    "to_columns": [],
                    "constraint_name": row["constraint_name"],
                    "on_delete": row["delete_rule"].replace(" ", "_") if row["delete_rule"] else "NO ACTION",
                }
            fk_map[key]["from_columns"].append(row["from_column"])
            fk_map[key]["to_columns"].append(row["to_column"])

        # Indexes
        cur.execute("""
            SELECT
                i.relname AS index_name,
                n.nspname || '.' || t.relname AS table_name,
                ix.indisunique AS is_unique,
                array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) AS columns
            FROM pg_index ix
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND NOT ix.indisprimary
            GROUP BY i.relname, n.nspname, t.relname, ix.indisunique
            ORDER BY i.relname
        """)
        indexes_out = []
        for row in cur.fetchall():
            indexes_out.append({
                "name": row["index_name"],
                "table": row["table_name"],
                "columns": row["columns"],
                "unique": row["is_unique"],
            })

        # Functions
        cur.execute("""
            SELECT
                n.nspname || '.' || p.proname AS name,
                l.lanname AS language
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            JOIN pg_language l ON l.oid = p.prolang
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
              AND p.prokind = 'f'
            ORDER BY n.nspname, p.proname
        """)
        functions_out = [
            {"name": row["name"], "file": "(live database)", "line": 0, "language": row["language"]}
            for row in cur.fetchall()
        ]

        # Triggers
        cur.execute("""
            SELECT
                t.tgname AS trigger_name,
                n.nspname || '.' || c.relname AS table_name,
                CASE t.tgtype & 2 WHEN 2 THEN 'BEFORE' ELSE 'AFTER' END AS timing,
                CASE t.tgtype & 4 WHEN 4 THEN 'INSERT' ELSE '' END ||
                CASE t.tgtype & 8 WHEN 8 THEN '|DELETE' ELSE '' END ||
                CASE t.tgtype & 16 WHEN 16 THEN '|UPDATE' ELSE '' END AS event,
                pn.nspname || '.' || p.proname AS function_name
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_proc p ON p.oid = t.tgfoid
            JOIN pg_namespace pn ON pn.oid = p.pronamespace
            WHERE NOT t.tgisinternal
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        """)
        triggers_out = []
        for row in cur.fetchall():
            event = row["event"].strip("|")
            triggers_out.append({
                "name": row["trigger_name"],
                "table": row["table_name"],
                "event": event,
                "timing": row["timing"],
                "function": row["function_name"],
            })

        tables_out = list(tables_dict.values())
        fks_out = list(fk_map.values())

        # Build FK graph
        fk_graph = [
            {"from": fk["from_table"], "to": fk["to_table"], "columns": fk["from_columns"]}
            for fk in fks_out
        ]

        # Summary
        total_columns = sum(len(t["columns"]) for t in tables_out)
        ref_counter: Counter[str] = Counter()
        for fk in fks_out:
            ref_counter[fk["to_table"]] += 1
        most_referenced = [
            {"table": tbl, "references": count}
            for tbl, count in ref_counter.most_common(10)
        ]
        widest = sorted(
            [{"table": t["name"], "column_count": len(t["columns"])} for t in tables_out],
            key=lambda x: x["column_count"],
            reverse=True,
        )[:10]

        return {
            "tables": tables_out,
            "foreign_keys": fks_out,
            "indexes": indexes_out,
            "stored_functions": functions_out,
            "triggers": triggers_out,
            "fk_graph": fk_graph,
            "summary": {
                "total_tables": len(tables_out),
                "total_columns": total_columns,
                "total_foreign_keys": len(fks_out),
                "total_indexes": len(indexes_out),
                "most_referenced_tables": most_referenced,
                "widest_tables": widest,
            },
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Postgres schema from SQL migration files.",
    )
    parser.add_argument(
        "migrations_dir",
        type=str,
        help="Path to directory containing numbered .sql migration files",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Query a live database instead of parsing files (requires psycopg2 and PG* env vars or PGHOST)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON output to this file (default: stdout)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Determine mode
    use_live = args.live or bool(os.environ.get("PGHOST"))

    if use_live:
        logger.info("Using live database mode")
        result = _query_live_db()
    else:
        migrations_path = Path(args.migrations_dir)
        if not migrations_path.is_dir():
            logger.error("Migrations directory does not exist: %s", migrations_path)
            sys.exit(1)

        sql_files = sorted(migrations_path.glob("*.sql"), key=_sort_key)
        if not sql_files:
            logger.error("No .sql files found in %s", migrations_path)
            sys.exit(1)

        logger.info("Parsing %d migration files from %s", len(sql_files), migrations_path)

        schema_parser = SchemaParser()
        for sql_file in sql_files:
            logger.info("  Parsing %s", sql_file.name)
            schema_parser.parse_file(sql_file)

        result = schema_parser.build_output()

    # Output
    json_str = json.dumps(result, indent=2, default=str)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str + "\n", encoding="utf-8")
        logger.info("Wrote analysis to %s", output_path)
        # Also print summary to stderr
        s = result["summary"]
        print(
            f"Schema analysis complete: "
            f"{s['total_tables']} tables, "
            f"{s['total_columns']} columns, "
            f"{s['total_foreign_keys']} FKs, "
            f"{s['total_indexes']} indexes",
            file=sys.stderr,
        )
    else:
        print(json_str)


if __name__ == "__main__":
    main()
