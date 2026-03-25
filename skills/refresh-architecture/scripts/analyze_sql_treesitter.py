#!/usr/bin/env python3
"""Tree-sitter-based SQL migration analyzer.

Replaces the regex-based analyze_postgres.py with a proper CST parser.
Produces the same postgres_analysis.json schema for backward compatibility.

Usage:
    python scripts/analyze_sql_treesitter.py <migrations_directory> \
        [--output docs/architecture-analysis/postgres_analysis.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("analyze_sql_treesitter")

# ---------------------------------------------------------------------------
# Tree-sitter imports (graceful fallback)
# ---------------------------------------------------------------------------

try:
    from tree_sitter import Language, Node, Parser
    import tree_sitter_sql

    SQL_LANGUAGE = Language(tree_sitter_sql.language())
    TREESITTER_AVAILABLE = True
except ImportError:
    TREESITTER_AVAILABLE = False
    SQL_LANGUAGE = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Data classes (same as analyze_postgres.py for compatibility)
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
    parameters: list[dict[str, str]] = field(default_factory=list)
    return_type: str = ""
    referenced_tables: list[str] = field(default_factory=list)


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
    m = _MIGRATION_NUM_RE.match(path.name)
    return (int(m.group(1)) if m else 999999, path.name)


def _node_text(node: Node) -> str:
    """Get the text of a node as a string."""
    return node.text.decode("utf8") if node.text else ""


def _qualify(name: str) -> str:
    """Ensure a name is schema-qualified."""
    name = name.strip().strip('"').lower()
    if "." not in name:
        return f"public.{name}"
    return name


def _split_statements(sql: str) -> list[tuple[str, int]]:
    """Split SQL text into individual statements, respecting dollar-quoted
    strings, standard quotes, and block comments.  Returns (statement, line_number)
    tuples where line_number is 1-based.

    Replicates the logic from analyze_postgres.py to ensure consistency.
    """
    statements: list[tuple[str, int]] = []
    current: list[str] = []
    line_start = 1
    i = 0
    length = len(sql)
    line = 1

    while i < length:
        ch = sql[i]

        if ch == "\n":
            line += 1

        # -- line comment
        if ch == "-" and i + 1 < length and sql[i + 1] == "-":
            end = sql.find("\n", i)
            if end == -1:
                end = length
            current.append(sql[i:end])
            i = end
            continue

        # /* block comment */
        if ch == "/" and i + 1 < length and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            if end == -1:
                end = length
            else:
                end += 2
            block = sql[i:end]
            current.append(block)
            line += block.count("\n")
            i = end
            continue

        # Dollar-quoted string  $tag$ ... $tag$
        if ch == "$":
            tag_match = re.match(r"\$(\w*)\$", sql[i:])
            if tag_match:
                tag = tag_match.group(0)
                end_pos = sql.find(tag, i + len(tag))
                if end_pos == -1:
                    fragment = sql[i:]
                    current.append(fragment)
                    line += fragment.count("\n")
                    i = length
                    continue
                end_pos += len(tag)
                fragment = sql[i:end_pos]
                current.append(fragment)
                line += fragment.count("\n")
                i = end_pos
                continue

        # Single-quoted string
        if ch == "'":
            j = i + 1
            while j < length:
                if sql[j] == "'" and j + 1 < length and sql[j + 1] == "'":
                    j += 2
                elif sql[j] == "'":
                    j += 1
                    break
                else:
                    if sql[j] == "\n":
                        line += 1
                    j += 1
            else:
                j = length
            current.append(sql[i:j])
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

    remaining = "".join(current).strip()
    if remaining:
        statements.append((remaining, line_start))

    return statements


def _object_ref_name(node: Node) -> str:
    """Extract a qualified name from an object_reference node."""
    parts = [_node_text(c) for c in node.children if c.type == "identifier"]
    return ".".join(parts).lower() if parts else _node_text(node).lower()


def _children_of_type(node: Node, *types: str) -> list[Node]:
    """Get all children matching any of the given types."""
    return [c for c in node.children if c.type in types]


def _has_child_type(node: Node, *types: str) -> bool:
    """Check if node has a child of given type."""
    return any(c.type in types for c in node.children)


def _extract_column_type(col_def: Node) -> str:
    """Extract the SQL type from a column_definition node.

    Type keywords appear as children like keyword_uuid, keyword_text, int,
    keyword_timestamptz, etc. We collect them until we hit a non-type node.
    """
    type_keywords = set()
    for kw in ["keyword_uuid", "keyword_text", "keyword_int", "keyword_integer",
               "keyword_bigint", "keyword_smallint", "keyword_boolean", "keyword_bool",
               "keyword_float", "keyword_real", "keyword_double", "keyword_numeric",
               "keyword_decimal", "keyword_serial", "keyword_bigserial",
               "keyword_varchar", "keyword_char", "keyword_character",
               "keyword_timestamp", "keyword_timestamptz", "keyword_date",
               "keyword_time", "keyword_interval", "keyword_json", "keyword_jsonb",
               "keyword_bytea", "keyword_xml", "keyword_trigger",
               "int", "bigint", "smallint", "float", "double"]:
        type_keywords.add(kw)

    type_parts = []
    skip_next = False
    for child in col_def.children:
        if child.type == "identifier" and not type_parts:
            # First identifier is column name, skip
            continue
        if child.type in type_keywords:
            type_parts.append(_node_text(child).upper())
        elif child.type == "keyword_varying":
            type_parts.append("VARYING")
        elif child.type == "keyword_precision":
            type_parts.append("PRECISION")
        elif child.type == "keyword_with" and not type_parts:
            continue
        elif child.type == "keyword_time" and "keyword_zone" in {c.type for c in col_def.children}:
            type_parts.append("TIME")
        elif type_parts and child.type in ("(", ")"):
            # Part of type like VARCHAR(255)
            type_parts.append(_node_text(child))
        elif type_parts and child.type == "literal" and type_parts[-1] == "(":
            type_parts.append(_node_text(child))
        elif type_parts:
            break

    if type_parts:
        return " ".join(type_parts)

    # Fallback: look for any type-like token after the identifier
    found_name = False
    for child in col_def.children:
        if child.type == "identifier" and not found_name:
            found_name = True
            continue
        if found_name and child.type not in (
            "keyword_not", "keyword_null", "keyword_default",
            "keyword_primary", "keyword_key", "keyword_references",
            "keyword_unique", "keyword_check", "keyword_on",
            "keyword_delete", "keyword_cascade", "keyword_restrict",
            "keyword_set", "keyword_action", "keyword_no",
            "literal", "invocation", "object_reference",
            ",", "(", ")", "keyword_constraint",
        ):
            return _node_text(child).upper()

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# CST Parser
# ---------------------------------------------------------------------------


class TreeSitterSchemaParser:
    """Parse SQL migrations using tree-sitter CST."""

    def __init__(self) -> None:
        if not TREESITTER_AVAILABLE:
            raise RuntimeError("tree-sitter is not installed")
        self.parser = Parser(SQL_LANGUAGE)
        self.tables: dict[str, Table] = {}
        self.foreign_keys: list[ForeignKey] = []
        self.indexes: list[Index] = []
        self.functions: list[StoredFunction] = []
        self.triggers: list[Trigger] = []

    def parse_directory(self, migrations_dir: Path) -> None:
        """Parse all SQL files in a migrations directory in order."""
        if not migrations_dir.is_dir():
            logger.error("Migrations directory not found: %s", migrations_dir)
            return

        sql_files = sorted(migrations_dir.glob("*.sql"), key=_sort_key)
        if not sql_files:
            logger.warning("No .sql files found in %s", migrations_dir)
            return

        for sql_file in sql_files:
            self._parse_file(sql_file)

    def _parse_file(self, path: Path) -> None:
        """Parse a single SQL file by splitting into individual statements.

        The tree-sitter SQL grammar is generic SQL and struggles with some
        PostgreSQL extensions (CHECK constraints, array types, POLICY statements).
        By parsing each statement individually, errors in one statement don't
        cascade and prevent later statements from being parsed.
        """
        try:
            source = path.read_text()
        except OSError as e:
            logger.warning("Could not read %s: %s", path, e)
            return

        filename = path.name
        statements = _split_statements(source)

        for stmt_text, stmt_line in statements:
            tree = self.parser.parse(stmt_text.encode("utf8"))
            root = tree.root_node

            if root.has_error:
                # Tree has errors but may still have useful nodes — try to extract
                pass

            for child in root.children:
                if child.type == "statement":
                    inner = child.children[0] if child.children else child
                    self._dispatch_statement(inner, filename, stmt_line)
                elif child.type == "ERROR":
                    # Top-level ERROR node (not inside a statement)
                    self._dispatch_statement(child, filename, stmt_line)

    def _dispatch_statement(self, node: Node, filename: str, line: int) -> None:
        """Route a statement node to the appropriate handler."""
        handlers = {
            "create_table": self._parse_create_table,
            "alter_table": self._parse_alter_table,
            "create_index": self._parse_create_index,
            "create_function": self._parse_create_function,
            "create_trigger": self._parse_create_trigger,
        }
        handler = handlers.get(node.type)
        if handler:
            handler(node, filename, line)
        elif node.type == "ERROR":
            # tree-sitter may produce ERROR nodes for valid PostgreSQL that
            # uses extensions the generic SQL grammar doesn't support (array
            # types, PL/pgSQL assignment, etc). Try to recover by checking
            # what keywords are present.
            self._try_recover_error_node(node, filename, line)

    def _try_recover_error_node(self, node: Node, filename: str, line: int) -> None:
        """Attempt to extract useful information from an ERROR node."""
        has_create = _has_child_type(node, "keyword_create")
        has_function_kw = _has_child_type(node, "keyword_function")
        has_trigger_kw = _has_child_type(node, "keyword_trigger")
        has_table = _has_child_type(node, "keyword_table")
        has_index = _has_child_type(node, "keyword_index")

        # Distinguish CREATE FUNCTION ... RETURNS TRIGGER from CREATE TRIGGER
        # by checking whether keyword_trigger appears before or after keyword_function
        is_create_trigger = False
        is_create_function = False
        if has_create and has_function_kw:
            # Look at order of keywords to distinguish
            # CREATE FUNCTION ... RETURNS TRIGGER → function_kw comes first
            # CREATE TRIGGER ... EXECUTE FUNCTION → trigger_kw comes first
            for child in node.children:
                if child.type == "keyword_function":
                    is_create_function = True
                    break
                elif child.type == "keyword_trigger":
                    is_create_trigger = True
                    break
        elif has_create and has_trigger_kw:
            is_create_trigger = True

        if is_create_function:
            self._parse_create_function(node, filename, line)
        elif is_create_trigger:
            self._parse_create_trigger(node, filename, line)
        elif has_create and has_index:
            self._parse_create_index(node, filename, line)
        elif has_create and has_table:
            self._parse_create_table(node, filename, line)

    # -- CREATE TABLE -------------------------------------------------------

    def _parse_create_table(self, node: Node, filename: str, line: int) -> None:
        obj_refs = _children_of_type(node, "object_reference")
        if not obj_refs:
            logger.warning("CREATE TABLE without table name at %s:%d", filename, line)
            return

        table_name = _qualify(_object_ref_name(obj_refs[0]))
        schema = table_name.split(".")[0] if "." in table_name else "public"

        table = Table(
            name=table_name,
            schema=schema,
            file=filename,
            line=line,
        )

        col_defs_node = None
        for child in node.children:
            if child.type == "column_definitions":
                col_defs_node = child
                break

        if col_defs_node:
            self._parse_column_definitions(col_defs_node, table)

        self.tables[table_name] = table

    def _parse_column_definitions(self, node: Node, table: Table) -> None:
        """Parse column_definitions node to extract columns, inline PKs, and FKs."""
        for child in node.children:
            if child.type == "column_definition":
                self._parse_column_def(child, table)
            elif child.type == "constraint":
                self._parse_table_constraint(child, table)

    def _parse_column_def(self, node: Node, table: Table) -> None:
        """Parse a single column_definition node."""
        identifiers = _children_of_type(node, "identifier")
        if not identifiers:
            return

        col_name = _node_text(identifiers[0]).lower().strip('"')
        col_type = _extract_column_type(node)

        # Check NOT NULL
        nullable = True
        has_not = _has_child_type(node, "keyword_not")
        has_null = _has_child_type(node, "keyword_null")
        if has_not and has_null:
            nullable = False

        # Check PRIMARY KEY (inline) — implies NOT NULL
        if _has_child_type(node, "keyword_primary"):
            nullable = False
            if col_name not in table.primary_key:
                table.primary_key.append(col_name)

        # Check DEFAULT
        default_val = None
        found_default = False
        for child in node.children:
            if child.type == "keyword_default":
                found_default = True
            elif found_default:
                if child.type in ("literal", "invocation", "identifier", "keyword_true",
                                  "keyword_false", "keyword_null"):
                    default_val = _node_text(child)
                    break
                elif child.type in ("keyword_not", "keyword_primary", "keyword_references",
                                    "keyword_unique", "keyword_check"):
                    break
                else:
                    default_val = _node_text(child)
                    break

        table.columns.append(Column(
            name=col_name,
            type=col_type,
            nullable=nullable,
            default=default_val,
        ))

        # Check inline REFERENCES (FK)
        if _has_child_type(node, "keyword_references"):
            self._parse_inline_fk(node, table.name, col_name)

    def _parse_inline_fk(self, node: Node, from_table: str, from_col: str) -> None:
        """Parse an inline REFERENCES clause on a column definition."""
        ref_table = ""
        ref_cols: list[str] = []
        on_delete = "NO ACTION"

        found_references = False
        for child in node.children:
            if child.type == "keyword_references":
                found_references = True
            elif found_references and child.type == "object_reference":
                ref_table = _qualify(_object_ref_name(child))
            elif found_references and child.type == "identifier" and ref_table:
                ref_cols.append(_node_text(child).lower().strip('"'))
            elif child.type == "keyword_cascade":
                on_delete = "CASCADE"
            elif child.type == "keyword_restrict":
                on_delete = "RESTRICT"

        if ref_table:
            if not ref_cols:
                ref_cols = ["id"]  # Default FK target
            self.foreign_keys.append(ForeignKey(
                from_table=from_table,
                from_columns=[from_col],
                to_table=ref_table,
                to_columns=ref_cols,
                on_delete=on_delete,
            ))

    def _parse_table_constraint(self, node: Node, table: Table) -> None:
        """Parse a table-level constraint (PRIMARY KEY or FOREIGN KEY)."""
        if _has_child_type(node, "keyword_primary"):
            # PRIMARY KEY constraint
            cols = self._extract_ordered_columns(node)
            table.primary_key = cols
        elif _has_child_type(node, "keyword_foreign"):
            self._parse_table_fk_constraint(node, table.name)

    def _parse_table_fk_constraint(
        self, node: Node, from_table: str, constraint_name: str = ""
    ) -> None:
        """Parse a table-level FOREIGN KEY constraint."""
        from_cols: list[str] = []
        to_table = ""
        to_cols: list[str] = []
        on_delete = "NO ACTION"

        # Extract ordered_columns (FK columns)
        ordered = _children_of_type(node, "ordered_columns")
        if ordered:
            from_cols = self._extract_column_names_from_ordered(ordered[0])

        # Extract REFERENCES target
        found_references = False
        for child in node.children:
            if child.type == "keyword_references":
                found_references = True
            elif found_references and child.type == "object_reference":
                to_table = _qualify(_object_ref_name(child))
            elif found_references and child.type == "identifier" and to_table:
                to_cols.append(_node_text(child).lower().strip('"'))
            elif child.type == "keyword_cascade":
                on_delete = "CASCADE"
            elif child.type == "keyword_restrict":
                on_delete = "RESTRICT"

        if to_table and from_cols:
            if not to_cols:
                to_cols = ["id"]
            self.foreign_keys.append(ForeignKey(
                from_table=from_table,
                from_columns=from_cols,
                to_table=to_table,
                to_columns=to_cols,
                constraint_name=constraint_name,
                on_delete=on_delete,
            ))

    def _extract_ordered_columns(self, node: Node) -> list[str]:
        """Extract column names from ordered_columns or similar node."""
        cols = []
        for child in node.children:
            if child.type == "ordered_columns":
                return self._extract_column_names_from_ordered(child)
            elif child.type == "identifier":
                cols.append(_node_text(child).lower().strip('"'))
        return cols

    def _extract_column_names_from_ordered(self, node: Node) -> list[str]:
        """Extract column names from an ordered_columns node like (col1, col2)."""
        cols = []
        for child in node.children:
            if child.type == "identifier":
                cols.append(_node_text(child).lower().strip('"'))
            elif child.type == "column":
                # In some tree-sitter versions, columns are wrapped in a "column" node
                text = _node_text(child).lower().strip('"')
                if text:
                    cols.append(text)
        return cols

    # -- ALTER TABLE --------------------------------------------------------

    def _parse_alter_table(self, node: Node, filename: str, line: int) -> None:
        obj_refs = _children_of_type(node, "object_reference")
        if not obj_refs:
            return

        table_name = _qualify(_object_ref_name(obj_refs[0]))

        for child in node.children:
            if child.type == "add_column":
                self._parse_add_column(child, table_name)
            elif child.type == "add_constraint":
                self._parse_add_constraint(child, table_name)

    def _parse_add_column(self, node: Node, table_name: str) -> None:
        col_defs = _children_of_type(node, "column_definition")
        table = self.tables.get(table_name)
        if not table:
            # Table may be defined in a later migration or not in scope
            table = Table(name=table_name, schema=table_name.split(".")[0])
            self.tables[table_name] = table

        for col_def in col_defs:
            self._parse_column_def(col_def, table)

    def _parse_add_constraint(self, node: Node, table_name: str) -> None:
        constraint_name = ""
        constraint_node = None

        for child in node.children:
            if child.type == "identifier":
                constraint_name = _node_text(child).lower().strip('"')
            elif child.type == "constraint":
                constraint_node = child

        if constraint_node:
            if _has_child_type(constraint_node, "keyword_foreign"):
                self._parse_table_fk_constraint(
                    constraint_node, table_name, constraint_name
                )
            elif _has_child_type(constraint_node, "keyword_primary"):
                table = self.tables.get(table_name)
                if table:
                    cols = self._extract_ordered_columns(constraint_node)
                    table.primary_key = cols

    # -- CREATE INDEX -------------------------------------------------------

    def _parse_create_index(self, node: Node, filename: str, line: int) -> None:
        unique = _has_child_type(node, "keyword_unique")

        # Index name
        idx_name = ""
        identifiers = _children_of_type(node, "identifier")
        if identifiers:
            idx_name = _node_text(identifiers[0]).lower().strip('"')

        # Table name (object_reference after ON)
        obj_refs = _children_of_type(node, "object_reference")
        table_name = ""
        if obj_refs:
            table_name = _qualify(_object_ref_name(obj_refs[0]))

        # Index columns
        columns: list[str] = []
        index_fields = _children_of_type(node, "index_fields")
        if index_fields:
            for child in index_fields[0].children:
                if child.type == "field":
                    text = _node_text(child).strip()
                    # For simple identifiers, lowercase; for expressions, keep as-is
                    ident = _children_of_type(child, "identifier")
                    if ident and len(ident) == 1 and _node_text(ident[0]).strip() == text:
                        columns.append(text.lower().strip('"'))
                    else:
                        columns.append(text)

        if idx_name and table_name:
            self.indexes.append(Index(
                name=idx_name,
                table=table_name,
                columns=columns,
                unique=unique,
            ))

    # -- CREATE FUNCTION ----------------------------------------------------

    def _parse_create_function(self, node: Node, filename: str, line: int) -> None:
        # Function name
        obj_refs = _children_of_type(node, "object_reference")
        if not obj_refs:
            return
        func_name = _qualify(_object_ref_name(obj_refs[0]))

        # Language — may be in a function_language node or directly as keyword_language + identifier
        language = "unknown"
        lang_nodes = _children_of_type(node, "function_language")
        if lang_nodes:
            idents = _children_of_type(lang_nodes[0], "identifier")
            if idents:
                language = _node_text(idents[0]).lower()
        else:
            # In ERROR nodes, LANGUAGE keyword may be a direct child
            found_lang_kw = False
            for child in node.children:
                if child.type == "keyword_language":
                    found_lang_kw = True
                elif found_lang_kw and child.type == "identifier":
                    language = _node_text(child).lower()
                    break
                elif found_lang_kw:
                    break
            if found_lang_kw and language == "unknown":
                # In deeply broken ERROR nodes, the language identifier may not
                # appear as a child. Fall back to regex on the raw node text.
                lang_match = re.search(
                    r"(?i)\bLANGUAGE\s+(\w+)", _node_text(node)
                )
                if lang_match:
                    language = lang_match.group(1).lower()

        # Return type
        return_type = ""
        found_returns = False
        for child in node.children:
            if child.type == "keyword_returns":
                found_returns = True
            elif found_returns:
                if child.type in ("keyword_trigger", "keyword_void"):
                    return_type = _node_text(child).lower()
                elif child.type == "keyword_setof":
                    return_type = "SETOF"
                elif child.type == "object_reference":
                    prefix = f"{return_type} " if return_type else ""
                    return_type = f"{prefix}{_object_ref_name(child)}".strip()
                elif child.type in ("identifier",):
                    prefix = f"{return_type} " if return_type else ""
                    return_type = f"{prefix}{_node_text(child).lower()}".strip()
                elif child.type.startswith("keyword_"):
                    # Type keyword like keyword_uuid, keyword_text, etc.
                    prefix = f"{return_type} " if return_type else ""
                    return_type = f"{prefix}{_node_text(child).lower()}".strip()
                else:
                    break

        # Parameters
        parameters: list[dict[str, str]] = []
        func_args = _children_of_type(node, "function_arguments")
        if func_args:
            self._extract_function_params(func_args[0], parameters)

        # Referenced tables from function body
        referenced_tables: list[str] = []
        body_nodes = _children_of_type(node, "function_body")
        if body_nodes:
            body_text = _node_text(body_nodes[0])
            referenced_tables = self._extract_table_refs_from_body(body_text)
        else:
            # In ERROR nodes, extract body text between dollar_quote markers
            dollar_quotes = _children_of_type(node, "dollar_quote")
            if len(dollar_quotes) >= 2:
                start = dollar_quotes[0].end_byte
                end = dollar_quotes[1].start_byte
                body_bytes = node.text[start - node.start_byte:end - node.start_byte]
                if body_bytes:
                    referenced_tables = self._extract_table_refs_from_body(
                        body_bytes.decode("utf8", errors="replace")
                    )

        # Check for duplicate (CREATE OR REPLACE)
        for existing in self.functions:
            if existing.name == func_name:
                existing.file = filename
                existing.line = line
                existing.language = language
                existing.parameters = parameters
                existing.return_type = return_type
                existing.referenced_tables = referenced_tables
                return

        self.functions.append(StoredFunction(
            name=func_name,
            file=filename,
            line=line,
            language=language,
            parameters=parameters,
            return_type=return_type,
            referenced_tables=referenced_tables,
        ))

    def _extract_function_params(
        self, node: Node, params: list[dict[str, str]]
    ) -> None:
        """Extract parameters from function_arguments node."""
        # Parameters appear as identifier pairs (name type) or just (type)
        children = [c for c in node.children if c.type not in ("(", ")", ",")]
        i = 0
        while i < len(children):
            child = children[i]
            if child.type == "identifier":
                name = _node_text(child).lower()
                # Next child might be the type
                if i + 1 < len(children):
                    next_child = children[i + 1]
                    type_text = _node_text(next_child).upper()
                    params.append({"name": name, "type": type_text})
                    i += 2
                else:
                    params.append({"name": "", "type": name.upper()})
                    i += 1
            else:
                type_text = _node_text(child).upper()
                params.append({"name": "", "type": type_text})
                i += 1

    _TABLE_REF_RE = re.compile(
        r"(?i)\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+([a-z_]\w*(?:\.[a-z_]\w*)?)\b"
    )

    def _extract_table_refs_from_body(self, body_text: str) -> list[str]:
        """Extract table references from a PL/pgSQL function body."""
        refs = set()
        for match in self._TABLE_REF_RE.finditer(body_text):
            name = _qualify(match.group(1))
            refs.add(name)
        return sorted(refs)

    # -- CREATE TRIGGER -----------------------------------------------------

    def _parse_create_trigger(self, node: Node, filename: str, line: int) -> None:
        obj_refs = _children_of_type(node, "object_reference")
        if len(obj_refs) < 2:
            logger.warning("CREATE TRIGGER: not enough references at %s:%d", filename, line)
            return

        trigger_name = _node_text(obj_refs[0]).lower().strip('"')
        table_name = _qualify(_object_ref_name(obj_refs[1]))

        # Timing (BEFORE / AFTER / INSTEAD OF)
        timing = ""
        for kw in ("keyword_before", "keyword_after", "keyword_instead"):
            if _has_child_type(node, kw):
                timing = kw.replace("keyword_", "").upper()
                break

        # Events (INSERT / UPDATE / DELETE)
        events = []
        for kw in ("keyword_insert", "keyword_update", "keyword_delete", "keyword_truncate"):
            if _has_child_type(node, kw):
                events.append(kw.replace("keyword_", "").upper())

        # Function reference (after EXECUTE FUNCTION/PROCEDURE)
        func_name = ""
        if len(obj_refs) >= 3:
            func_name = _qualify(_object_ref_name(obj_refs[2]))

        self.triggers.append(Trigger(
            name=trigger_name,
            table=table_name,
            event="|".join(events),
            timing=timing,
            function=func_name,
        ))

    # -- Output -------------------------------------------------------------

    def build_output(self) -> dict[str, Any]:
        """Build the final JSON-serializable output (same schema as analyze_postgres.py)."""
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
                "parameters": fn.parameters,
                "return_type": fn.return_type,
                "referenced_tables": fn.referenced_tables,
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

        fk_graph = [
            {
                "from": fk.from_table,
                "to": fk.to_table,
                "columns": fk.from_columns,
            }
            for fk in self.foreign_keys
        ]

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
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tree-sitter-based SQL migration analyzer.",
    )
    parser.add_argument(
        "migrations_dir",
        type=Path,
        help="Directory containing numbered SQL migration files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/architecture-analysis/postgres_analysis.json"),
        help="Output path (default: docs/architecture-analysis/postgres_analysis.json)",
    )
    parser.add_argument(
        "--schema",
        default="public",
        help="Default schema name (default: public)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    if not TREESITTER_AVAILABLE:
        logger.error(
            "tree-sitter is not installed. "
            "Run 'cd scripts && uv sync' to install dependencies."
        )
        return 1

    schema_parser = TreeSitterSchemaParser()
    schema_parser.parse_directory(args.migrations_dir)
    output = schema_parser.build_output()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    logger.info(
        "Tree-sitter SQL analysis complete: %d tables, %d FKs, %d indexes, "
        "%d functions, %d triggers",
        output["summary"]["total_tables"],
        output["summary"]["total_foreign_keys"],
        output["summary"]["total_indexes"],
        len(output["stored_functions"]),
        len(output["triggers"]),
    )
    logger.info("Wrote %s", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
