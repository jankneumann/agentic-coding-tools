"""Comprehensive tests for architecture analysis scripts.

Tests cover:
- validate_schema.py   -- JSON schema validation of architecture.graph.json
- analyze_python.py    -- Python AST analyzer
- analyze_postgres.py  -- Database schema analyzer
- compile_architecture_graph.py -- Graph compiler
- validate_flows.py    -- Flow validator
- generate_views.py    -- Mermaid view generator
- parallel_zones.py    -- Parallel zone analyzer
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

# Ensure the scripts directory is importable.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import analyze_postgres as pg_mod
import analyze_python as py_mod
import compile_architecture_graph as compiler_mod
import generate_views as views_mod
import parallel_zones as pz_mod
import validate_flows as flows_mod
import validate_schema as schema_mod


# ============================================================================
# Shared fixtures
# ============================================================================


def _minimal_valid_graph(
    *,
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
    entrypoints: list[dict] | None = None,
) -> dict:
    """Return a minimal valid architecture graph dict."""
    return {
        "snapshots": [
            {
                "generated_at": "2025-01-01T00:00:00+00:00",
                "git_sha": "abc123",
                "tool_versions": {"test": "1.0.0"},
            }
        ],
        "nodes": nodes or [
            {
                "id": "py:app.main",
                "kind": "function",
                "language": "python",
                "name": "main",
                "file": "app/main.py",
                "span": {"start": 1, "end": 10},
                "tags": ["entrypoint"],
                "signatures": {},
            },
            {
                "id": "py:app.service.get_users",
                "kind": "function",
                "language": "python",
                "name": "get_users",
                "file": "app/service.py",
                "span": {"start": 5, "end": 20},
                "tags": [],
                "signatures": {},
            },
            {
                "id": "pg:public.users",
                "kind": "table",
                "language": "sql",
                "name": "users",
                "file": "001_create_users.sql",
                "span": {"start": 1, "end": 1},
                "tags": [],
                "signatures": {},
            },
        ],
        "edges": edges if edges is not None else [
            {
                "from": "py:app.main",
                "to": "py:app.service.get_users",
                "type": "call",
                "confidence": "high",
                "evidence": "ast:call",
            },
            {
                "from": "py:app.service.get_users",
                "to": "pg:public.users",
                "type": "db_access",
                "confidence": "medium",
                "evidence": "orm:model_usage",
            },
        ],
        "entrypoints": entrypoints if entrypoints is not None else [
            {"node_id": "py:app.main", "kind": "route", "method": "GET", "path": "/users"},
        ],
    }


@pytest.fixture
def valid_graph_file(tmp_path: Path) -> Path:
    """Write a minimal valid graph to a temp file and return its path."""
    graph = _minimal_valid_graph()
    p = tmp_path / "architecture.graph.json"
    p.write_text(json.dumps(graph, indent=2))
    return p


@pytest.fixture
def sample_graph() -> dict:
    """Return a minimal valid graph dict."""
    return _minimal_valid_graph()


# ============================================================================
# TestSchemaValidation
# ============================================================================


class TestSchemaValidation:
    """Tests for scripts/validate_schema.py."""

    def test_well_formed_graph_passes(self, valid_graph_file: Path) -> None:
        """A graph matching the schema should produce no errors."""
        errors = schema_mod.validate_graph(valid_graph_file)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_missing_confidence_on_edges_fails(self, tmp_path: Path) -> None:
        """An edge without 'confidence' must be rejected."""
        graph = _minimal_valid_graph()
        graph["edges"] = [
            {
                "from": "py:app.main",
                "to": "py:app.service.get_users",
                "type": "call",
                # "confidence" intentionally missing
                "evidence": "ast:call",
            },
        ]
        p = tmp_path / "bad_edge.json"
        p.write_text(json.dumps(graph))
        errors = schema_mod.validate_graph(p)
        assert len(errors) > 0
        assert any("confidence" in e.lower() for e in errors), (
            f"Expected an error about missing 'confidence', got: {errors}"
        )

    def test_invalid_node_id_pattern_fails(self, tmp_path: Path) -> None:
        """A node with an ID not matching the ^(py|ts|pg):.+$ pattern must fail."""
        graph = _minimal_valid_graph()
        graph["nodes"] = [
            {
                "id": "badprefix:module",  # invalid prefix
                "kind": "function",
                "language": "python",
                "name": "test",
                "file": "test.py",
                "span": {"start": 1, "end": 1},
                "tags": [],
                "signatures": {},
            },
        ]
        graph["edges"] = []
        graph["entrypoints"] = []
        p = tmp_path / "bad_node_id.json"
        p.write_text(json.dumps(graph))
        errors = schema_mod.validate_graph(p)
        assert len(errors) > 0
        # The pattern check should flag the ID.
        assert any("badprefix" in e or "pattern" in e.lower() for e in errors), (
            f"Expected a pattern error for 'badprefix:module', got: {errors}"
        )

    def test_edges_referencing_nonexistent_nodes(self, tmp_path: Path) -> None:
        """Edges that reference node IDs not in the nodes array must be caught."""
        graph = _minimal_valid_graph()
        graph["edges"] = [
            {
                "from": "py:app.main",
                "to": "py:nonexistent.func",
                "type": "call",
                "confidence": "high",
                "evidence": "ast:call",
            },
        ]
        p = tmp_path / "dangling_edge.json"
        p.write_text(json.dumps(graph))
        errors = schema_mod.validate_graph(p)
        assert len(errors) > 0
        assert any("nonexistent" in e for e in errors), (
            f"Expected an error about nonexistent node, got: {errors}"
        )

    def test_entrypoint_referencing_nonexistent_node(self, tmp_path: Path) -> None:
        """Entrypoints referencing missing nodes must be caught."""
        graph = _minimal_valid_graph()
        graph["entrypoints"] = [
            {"node_id": "py:does.not.exist", "kind": "route"},
        ]
        p = tmp_path / "bad_ep.json"
        p.write_text(json.dumps(graph))
        errors = schema_mod.validate_graph(p)
        assert len(errors) > 0
        assert any("does.not.exist" in e for e in errors)


# ============================================================================
# TestPythonAnalyzer
# ============================================================================


class TestPythonAnalyzer:
    """Tests for scripts/analyze_python.py."""

    @pytest.fixture
    def python_project(self, tmp_path: Path) -> Path:
        """Create a small synthetic Python project with various patterns."""
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        # FastAPI route file
        (pkg / "routes.py").write_text(textwrap.dedent("""\
            from fastapi import APIRouter
            from myapp.service import fetch_users

            router = APIRouter()

            @router.get("/users")
            async def list_users():
                \"\"\"List all users.\"\"\"
                return await fetch_users()

            @router.post("/users")
            async def create_user():
                return {"ok": True}
        """))

        # Service file with DB access
        (pkg / "service.py").write_text(textwrap.dedent("""\
            from myapp.models import User

            async def fetch_users():
                \"\"\"Fetch users from DB.\"\"\"
                return User.query.all()

            def _internal_helper():
                pass
        """))

        # Model file with SQLAlchemy pattern
        (pkg / "models.py").write_text(textwrap.dedent("""\
            from sqlalchemy import Column, Integer, String
            from sqlalchemy.ext.declarative import declarative_base

            Base = declarative_base()

            class User(Base):
                __tablename__ = "users"
                id = Column(Integer, primary_key=True)
                name = Column(String)
        """))

        # Broken file with SyntaxError
        (pkg / "broken.py").write_text("def oops(\n    pass\n")

        return tmp_path

    def test_analyze_directory_output_structure(self, python_project: Path) -> None:
        """analyze_directory returns all expected top-level keys."""
        result = py_mod.analyze_directory(python_project)
        expected_keys = {
            "modules",
            "functions",
            "classes",
            "import_graph",
            "entry_points",
            "db_access",
            "summary",
        }
        assert set(result.keys()) == expected_keys

    def test_entry_point_detection(self, python_project: Path) -> None:
        """FastAPI route decorators are detected as entry points."""
        result = py_mod.analyze_directory(python_project)
        ep_functions = [ep["function"] for ep in result["entry_points"]]
        # The qualified names should include the route functions.
        assert any("list_users" in f for f in ep_functions), (
            f"Expected list_users as entry point, found: {ep_functions}"
        )
        assert any("create_user" in f for f in ep_functions), (
            f"Expected create_user as entry point, found: {ep_functions}"
        )
        # Verify entry point kind and method.
        for ep in result["entry_points"]:
            if "list_users" in ep["function"]:
                assert ep["kind"] == "route"
                assert ep["method"] == "GET"
                assert ep["path"] == "/users"

    def test_call_graph_extraction(self, python_project: Path) -> None:
        """Functions that call other functions should have calls recorded."""
        result = py_mod.analyze_directory(python_project)
        functions_by_name = {
            f["qualified_name"]: f for f in result["functions"]
        }
        # list_users calls fetch_users
        list_users_func = None
        for f in result["functions"]:
            if "list_users" in f["qualified_name"]:
                list_users_func = f
                break
        assert list_users_func is not None
        assert any("fetch_users" in c for c in list_users_func["calls"]), (
            f"Expected fetch_users in calls, got: {list_users_func['calls']}"
        )

    def test_db_access_pattern_detection(self, python_project: Path) -> None:
        """ORM patterns (Model.query.all()) should be detected as DB access."""
        result = py_mod.analyze_directory(python_project)
        db_functions = [da["function"] for da in result["db_access"]]
        assert any("fetch_users" in f for f in db_functions), (
            f"Expected fetch_users in db_access, found: {db_functions}"
        )
        # The detected pattern should be "orm"
        for da in result["db_access"]:
            if "fetch_users" in da["function"]:
                assert da["pattern"] == "orm"

    def test_dead_code_candidate_detection(self, python_project: Path) -> None:
        """Functions without callers and not entry points should be dead code candidates."""
        result = py_mod.analyze_directory(python_project)
        dead = result["summary"]["dead_code_candidates"]
        # _internal_helper is not called by anything and is not an entry point.
        assert any("_internal_helper" in dc for dc in dead), (
            f"Expected _internal_helper as dead code, got: {dead}"
        )

    def test_syntax_error_handling(self, python_project: Path) -> None:
        """Files with SyntaxErrors should be skipped without crashing."""
        # The broken.py file has a syntax error; the analysis should still succeed.
        result = py_mod.analyze_directory(python_project)
        # Verify the broken module is NOT in the modules list.
        module_files = [m["file"] for m in result["modules"]]
        assert not any("broken.py" in f for f in module_files), (
            f"broken.py should be skipped, but found in: {module_files}"
        )
        # Other modules should still be present.
        assert len(result["modules"]) >= 3  # __init__, routes, service, models (minus broken)

    def test_include_exclude_filtering(self, python_project: Path) -> None:
        """--include and --exclude patterns should filter discovered files."""
        # Include only routes.py
        result = py_mod.analyze_directory(
            python_project, include_patterns=["routes.py"]
        )
        module_files = [m["file"] for m in result["modules"]]
        assert len(module_files) == 1
        assert "routes.py" in module_files[0]

        # Exclude routes.py
        result2 = py_mod.analyze_directory(
            python_project, exclude_patterns=["routes.py"]
        )
        module_files2 = [m["file"] for m in result2["modules"]]
        assert not any("routes.py" in f for f in module_files2)

    def test_async_function_detection(self, python_project: Path) -> None:
        """Async functions should be tagged appropriately."""
        result = py_mod.analyze_directory(python_project)
        for f in result["functions"]:
            if "list_users" in f["qualified_name"]:
                assert f["is_async"] is True
                assert "async" in f["tags"]

    def test_class_extraction(self, python_project: Path) -> None:
        """Classes and their bases should be extracted."""
        result = py_mod.analyze_directory(python_project)
        class_names = [c["name"] for c in result["classes"]]
        assert "User" in class_names
        for cls in result["classes"]:
            if cls["name"] == "User":
                assert "Base" in cls["bases"]


# ============================================================================
# TestPostgresAnalyzer
# ============================================================================


class TestPostgresAnalyzer:
    """Tests for scripts/analyze_postgres.py."""

    @pytest.fixture
    def migration_dir(self, tmp_path: Path) -> Path:
        """Create a temp directory with sample SQL migration files."""
        mig = tmp_path / "migrations"
        mig.mkdir()

        (mig / "001_create_users.sql").write_text(textwrap.dedent("""\
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                name VARCHAR(100) DEFAULT 'unknown',
                created_at TIMESTAMP DEFAULT now()
            );

            CREATE INDEX idx_users_email ON users(email);
        """))

        (mig / "002_create_posts.sql").write_text(textwrap.dedent("""\
            CREATE TABLE posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                body TEXT
            );

            CREATE INDEX idx_posts_user_id ON posts(user_id);
        """))

        (mig / "003_alter_users.sql").write_text(textwrap.dedent("""\
            ALTER TABLE users ADD COLUMN bio TEXT;
            ALTER TABLE posts ADD CONSTRAINT fk_posts_user
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
            CREATE UNIQUE INDEX idx_users_email_unique ON users(email);
        """))

        return mig

    def test_table_extraction(self, migration_dir: Path) -> None:
        """CREATE TABLE statements should produce table entries with columns."""
        parser = pg_mod.SchemaParser()
        for sql_file in sorted(migration_dir.glob("*.sql"), key=pg_mod._sort_key):
            parser.parse_file(sql_file)
        output = parser.build_output()

        table_names = [t["name"] for t in output["tables"]]
        assert "public.users" in table_names
        assert "public.posts" in table_names

        # Check users table columns
        users_table = next(t for t in output["tables"] if t["name"] == "public.users")
        col_names = [c["name"] for c in users_table["columns"]]
        assert "id" in col_names
        assert "email" in col_names
        assert "name" in col_names
        assert "created_at" in col_names
        # bio was added by ALTER TABLE
        assert "bio" in col_names

        # Verify primary key
        assert "id" in users_table["primary_key"]

    def test_fk_relationship_extraction(self, migration_dir: Path) -> None:
        """FOREIGN KEY constraints (inline and via ALTER TABLE) should be extracted."""
        parser = pg_mod.SchemaParser()
        for sql_file in sorted(migration_dir.glob("*.sql"), key=pg_mod._sort_key):
            parser.parse_file(sql_file)
        output = parser.build_output()

        fks = output["foreign_keys"]
        assert len(fks) >= 1
        # Check that posts -> users FK exists
        found_fk = False
        for fk in fks:
            if fk["from_table"] == "public.posts" and fk["to_table"] == "public.users":
                found_fk = True
                assert "user_id" in fk["from_columns"]
                assert "id" in fk["to_columns"]
                break
        assert found_fk, f"Expected FK from posts to users, got: {fks}"

        # Check FK graph
        fk_graph = output["fk_graph"]
        assert any(
            e["from"] == "public.posts" and e["to"] == "public.users"
            for e in fk_graph
        )

    def test_index_extraction(self, migration_dir: Path) -> None:
        """CREATE INDEX statements should be extracted with metadata."""
        parser = pg_mod.SchemaParser()
        for sql_file in sorted(migration_dir.glob("*.sql"), key=pg_mod._sort_key):
            parser.parse_file(sql_file)
        output = parser.build_output()

        indexes = output["indexes"]
        idx_names = [idx["name"] for idx in indexes]
        assert "idx_users_email" in idx_names
        assert "idx_posts_user_id" in idx_names
        assert "idx_users_email_unique" in idx_names

        # The unique index should be marked as unique.
        for idx in indexes:
            if idx["name"] == "idx_users_email_unique":
                assert idx["unique"] is True
            if idx["name"] == "idx_users_email":
                assert idx["unique"] is False

    def test_summary_statistics(self, migration_dir: Path) -> None:
        """Summary should include correct aggregate counts."""
        parser = pg_mod.SchemaParser()
        for sql_file in sorted(migration_dir.glob("*.sql"), key=pg_mod._sort_key):
            parser.parse_file(sql_file)
        output = parser.build_output()

        summary = output["summary"]
        assert summary["total_tables"] == 2
        assert summary["total_indexes"] >= 3
        assert summary["total_foreign_keys"] >= 1

    def test_unparseable_sql_handling(self, tmp_path: Path) -> None:
        """Unparseable SQL should not crash the parser."""
        mig = tmp_path / "bad_migrations"
        mig.mkdir()
        (mig / "001_garbage.sql").write_text(textwrap.dedent("""\
            THIS IS NOT VALID SQL AT ALL;
            JUST RANDOM GIBBERISH;
            CREATE TABLE good_table (
                id SERIAL PRIMARY KEY,
                name TEXT
            );
        """))
        parser = pg_mod.SchemaParser()
        for sql_file in sorted(mig.glob("*.sql"), key=pg_mod._sort_key):
            parser.parse_file(sql_file)
        output = parser.build_output()
        # The valid CREATE TABLE should still be parsed.
        table_names = [t["name"] for t in output["tables"]]
        assert "public.good_table" in table_names


# ============================================================================
# TestGraphCompiler
# ============================================================================


class TestGraphCompiler:
    """Tests for scripts/compile_architecture_graph.py."""

    @pytest.fixture
    def intermediate_dir(self, tmp_path: Path) -> Path:
        """Create mock intermediate analysis files."""
        arch_dir = tmp_path / ".architecture"
        arch_dir.mkdir()

        python_analysis = {
            "modules": [
                {
                    "name": "app.service",
                    "file": "app/service.py",
                    "qualified_name": "app.service",
                },
            ],
            "functions": [
                {
                    "name": "get_users",
                    "qualified_name": "app.service.get_users",
                    "file": "app/service.py",
                    "span": {"start": 1, "end": 10},
                    "tags": ["db_access"],
                    "signatures": {},
                    "db_tables": ["users"],
                    "entrypoints": [
                        {"kind": "route", "method": "GET", "path": "/users"},
                    ],
                },
                {
                    "name": "helper",
                    "qualified_name": "app.service.helper",
                    "file": "app/service.py",
                    "span": {"start": 12, "end": 20},
                    "tags": [],
                    "signatures": {},
                },
            ],
            "classes": [],
            "call_edges": [
                {"from": "app.service.get_users", "to": "app.service.helper"},
            ],
            "import_edges": [],
            "db_access_edges": [
                {
                    "from": "app.service.get_users",
                    "table": "users",
                    "confidence": "medium",
                    "evidence": "orm:model_usage",
                },
            ],
        }

        postgres_analysis = {
            "tables": [
                {
                    "name": "users",
                    "schema": "public",
                    "columns": [
                        {"name": "id", "type": "integer"},
                        {"name": "email", "type": "varchar"},
                    ],
                    "file": "001_init.sql",
                },
            ],
            "foreign_keys": [],
            "indexes": [],
            "functions": [],
            "triggers": [],
            "migrations": [],
        }

        (arch_dir / "python_analysis.json").write_text(json.dumps(python_analysis))
        (arch_dir / "postgres_analysis.json").write_text(json.dumps(postgres_analysis))

        return arch_dir

    def test_compile_graph_produces_output(self, intermediate_dir: Path) -> None:
        """compile_graph should produce architecture.graph.json and summary."""
        output_dir = intermediate_dir.parent / "output"
        rc = compiler_mod.compile_graph(
            input_dir=intermediate_dir,
            output_dir=output_dir,
            summary_limit=50,
            emit_sqlite_flag=False,
        )
        assert rc == 0
        assert (output_dir / "architecture.graph.json").exists()
        assert (output_dir / "architecture.summary.json").exists()

    def test_node_id_normalization(self) -> None:
        """make_node_id should produce stable {prefix}:{qualified_name} IDs."""
        assert compiler_mod.make_node_id("py", "app.service.get_users") == "py:app.service.get_users"
        assert compiler_mod.make_node_id("pg", "public.users") == "pg:public.users"
        # Whitespace should be replaced with underscore.
        assert compiler_mod.make_node_id("py", "  some func  ") == "py:some_func"

    def test_python_ingestion_creates_nodes_and_edges(self, intermediate_dir: Path) -> None:
        """ingest_python should create nodes for modules and functions, and edges for calls."""
        py_data = json.loads((intermediate_dir / "python_analysis.json").read_text())
        nodes, edges, entrypoints = compiler_mod.ingest_python(py_data)

        node_ids = {n["id"] for n in nodes}
        assert "py:app.service" in node_ids
        assert "py:app.service.get_users" in node_ids
        assert "py:app.service.helper" in node_ids

        # Call edges
        call_edges = [e for e in edges if e["type"] == "call"]
        assert any(
            e["from"] == "py:app.service.get_users" and e["to"] == "py:app.service.helper"
            for e in call_edges
        )

        # Entrypoints
        assert len(entrypoints) >= 1
        ep = entrypoints[0]
        assert ep["node_id"] == "py:app.service.get_users"
        assert ep["kind"] == "route"

    def test_cross_language_backend_db_edges(self, intermediate_dir: Path) -> None:
        """db_access_edges should link Python functions to PG tables."""
        py_data = json.loads((intermediate_dir / "python_analysis.json").read_text())
        nodes, edges, _ = compiler_mod.ingest_python(py_data)

        db_edges = [e for e in edges if e["type"] == "db_access"]
        assert any(
            e["from"] == "py:app.service.get_users"
            and "pg:" in e["to"]
            and "users" in e["to"]
            for e in db_edges
        ), f"Expected db_access edge from get_users to users table, got: {db_edges}"

    def test_full_compilation_with_backend_db_linking(self, intermediate_dir: Path) -> None:
        """Full compilation should produce nodes from both py and pg, with linking edges."""
        output_dir = intermediate_dir.parent / "output2"
        compiler_mod.compile_graph(
            input_dir=intermediate_dir,
            output_dir=output_dir,
            summary_limit=50,
            emit_sqlite_flag=False,
        )
        graph = json.loads((output_dir / "architecture.graph.json").read_text())
        node_ids = {n["id"] for n in graph["nodes"]}

        # Python nodes
        assert any("py:" in nid for nid in node_ids)
        # Postgres nodes (tables)
        assert any("pg:" in nid for nid in node_ids)

        # db_access edges should exist
        db_edges = [e for e in graph["edges"] if e["type"] == "db_access"]
        assert len(db_edges) >= 1

    def test_summary_generation_adaptive_threshold(self, intermediate_dir: Path) -> None:
        """Summary should be generated with stats."""
        output_dir = intermediate_dir.parent / "output3"
        compiler_mod.compile_graph(
            input_dir=intermediate_dir,
            output_dir=output_dir,
            summary_limit=50,
            emit_sqlite_flag=False,
        )
        summary = json.loads((output_dir / "architecture.summary.json").read_text())
        assert "stats" in summary
        assert summary["stats"]["total_nodes"] > 0
        assert summary["stats"]["total_edges"] >= 0
        assert "generated_at" in summary
        assert "git_sha" in summary

    def test_deduplication_helpers(self) -> None:
        """deduplicate_nodes and deduplicate_edges should remove duplicates."""
        nodes = [
            {"id": "py:a", "kind": "function"},
            {"id": "py:a", "kind": "function"},
            {"id": "py:b", "kind": "function"},
        ]
        deduped = compiler_mod.deduplicate_nodes(nodes)
        assert len(deduped) == 2

        edges = [
            {"from": "py:a", "to": "py:b", "type": "call", "confidence": "high", "evidence": "e1"},
            {"from": "py:a", "to": "py:b", "type": "call", "confidence": "medium", "evidence": "e2"},
            {"from": "py:a", "to": "py:b", "type": "import", "confidence": "high", "evidence": "e3"},
        ]
        deduped_edges = compiler_mod.deduplicate_edges(edges)
        # (a, b, call) and (a, b, import) = 2 unique
        assert len(deduped_edges) == 2

    def test_validate_edges_drops_invalid(self) -> None:
        """validate_edges should remove edges referencing missing nodes."""
        edges = [
            {"from": "py:a", "to": "py:b", "type": "call", "confidence": "high", "evidence": "e1"},
            {"from": "py:a", "to": "py:missing", "type": "call", "confidence": "high", "evidence": "e2"},
        ]
        valid = compiler_mod.validate_edges(edges, {"py:a", "py:b"})
        assert len(valid) == 1
        assert valid[0]["to"] == "py:b"


# ============================================================================
# TestFlowValidator
# ============================================================================


class TestFlowValidator:
    """Tests for scripts/validate_flows.py."""

    def test_reachability_check(self, valid_graph_file: Path, tmp_path: Path) -> None:
        """Entrypoint with downstream DB access should pass reachability."""
        report = flows_mod.validate_flows(
            graph_path=valid_graph_file,
            output_path=tmp_path / "diag.json",
            changed_files=None,
        )
        # The main entry point reaches get_users -> users table (db_access),
        # so reachability should be satisfied.
        reachability_findings = [
            f for f in report["findings"] if f["category"] == "reachability"
        ]
        # No warning about missing downstream for the main endpoint.
        reachability_warnings = [
            f for f in reachability_findings
            if f["severity"] == "warning" and "no downstream" in f["message"]
        ]
        assert len(reachability_warnings) == 0, (
            f"Expected no 'no downstream' warnings, got: {reachability_warnings}"
        )

    def test_disconnected_flow_detection(self, tmp_path: Path) -> None:
        """A route with no api_call edges should be flagged as disconnected."""
        graph = _minimal_valid_graph()
        # Route entrypoint exists but no api_call edge from frontend.
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(graph))
        report = flows_mod.validate_flows(
            graph_path=p,
            output_path=tmp_path / "diag.json",
            changed_files=None,
        )
        disconnected = [
            f for f in report["findings"]
            if f["category"] == "disconnected_flow"
        ]
        # The route has no api_call edges, so it should be flagged.
        assert any(
            "no frontend callers" in f["message"]
            for f in disconnected
        ), f"Expected disconnected flow finding, got: {disconnected}"

    def test_orphan_detection(self, tmp_path: Path) -> None:
        """A function unreachable from any entrypoint should be detected as orphan."""
        graph = _minimal_valid_graph()
        # Add an orphan node not connected to anything.
        graph["nodes"].append({
            "id": "py:orphan.func",
            "kind": "function",
            "language": "python",
            "name": "orphan_func",
            "file": "orphan.py",
            "span": {"start": 1, "end": 5},
            "tags": [],
            "signatures": {},
        })
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(graph))
        report = flows_mod.validate_flows(
            graph_path=p,
            output_path=tmp_path / "diag.json",
            changed_files=None,
        )
        orphan_findings = [
            f for f in report["findings"] if f["category"] == "orphan"
        ]
        assert any(
            "orphan_func" in f["message"]
            for f in orphan_findings
        ), f"Expected orphan finding for orphan_func, got: {orphan_findings}"

    def test_diagnostics_output_format(self, valid_graph_file: Path, tmp_path: Path) -> None:
        """Diagnostics report should have the expected structure."""
        output = tmp_path / "diag.json"
        report = flows_mod.validate_flows(
            graph_path=valid_graph_file,
            output_path=output,
            changed_files=None,
        )
        assert output.exists()
        data = json.loads(output.read_text())

        assert "generated_at" in data
        assert "scope" in data
        assert "findings" in data
        assert "summary" in data
        assert isinstance(data["findings"], list)

        summary = data["summary"]
        for key in ["total_findings", "errors", "warnings", "info", "entrypoints_checked"]:
            assert key in summary, f"Missing key: {key}"

    def test_entrypoint_no_downstream(self, tmp_path: Path) -> None:
        """An entrypoint with zero downstream edges should produce a warning."""
        graph = _minimal_valid_graph(
            nodes=[
                {
                    "id": "py:lonely.endpoint",
                    "kind": "function",
                    "language": "python",
                    "name": "lonely_endpoint",
                    "file": "lonely.py",
                    "span": {"start": 1, "end": 5},
                    "tags": [],
                    "signatures": {},
                },
            ],
            edges=[],
            entrypoints=[
                {"node_id": "py:lonely.endpoint", "kind": "route"},
            ],
        )
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(graph))
        report = flows_mod.validate_flows(
            graph_path=p,
            output_path=tmp_path / "diag.json",
            changed_files=None,
        )
        reachability_findings = [
            f for f in report["findings"]
            if f["category"] == "reachability"
        ]
        assert any(
            "no downstream" in f["message"]
            for f in reachability_findings
        ), f"Expected reachability warning, got: {reachability_findings}"


# ============================================================================
# TestViewGenerator
# ============================================================================


class TestViewGenerator:
    """Tests for scripts/generate_views.py."""

    @pytest.fixture
    def graph_for_views(self) -> dict:
        """Graph with Python, TypeScript, and SQL nodes for view generation."""
        return {
            "snapshots": [
                {
                    "generated_at": "2025-01-01T00:00:00+00:00",
                    "git_sha": "abc123",
                    "tool_versions": {"test": "1.0.0"},
                }
            ],
            "nodes": [
                {
                    "id": "py:backend.api.list_users",
                    "kind": "function",
                    "language": "python",
                    "name": "list_users",
                    "file": "backend/api/routes.py",
                    "span": {"start": 1, "end": 10},
                    "tags": ["entrypoint"],
                    "signatures": {},
                },
                {
                    "id": "ts:src.components.UserList",
                    "kind": "component",
                    "language": "typescript",
                    "name": "UserList",
                    "file": "src/components/UserList.tsx",
                    "span": {"start": 1, "end": 50},
                    "tags": [],
                    "signatures": {},
                },
                {
                    "id": "pg:public.users",
                    "kind": "table",
                    "language": "sql",
                    "name": "users",
                    "file": "001_init.sql",
                    "span": {"start": 1, "end": 1},
                    "tags": [],
                    "signatures": {},
                },
                {
                    "id": "pg:public.posts",
                    "kind": "table",
                    "language": "sql",
                    "name": "posts",
                    "file": "002_posts.sql",
                    "span": {"start": 1, "end": 1},
                    "tags": [],
                    "signatures": {},
                },
            ],
            "edges": [
                {
                    "from": "ts:src.components.UserList",
                    "to": "py:backend.api.list_users",
                    "type": "api_call",
                    "confidence": "high",
                    "evidence": "string_match:/users",
                },
                {
                    "from": "py:backend.api.list_users",
                    "to": "pg:public.users",
                    "type": "db_access",
                    "confidence": "medium",
                    "evidence": "orm:model_usage",
                },
                {
                    "from": "pg:public.posts",
                    "to": "pg:public.users",
                    "type": "fk_reference",
                    "confidence": "high",
                    "evidence": "fk:fk_posts_user",
                },
            ],
            "entrypoints": [
                {
                    "node_id": "py:backend.api.list_users",
                    "kind": "route",
                    "method": "GET",
                    "path": "/users",
                },
            ],
        }

    def test_view_files_are_generated(self, graph_for_views: dict, tmp_path: Path) -> None:
        """Running main should produce all expected .mmd files."""
        graph_path = tmp_path / "graph.json"
        graph_path.write_text(json.dumps(graph_for_views))
        output_dir = tmp_path / "views"

        rc = views_mod.main([
            "--graph", str(graph_path),
            "--output-dir", str(output_dir),
        ])
        assert rc == 0
        assert (output_dir / "containers.mmd").exists()
        assert (output_dir / "backend_components.mmd").exists()
        assert (output_dir / "frontend_components.mmd").exists()
        assert (output_dir / "db_erd.mmd").exists()

    def test_container_view_contents(self, graph_for_views: dict) -> None:
        """Container view should mention Backend, Frontend, and Database."""
        content = views_mod.generate_container_view(graph_for_views)
        assert "Backend" in content
        assert "Frontend" in content
        assert "Database" in content
        # Should show cross-container edge types.
        assert "api_call" in content

    def test_db_erd_contains_table_nodes(self, graph_for_views: dict) -> None:
        """DB ERD should contain table names."""
        content = views_mod.generate_db_erd(graph_for_views)
        assert "erDiagram" in content
        assert "users" in content
        assert "posts" in content

    def test_backend_component_view(self, graph_for_views: dict) -> None:
        """Backend component view should group Python nodes by package."""
        content = views_mod.generate_backend_component_view(graph_for_views)
        assert "flowchart TB" in content
        # Should contain the package name.
        assert "backend" in content.lower()

    def test_frontend_component_view(self, graph_for_views: dict) -> None:
        """Frontend component view should group TS nodes by directory."""
        content = views_mod.generate_frontend_component_view(graph_for_views)
        assert "flowchart TB" in content
        assert "src" in content.lower()

    def test_feature_slice_generation(self, graph_for_views: dict, tmp_path: Path) -> None:
        """Feature slice should extract relevant subgraph for given files."""
        mermaid, subgraph = views_mod.generate_feature_slice(
            graph_for_views,
            ["backend/api/routes.py"],
        )
        assert "flowchart TB" in mermaid
        # The matched node should be included.
        assert len(subgraph["matched_file_nodes"]) >= 1
        # Neighbors should be included too.
        node_ids = {n["id"] for n in subgraph["nodes"]}
        assert "py:backend.api.list_users" in node_ids


# ============================================================================
# TestParallelZones
# ============================================================================


class TestParallelZones:
    """Tests for scripts/parallel_zones.py."""

    @pytest.fixture
    def graph_with_groups(self) -> dict:
        """Graph with two independent connected components and a leaf module."""
        return {
            "snapshots": [
                {
                    "generated_at": "2025-01-01T00:00:00+00:00",
                    "git_sha": "abc123",
                    "tool_versions": {"test": "1.0.0"},
                }
            ],
            "nodes": [
                # Group 1: auth module
                {
                    "id": "py:auth.login",
                    "kind": "function",
                    "language": "python",
                    "name": "login",
                    "file": "auth/login.py",
                },
                {
                    "id": "py:auth.tokens",
                    "kind": "function",
                    "language": "python",
                    "name": "tokens",
                    "file": "auth/tokens.py",
                },
                # Group 2: billing module (independent of auth)
                {
                    "id": "py:billing.charge",
                    "kind": "function",
                    "language": "python",
                    "name": "charge",
                    "file": "billing/charge.py",
                },
                {
                    "id": "py:billing.invoice",
                    "kind": "function",
                    "language": "python",
                    "name": "invoice",
                    "file": "billing/invoice.py",
                },
                # Isolated leaf (no dependencies at all)
                {
                    "id": "py:utils.constants",
                    "kind": "module",
                    "language": "python",
                    "name": "constants",
                    "file": "utils/constants.py",
                },
                # Hub module: depended on by many
                {
                    "id": "py:core.db",
                    "kind": "module",
                    "language": "python",
                    "name": "db",
                    "file": "core/db.py",
                },
            ],
            "edges": [
                # Group 1 internal edge
                {
                    "from": "py:auth.login",
                    "to": "py:auth.tokens",
                    "type": "call",
                    "confidence": "high",
                    "evidence": "ast:call",
                },
                # Group 2 internal edge
                {
                    "from": "py:billing.charge",
                    "to": "py:billing.invoice",
                    "type": "call",
                    "confidence": "high",
                    "evidence": "ast:call",
                },
                # Both groups depend on core.db
                {
                    "from": "py:auth.login",
                    "to": "py:core.db",
                    "type": "import",
                    "confidence": "high",
                    "evidence": "ast:import",
                },
                {
                    "from": "py:billing.charge",
                    "to": "py:core.db",
                    "type": "import",
                    "confidence": "high",
                    "evidence": "ast:import",
                },
            ],
            "entrypoints": [],
        }

    def test_connected_component_detection(self, graph_with_groups: dict) -> None:
        """Nodes connected by dependency edges should be in the same component."""
        node_ids = [n["id"] for n in graph_with_groups["nodes"]]
        edges = graph_with_groups["edges"]

        components = pz_mod.compute_connected_components(node_ids, edges)
        # All connected nodes should be in one big component (auth + billing + core.db
        # are all connected through core.db), and constants is isolated.
        # Let's check that constants is in its own component.
        component_with_constants = None
        component_with_auth = None
        for comp in components:
            if "py:utils.constants" in comp:
                component_with_constants = comp
            if "py:auth.login" in comp:
                component_with_auth = comp

        assert component_with_constants is not None
        assert len(component_with_constants) == 1, (
            "constants should be isolated in its own component"
        )
        assert component_with_auth is not None
        assert "py:core.db" in component_with_auth, (
            "core.db should be in the same component as auth (connected via import)"
        )

    def test_leaf_module_identification(self, graph_with_groups: dict) -> None:
        """Leaf modules are nodes with no dependents (nothing points to them)."""
        node_ids = set(n["id"] for n in graph_with_groups["nodes"])
        edges = graph_with_groups["edges"]

        leaves = pz_mod.find_leaf_modules(node_ids, edges)
        # constants has no edges at all -> leaf
        assert "py:utils.constants" in leaves
        # auth.login is not depended upon by anything -> leaf
        assert "py:auth.login" in leaves
        # billing.charge is not depended upon by anything -> leaf
        assert "py:billing.charge" in leaves
        # core.db IS depended upon (by auth.login and billing.charge) -> NOT a leaf
        assert "py:core.db" not in leaves
        # auth.tokens is depended upon by auth.login -> NOT a leaf
        assert "py:auth.tokens" not in leaves

    def test_high_impact_module_detection(self, graph_with_groups: dict) -> None:
        """Modules depended on by many others should be detected as high-impact."""
        edges = graph_with_groups["edges"]
        node_ids = set(n["id"] for n in graph_with_groups["nodes"])
        dependents_graph = pz_mod.compute_dependents_graph(edges)

        # core.db has 2 direct dependents: auth.login and billing.charge
        # With transitive dependents, billing.invoice depends on billing.charge
        # which depends on core.db, so core.db has at least 3 transitive dependents.
        # Use threshold=1 to detect it.
        high_impact = pz_mod.find_high_impact_modules(node_ids, dependents_graph, threshold=1)
        high_impact_ids = [h["id"] for h in high_impact]
        assert "py:core.db" in high_impact_ids, (
            f"Expected core.db as high-impact, got: {high_impact_ids}"
        )
        # core.db should have the most dependents.
        if high_impact:
            assert high_impact[0]["id"] == "py:core.db"

    def test_impact_radius(self, graph_with_groups: dict) -> None:
        """compute_impact_radius should return all transitive dependents."""
        edges = graph_with_groups["edges"]
        dependents_graph = pz_mod.compute_dependents_graph(edges)

        radius = pz_mod.compute_impact_radius("py:core.db", dependents_graph)
        # auth.login and billing.charge directly depend on core.db.
        assert "py:auth.login" in radius
        assert "py:billing.charge" in radius

    def test_build_output_structure(self, graph_with_groups: dict) -> None:
        """build_output should produce a well-formed result dict."""
        node_ids = [n["id"] for n in graph_with_groups["nodes"]]
        edges = graph_with_groups["edges"]
        node_map = {n["id"]: n for n in graph_with_groups["nodes"]}

        components = pz_mod.compute_connected_components(node_ids, edges)
        leaf_ids = pz_mod.find_leaf_modules(set(node_ids), edges)
        dependents_graph = pz_mod.compute_dependents_graph(edges)
        high_impact = pz_mod.find_high_impact_modules(set(node_ids), dependents_graph, threshold=1)

        output = pz_mod.build_output(graph_with_groups, components, leaf_ids, high_impact, node_map)

        assert "independent_groups" in output
        assert "leaf_modules" in output
        assert "high_impact_modules" in output
        assert "summary" in output
        assert output["summary"]["total_modules"] == len(graph_with_groups["nodes"])
        assert output["summary"]["total_groups"] == len(components)
        assert output["summary"]["leaf_count"] > 0

    def test_union_find_components(self) -> None:
        """UnionFind should correctly compute connected components."""
        uf = pz_mod.UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")
        uf.union("c", "d")
        comps = uf.components()
        # Should be 2 groups: {a, b} and {c, d}
        assert len(comps) == 2
        group_sizes = sorted(len(g) for g in comps.values())
        assert group_sizes == [2, 2]

    def test_main_cli(self, graph_with_groups: dict, tmp_path: Path) -> None:
        """CLI main should produce the output JSON file."""
        graph_path = tmp_path / "graph.json"
        graph_path.write_text(json.dumps(graph_with_groups))
        output_path = tmp_path / "parallel_zones.json"

        rc = pz_mod.main([
            "--graph", str(graph_path),
            "--output", str(output_path),
            "--impact-threshold", "1",
        ])
        assert rc == 0
        assert output_path.exists()

        data = json.loads(output_path.read_text())
        assert "independent_groups" in data
        assert "summary" in data
