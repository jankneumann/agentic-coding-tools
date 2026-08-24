"""Both SQL analyzers must replay removals, not just creations (issue #386).

The migration directory is a *sequence*, not an append-only set of ``CREATE``
statements. Read as the latter, the schema graph keeps describing objects that
were dropped: after migration 031 dropped ``memory_working`` and
``memory_procedural``, the regenerated graph still carried 27 references to
them — tables, columns, indexes — and nothing flagged it, because the artifacts
were internally consistent and the drift gate only compares them to each other.

Every test here runs against **both** producers. There are two, and the
distinction is easy to miss: refresh step 1.2 runs the regex analyzer
(``analyze_postgres.py``), then step 1.2b runs the tree-sitter one and
*overwrites* its output. Fixing only the first leaves the committed graph
exactly as wrong as before while the tests go green — so the parametrization is
load-bearing, not thoroughness for its own sake.

They pin the removal semantics for every DDL form the migrations use, including
the cascade Postgres performs on its own, and close with an independent check
over the real migration directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from analyze_postgres import SchemaParser
from analyze_sql_treesitter import TREESITTER_AVAILABLE, TreeSitterSchemaParser

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[4] / "agent-coordinator" / "database" / "migrations"
)


def _parse_regex(tmp_path: Path, sql: str) -> Any:
    path = tmp_path / "001_test.sql"
    path.write_text(sql)
    parser = SchemaParser()
    parser.parse_file(path)
    return parser


def _parse_treesitter(tmp_path: Path, sql: str) -> Any:
    (tmp_path / "001_test.sql").write_text(sql)
    parser = TreeSitterSchemaParser()
    parser.parse_directory(tmp_path)
    return parser


@pytest.fixture(
    params=[
        pytest.param(_parse_regex, id="regex"),
        pytest.param(
            _parse_treesitter,
            id="treesitter",
            marks=pytest.mark.skipif(
                not TREESITTER_AVAILABLE, reason="tree-sitter not installed"
            ),
        ),
    ]
)
def parse(request):
    """Parse SQL with each analyzer in turn — both must agree on removals."""
    return request.param


def _table_names(parser: Any) -> set[str]:
    return set(parser.tables)


def _index_names(parser: Any) -> list[str]:
    return [idx.name for idx in parser.indexes]


# ---------------------------------------------------------------------------
# DROP TABLE
# ---------------------------------------------------------------------------
class TestDropTable:
    def test_dropped_table_is_absent(self, parse, tmp_path):
        """The exact shape migration 031 uses."""
        parser = parse(
            tmp_path,
            """
            CREATE TABLE memory_working (
                id UUID PRIMARY KEY,
                agent_id TEXT NOT NULL
            );
            DROP TABLE IF EXISTS memory_working CASCADE;
            """,
        )
        assert _table_names(parser) == set()
        assert parser.build_output()["summary"]["total_tables"] == 0

    def test_plain_drop_without_if_exists_or_cascade(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE approval_queue (id UUID PRIMARY KEY);
            DROP TABLE approval_queue;
            """,
        )
        assert _table_names(parser) == set()

    def test_multiple_names_in_one_statement(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE a (id UUID PRIMARY KEY);
            CREATE TABLE b (id UUID PRIMARY KEY);
            CREATE TABLE c (id UUID PRIMARY KEY);
            DROP TABLE IF EXISTS a, b CASCADE;
            """,
        )
        assert _table_names(parser) == {"public.c"}

    def test_drop_takes_indexes_and_triggers_with_it(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE memory_working (
                id UUID PRIMARY KEY,
                agent_id TEXT NOT NULL
            );
            CREATE INDEX idx_memory_working_agent ON memory_working (agent_id);
            CREATE TRIGGER trg_mw_notify AFTER INSERT ON memory_working
                FOR EACH ROW EXECUTE FUNCTION notify_change();
            DROP TABLE IF EXISTS memory_working CASCADE;
            """,
        )
        assert _index_names(parser) == []
        assert parser.triggers == []

    def test_drop_takes_foreign_keys_in_both_directions(self, parse, tmp_path):
        """An FK *pointing at* a dropped table cannot survive it either.

        That is exactly why Postgres refuses the DROP without ``CASCADE``: it
        would have to remove the referencing constraint. Keeping the inbound
        edge would leave the graph with a dangling reference.
        """
        parser = parse(
            tmp_path,
            """
            CREATE TABLE agents (id UUID PRIMARY KEY);
            CREATE TABLE sessions (
                id UUID PRIMARY KEY,
                agent_id UUID REFERENCES agents(id)
            );
            CREATE TABLE notes (
                id UUID PRIMARY KEY,
                session_id UUID REFERENCES sessions(id)
            );
            DROP TABLE IF EXISTS sessions CASCADE;
            """,
        )
        assert _table_names(parser) == {"public.agents", "public.notes"}
        assert parser.foreign_keys == []

    def test_recreate_after_drop_keeps_the_new_definition(self, parse, tmp_path):
        """Migration 014's drop-and-recreate must not resurrect the old shape."""
        parser = parse(
            tmp_path,
            """
            CREATE TABLE approval_queue (
                id UUID PRIMARY KEY,
                changeset_id TEXT NOT NULL
            );
            DROP TABLE IF EXISTS approval_queue;
            CREATE TABLE approval_queue (
                id UUID PRIMARY KEY,
                agent_id TEXT NOT NULL
            );
            """,
        )
        columns = {c.name for c in parser.tables["public.approval_queue"].columns}
        assert columns == {"id", "agent_id"}


