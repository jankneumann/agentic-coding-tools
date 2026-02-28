"""Tests for the tree-sitter SQL migration analyzer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure scripts/ is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from analyze_sql_treesitter import (
    TREESITTER_AVAILABLE,
    TreeSitterSchemaParser,
    _qualify,
    _split_statements,
)

pytestmark = pytest.mark.skipif(
    not TREESITTER_AVAILABLE,
    reason="tree-sitter not installed",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser() -> TreeSitterSchemaParser:
    return TreeSitterSchemaParser()


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Create a temp directory with SQL migration files."""
    d = tmp_path / "migrations"
    d.mkdir()
    return d


def write_migration(migrations_dir: Path, name: str, content: str) -> Path:
    p = migrations_dir / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# _qualify
# ---------------------------------------------------------------------------


class TestQualify:
    def test_unqualified(self) -> None:
        assert _qualify("users") == "public.users"

    def test_qualified(self) -> None:
        assert _qualify("auth.users") == "auth.users"

    def test_strips_quotes(self) -> None:
        assert _qualify('"Users"') == "public.users"


# ---------------------------------------------------------------------------
# _split_statements
# ---------------------------------------------------------------------------


class TestSplitStatements:
    def test_simple(self) -> None:
        stmts = _split_statements("SELECT 1; SELECT 2;")
        assert len(stmts) == 2
        assert stmts[0][0] == "SELECT 1;"
        assert stmts[1][0] == "SELECT 2;"

    def test_dollar_quoted(self) -> None:
        sql = "CREATE FUNCTION f() AS $$ BEGIN END; $$ LANGUAGE plpgsql;"
        stmts = _split_statements(sql)
        assert len(stmts) == 1

    def test_line_comments(self) -> None:
        sql = "-- comment\nSELECT 1;"
        stmts = _split_statements(sql)
        assert len(stmts) == 1

    def test_line_numbers(self) -> None:
        sql = "\nSELECT 1;\n\nSELECT 2;"
        stmts = _split_statements(sql)
        assert stmts[0][1] == 1
        # Second statement starts after the second newline (line_start is set
        # to the current line when the semicolon is consumed)
        assert stmts[1][1] == 2


# ---------------------------------------------------------------------------
# CREATE TABLE
# ---------------------------------------------------------------------------