# ---------------------------------------------------------------------------
# DROP INDEX
# ---------------------------------------------------------------------------
class TestDropIndex:
    def test_dropped_index_is_absent(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE approval_queue (id UUID PRIMARY KEY, status TEXT);
            CREATE INDEX idx_approval_queue_status ON approval_queue (status);
            DROP INDEX IF EXISTS idx_approval_queue_status;
            """,
        )
        assert _index_names(parser) == []

    def test_drop_then_recreate_yields_exactly_one(self, parse, tmp_path):
        """Migration 014's real sequence — previously counted twice."""
        parser = parse(
            tmp_path,
            """
            CREATE TABLE approval_queue (id UUID PRIMARY KEY, status TEXT);
            CREATE INDEX idx_approval_queue_status ON approval_queue (status);
            DROP INDEX IF EXISTS idx_approval_queue_status;
            CREATE INDEX idx_approval_queue_status ON approval_queue (status, id);
            """,
        )
        assert _index_names(parser) == ["idx_approval_queue_status"]

    def test_other_indexes_survive(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE t (id UUID PRIMARY KEY, a TEXT, b TEXT);
            CREATE INDEX idx_a ON t (a);
            CREATE INDEX idx_b ON t (b);
            DROP INDEX idx_a;
            """,
        )
        assert _index_names(parser) == ["idx_b"]

    def test_schema_qualified_drop_matches_bare_name(self, parse, tmp_path):
        """CREATE INDEX names are bare; DROP INDEX may qualify them."""
        parser = parse(
            tmp_path,
            """
            CREATE TABLE t (id UUID PRIMARY KEY, a TEXT);
            CREATE INDEX idx_a ON t (a);
            DROP INDEX IF EXISTS public.idx_a;
            """,
        )
        assert _index_names(parser) == []


# ---------------------------------------------------------------------------
# DROP TRIGGER
# ---------------------------------------------------------------------------
class TestDropTrigger:
    def test_drop_then_recreate_yields_exactly_one(self, parse, tmp_path):
        """The idempotency pattern the migrations use for notify triggers."""
        sql = """
            CREATE TABLE work_queue (id UUID PRIMARY KEY);
            DROP TRIGGER IF EXISTS trg_work_queue_notify ON work_queue;
            CREATE TRIGGER trg_work_queue_notify AFTER INSERT ON work_queue
                FOR EACH ROW EXECUTE FUNCTION notify_change();
        """
        parser = parse(tmp_path, sql + sql)
        assert [t.name for t in parser.triggers] == ["trg_work_queue_notify"]

    def test_same_trigger_name_on_another_table_survives(self, parse, tmp_path):
        """Trigger names are unique per table, not per schema.

        The migrations reuse ``trg_*_notify`` across tables, so dropping by
        name alone would silently take an unrelated trigger with it.
        """
        parser = parse(
            tmp_path,
            """
            CREATE TABLE work_queue (id UUID PRIMARY KEY);
            CREATE TABLE audit_log (id UUID PRIMARY KEY);
            CREATE TRIGGER trg_notify AFTER INSERT ON work_queue
                FOR EACH ROW EXECUTE FUNCTION notify_change();
            CREATE TRIGGER trg_notify AFTER INSERT ON audit_log
                FOR EACH ROW EXECUTE FUNCTION notify_change();
            DROP TRIGGER IF EXISTS trg_notify ON work_queue;
            """,
        )
        assert [(t.name, t.table) for t in parser.triggers] == [
            ("trg_notify", "public.audit_log")
        ]


# ---------------------------------------------------------------------------
# DROP FUNCTION
# ---------------------------------------------------------------------------
class TestDropFunction:
    def test_dropped_function_is_absent(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE FUNCTION claim_task(p_agent_id TEXT) RETURNS JSONB AS $$
            BEGIN
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            DROP FUNCTION IF EXISTS claim_task(TEXT);
            """,
        )
        assert parser.functions == []

    def test_drop_without_argument_list(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE FUNCTION touch() RETURNS TRIGGER AS $$
            BEGIN
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            DROP FUNCTION touch;
            """,
        )
        assert parser.functions == []


# ---------------------------------------------------------------------------
# ALTER TABLE ... DROP COLUMN / DROP CONSTRAINT
# ---------------------------------------------------------------------------
class TestAlterTableDrops:
    def test_dropped_column_is_absent(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE t (id UUID PRIMARY KEY, stale TEXT, keep TEXT);
            ALTER TABLE t DROP COLUMN stale;
            """,
        )
        assert [c.name for c in parser.tables["public.t"].columns] == ["id", "keep"]

    def test_drop_column_if_exists_and_multiple(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE t (id UUID PRIMARY KEY, a TEXT, b TEXT, c TEXT);
            ALTER TABLE t DROP COLUMN IF EXISTS a, DROP COLUMN b;
            """,
        )
        assert [c.name for c in parser.tables["public.t"].columns] == ["id", "c"]

    def test_dropped_column_takes_its_index_and_fk(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE agents (id UUID PRIMARY KEY);
            CREATE TABLE t (
                id UUID PRIMARY KEY,
                agent_id UUID REFERENCES agents(id)
            );
            CREATE INDEX idx_t_agent ON t (agent_id);
            ALTER TABLE t DROP COLUMN agent_id;
            """,
        )
        assert parser.foreign_keys == []
        assert _index_names(parser) == []

    def test_dropped_column_leaves_the_primary_key_consistent(self, parse, tmp_path):
        """A dropped column must not linger in ``primary_key``.

        Asserted as absence rather than as the exact remaining list: the
        tree-sitter analyzer does not extract table-level composite
        ``PRIMARY KEY (a, b)`` constraints at all — it reports ``[]`` before
        any drop — which is a separate pre-existing gap, not a removal bug.
        """
        parser = parse(
            tmp_path,
            """
            CREATE TABLE t (
                a TEXT,
                b TEXT,
                PRIMARY KEY (a, b)
            );
            ALTER TABLE t DROP COLUMN b;
            """,
        )
        table = parser.tables["public.t"]
        assert "b" not in table.primary_key
        assert [c.name for c in table.columns] == ["a"]

    def test_drop_constraint_removes_a_tracked_foreign_key(self, parse, tmp_path):
        parser = parse(
            tmp_path,
            """
            CREATE TABLE agents (id UUID PRIMARY KEY);
            CREATE TABLE t (id UUID PRIMARY KEY, agent_id UUID);
            ALTER TABLE t ADD CONSTRAINT fk_t_agent
                FOREIGN KEY (agent_id) REFERENCES agents(id);
            ALTER TABLE t DROP CONSTRAINT IF EXISTS fk_t_agent;
            """,
        )
        assert parser.foreign_keys == []

    def test_drop_constraint_for_an_untracked_kind_is_a_no_op(self, parse, tmp_path):
        """CHECK/UNIQUE constraints are not modelled — dropping one changes nothing."""
        parser = parse(
            tmp_path,
            """
            CREATE TABLE t (id UUID PRIMARY KEY, phase TEXT);
            ALTER TABLE t DROP CONSTRAINT IF EXISTS phase_archetype_valid;
            """,
        )
        assert [c.name for c in parser.tables["public.t"].columns] == ["id", "phase"]

    def test_drop_column_on_unknown_table_does_not_crash(self, parse, tmp_path):
        """Migrations may alter a table created outside the scanned set."""
        parser = parse(tmp_path, "ALTER TABLE ghost DROP COLUMN gone;")
        assert _table_names(parser) == set()


# ---------------------------------------------------------------------------
# The real migration directory
# ---------------------------------------------------------------------------
def test_live_migrations_have_no_resurrected_tables():
    """No table whose last DDL action was a DROP may appear in the output.

    The expectation is derived from the migration text by an independent
    regex sweep rather than restated as a list of table names, so a future
    ``DROP TABLE`` is covered by this test the day it is written.
    """
    import re

    from analyze_postgres import _sort_key

    last_action: dict[str, str] = {}
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql"), key=_sort_key):
        text = path.read_text()
        for match in re.finditer(
            r"(?im)^\s*(?:(CREATE)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"|(DROP)\s+TABLE\s+(?:IF\s+EXISTS\s+)?)([\w.\"]+)",
            text,
        ):
            action = "create" if match.group(1) else "drop"
            name = match.group(3).strip('"').lower()
            if "." not in name:
                name = f"public.{name}"
            last_action[name] = action

    dropped = {name for name, action in last_action.items() if action == "drop"}
    assert dropped, (
        "no DROP TABLE found in the migrations — this test would pass "
        "vacuously; check the sweep still matches the migration syntax"
    )

    parser = SchemaParser()
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql"), key=_sort_key):
        parser.parse_file(path)

    resurrected = dropped & _table_names(parser)
    assert resurrected == set(), (
        f"dropped tables still present in the analysis: {sorted(resurrected)}"
    )