class TestCreateTable:
    def test_basic_table(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE users (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT DEFAULT 'unknown'
            );
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["tables"]) == 1
        table = output["tables"][0]
        assert table["name"] == "public.users"
        assert table["schema"] == "public"
        assert table["primary_key"] == ["id"]
        assert len(table["columns"]) == 3

        id_col = table["columns"][0]
        assert id_col["name"] == "id"
        assert id_col["nullable"] is False  # PK implies NOT NULL

        name_col = table["columns"][1]
        assert name_col["name"] == "name"
        assert name_col["nullable"] is False

        email_col = table["columns"][2]
        assert email_col["name"] == "email"
        assert email_col["nullable"] is True
        assert email_col["default"] == "'unknown'"

    def test_schema_qualified(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE auth.roles (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            );
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert output["tables"][0]["name"] == "auth.roles"
        assert output["tables"][0]["schema"] == "auth"

    def test_if_not_exists(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE IF NOT EXISTS configs (
                key TEXT PRIMARY KEY,
                value JSONB
            );
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()
        assert len(output["tables"]) == 1
        assert output["tables"][0]["name"] == "public.configs"

    def test_inline_foreign_key(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE departments (id UUID PRIMARY KEY);
            CREATE TABLE employees (
                id UUID PRIMARY KEY,
                dept_id UUID REFERENCES departments(id) ON DELETE CASCADE
            );
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["foreign_keys"]) == 1
        fk = output["foreign_keys"][0]
        assert fk["from_table"] == "public.employees"
        assert fk["from_columns"] == ["dept_id"]
        assert fk["to_table"] == "public.departments"
        assert fk["to_columns"] == ["id"]
        assert fk["on_delete"] == "CASCADE"


# ---------------------------------------------------------------------------
# ALTER TABLE
# ---------------------------------------------------------------------------


class TestAlterTable:
    def test_add_column(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", "CREATE TABLE users (id UUID PRIMARY KEY);")
        write_migration(migrations_dir, "002.sql", """
            ALTER TABLE users ADD COLUMN email TEXT DEFAULT NULL;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        table = output["tables"][0]
        assert len(table["columns"]) == 2
        assert table["columns"][1]["name"] == "email"

    def test_add_foreign_key_constraint(
        self, parser: TreeSitterSchemaParser, migrations_dir: Path
    ) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE parents (id UUID PRIMARY KEY);
            CREATE TABLE children (id UUID PRIMARY KEY, parent_id UUID);
        """)
        write_migration(migrations_dir, "002.sql", """
            ALTER TABLE children ADD CONSTRAINT fk_parent
            FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE CASCADE;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["foreign_keys"]) == 1
        fk = output["foreign_keys"][0]
        assert fk["constraint_name"] == "fk_parent"
        assert fk["from_table"] == "public.children"
        assert fk["to_table"] == "public.parents"
        assert fk["on_delete"] == "CASCADE"


# ---------------------------------------------------------------------------
# CREATE INDEX
# ---------------------------------------------------------------------------


class TestCreateIndex:
    def test_simple_index(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE users (id UUID PRIMARY KEY, email TEXT);
            CREATE INDEX idx_users_email ON users (email);
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["indexes"]) == 1
        idx = output["indexes"][0]
        assert idx["name"] == "idx_users_email"
        assert idx["table"] == "public.users"
        assert idx["columns"] == ["email"]
        assert idx["unique"] is False

    def test_unique_index(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE users (id UUID PRIMARY KEY, email TEXT);
            CREATE UNIQUE INDEX idx_users_email ON users (email);
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert output["indexes"][0]["unique"] is True

    def test_composite_index(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE logs (id UUID PRIMARY KEY, level TEXT, ts TIMESTAMPTZ);
            CREATE INDEX idx_logs_level_ts ON logs (level, ts);
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert output["indexes"][0]["columns"] == ["level", "ts"]

    def test_functional_index(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE users (id UUID PRIMARY KEY, email TEXT);
            CREATE INDEX idx_users_lower_email ON users (lower(email));
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["indexes"]) == 1
        # Functional expressions are preserved as-is
        assert "lower(email)" in output["indexes"][0]["columns"]


# ---------------------------------------------------------------------------
# CREATE FUNCTION
# ---------------------------------------------------------------------------


class TestCreateFunction:
    def test_basic_function(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE OR REPLACE FUNCTION my_func()
            RETURNS void LANGUAGE plpgsql AS $$
            BEGIN
                RETURN;
            END;
            $$;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["stored_functions"]) == 1
        fn = output["stored_functions"][0]
        assert fn["name"] == "public.my_func"
        assert fn["language"] == "plpgsql"
        assert fn["file"] == "001.sql"

    def test_function_with_params(
        self, parser: TreeSitterSchemaParser, migrations_dir: Path
    ) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE FUNCTION add_numbers(a INTEGER, b INTEGER)
            RETURNS INTEGER LANGUAGE sql AS $$
            SELECT a + b;
            $$;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        fn = output["stored_functions"][0]
        assert fn["name"] == "public.add_numbers"
        assert len(fn["parameters"]) >= 2

    def test_plpgsql_table_references(
        self, parser: TreeSitterSchemaParser, migrations_dir: Path
    ) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE orders (id UUID PRIMARY KEY);
            CREATE FUNCTION process_order()
            RETURNS void LANGUAGE plpgsql AS $$
            BEGIN
                INSERT INTO orders (id) VALUES (gen_random_uuid());
                UPDATE orders SET id = id;
            END;
            $$;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        fn = output["stored_functions"][0]
        assert "public.orders" in fn["referenced_tables"]

    def test_create_or_replace(
        self, parser: TreeSitterSchemaParser, migrations_dir: Path
    ) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE FUNCTION my_func() RETURNS void LANGUAGE sql AS $$ SELECT 1; $$;
        """)
        write_migration(migrations_dir, "002.sql", """
            CREATE OR REPLACE FUNCTION my_func() RETURNS void LANGUAGE sql AS $$ SELECT 2; $$;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["stored_functions"]) == 1
        assert output["stored_functions"][0]["file"] == "002.sql"

    def test_returns_trigger(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE OR REPLACE FUNCTION immutable_error()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'immutable';
            END;
            $$ LANGUAGE plpgsql;
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["stored_functions"]) == 1
        fn = output["stored_functions"][0]
        assert fn["name"] == "public.immutable_error"
        assert fn["language"] == "plpgsql"


# ---------------------------------------------------------------------------
# CREATE TRIGGER
# ---------------------------------------------------------------------------


class TestCreateTrigger:
    def test_basic_trigger(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE users (id UUID PRIMARY KEY, updated_at TIMESTAMPTZ);
            CREATE FUNCTION update_ts() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;
            CREATE TRIGGER trg_update_ts
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_ts();
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["triggers"]) == 1
        trg = output["triggers"][0]
        assert trg["name"] == "trg_update_ts"
        assert trg["table"] == "public.users"
        assert trg["timing"] == "BEFORE"
        assert "UPDATE" in trg["event"]
        assert trg["function"] == "public.update_ts"


# ---------------------------------------------------------------------------
# Summary and FK graph
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_counts(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE a (id UUID PRIMARY KEY, name TEXT);
            CREATE TABLE b (id UUID PRIMARY KEY, a_id UUID REFERENCES a(id));
            CREATE INDEX idx_b_a ON b (a_id);
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert output["summary"]["total_tables"] == 2
        assert output["summary"]["total_columns"] == 4
        assert output["summary"]["total_foreign_keys"] == 1
        assert output["summary"]["total_indexes"] == 1

    def test_fk_graph(self, parser: TreeSitterSchemaParser, migrations_dir: Path) -> None:
        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE parents (id UUID PRIMARY KEY);
            CREATE TABLE children (id UUID PRIMARY KEY, parent_id UUID REFERENCES parents(id));
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        assert len(output["fk_graph"]) == 1
        assert output["fk_graph"][0]["from"] == "public.children"
        assert output["fk_graph"][0]["to"] == "public.parents"


# ---------------------------------------------------------------------------
# Migration ordering
# ---------------------------------------------------------------------------


class TestMigrationOrdering:
    def test_files_parsed_in_order(
        self, parser: TreeSitterSchemaParser, migrations_dir: Path
    ) -> None:
        write_migration(migrations_dir, "002_later.sql", """
            ALTER TABLE users ADD COLUMN role TEXT;
        """)
        write_migration(migrations_dir, "001_first.sql", """
            CREATE TABLE users (id UUID PRIMARY KEY);
        """)
        parser.parse_directory(migrations_dir)
        output = parser.build_output()

        table = output["tables"][0]
        assert len(table["columns"]) == 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_main(self, migrations_dir: Path, tmp_path: Path) -> None:
        from analyze_sql_treesitter import main

        write_migration(migrations_dir, "001.sql", """
            CREATE TABLE test (id UUID PRIMARY KEY);
        """)
        output_path = tmp_path / "output.json"
        rc = main([str(migrations_dir), "--output", str(output_path)])

        assert rc == 0
        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert data["summary"]["total_tables"] == 1
