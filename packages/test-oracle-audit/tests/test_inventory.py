"""Inventory stage tests (tasks 2.1; design D1).

Derived from the "Test Inventory" requirement of
``specs/test-oracle-audit/spec.md`` and the ``InventoryPayload`` schema. The
module under test, ``test_oracle_audit.inventory``, defines::

    build_inventory(suite: SuiteSpec, *, repo_root: Path, python: str | None = None)
        -> list[StageRecord]

Collection is run with ``python=sys.executable`` so no ``uv``/network is
needed: the implementation then shells out to ``[python, "-m", "pytest",
"--collect-only", ...]`` with cwd = the suite's project root.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_oracle_audit.inventory import build_inventory
from test_oracle_audit.records import (
    SuiteSpec,
    TestId,
    content_hash,
    to_entries,
    write_records,
)

PYTEST_ARGS = ("-p", "no:cacheprovider")


def _suite(name: str) -> SuiteSpec:
    # Paths in a SuiteSpec are relative to the repository root; the fixture
    # project *is* the repository root here.
    return SuiteSpec(
        name=name,
        project_root=".",
        test_paths=("tests",),
        source_roots=("src",),
        pytest_args=PYTEST_ARGS,
    )


def _build(root: Path, name: str = "fx") -> list:
    return build_inventory(_suite(name), repo_root=root, python=sys.executable)


@pytest.fixture
def basic(fixture_project):
    return fixture_project("inventory/basic")


@pytest.fixture
def broken(fixture_project):
    return fixture_project("inventory/broken")


def _by_node(records):
    return {r.test_id.node_id: r for r in records}


def test_records_are_valid_inventory_records(basic, schema_validator):
    """test-oracle-audit.8 (record shape): every record is a schema-valid ``inventory`` record.

    Covers the InventoryPayload contract: path, line_start, line_end, fixtures,
    covered_modules, plus an ``ok`` status and the expected node ids.
    """
    records = _build(basic)

    assert records, "inventory of a non-empty suite must not be empty"
    for record in records:
        assert record.stage == "inventory"
        assert record.status == "ok"
        schema_validator(record.to_json())
    assert set(_by_node(records)) == {
        "tests/test_calc.py::test_add",
        "tests/test_calc.py::test_sub_with_fixtures",
        "tests/test_cls.py::TestUtil::test_double_in_class",
        "tests/test_params.py::test_double[1]",
        "tests/test_params.py::test_double[2]",
        "tests/test_params.py::test_double[3]",
    }


def test_inventory_is_deterministic(basic, tmp_path):
    """test-oracle-audit.8: building twice over an unchanged suite gives byte-identical inventory.jsonl."""
    first = _build(basic)
    second = _build(basic)

    out_a, out_b = tmp_path / "a" / "inventory.jsonl", tmp_path / "b" / "inventory.jsonl"
    write_records(out_a, first)
    write_records(out_b, second)

    assert out_a.read_bytes() == out_b.read_bytes()
    assert out_a.read_bytes(), "inventory.jsonl must not be empty"


def test_inventory_order_is_sorted_by_node_id(basic):
    """test-oracle-audit.8: the output order is deterministic, sorted by pytest node id."""
    node_ids = [r.test_id.node_id for r in _build(basic)]

    assert node_ids == sorted(node_ids)


def test_parametrized_cases_are_distinct_entries_sharing_one_hash(basic):
    """test-oracle-audit.9: three parametrize cases give three node ids with the same content hash."""
    records = [r for r in _build(basic) if r.test_id.node_id.startswith("tests/test_params.py::test_double[")]

    assert len(records) == 3
    assert len({r.test_id.node_id for r in records}) == 3
    hashes = {r.test_id.content_hash for r in records}
    assert len(hashes) == 1
    source = (basic / "tests/test_params.py").read_text("utf-8")
    assert hashes == {content_hash(source, "test_double")}


def test_entry_carries_path_line_range_and_hash(basic):
    """test-oracle-audit.8: path is repo-relative; line range spans the test function; hash is content_hash."""
    record = _by_node(_build(basic))["tests/test_calc.py::test_add"]

    source = (basic / "tests/test_calc.py").read_text("utf-8")
    func = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "test_add")
    assert record.payload["path"] == "tests/test_calc.py"
    assert record.payload["line_start"] == func.lineno
    assert record.payload["line_end"] == func.end_lineno
    assert record.test_id.content_hash == content_hash(source, "test_add")


def test_entries_round_trip_through_to_entries(basic):
    """test-oracle-audit.8: ok inventory records convert to TestEntry with function and class names."""
    entries = {e.test_id.node_id: e for e in to_entries(_build(basic))}

    method = entries["tests/test_cls.py::TestUtil::test_double_in_class"]
    assert method.class_name == "TestUtil"
    assert method.function_name == "test_double_in_class"
    plain = entries["tests/test_calc.py::test_add"]
    assert plain.class_name is None
    assert plain.function_name == "test_add"
    assert isinstance(plain.test_id, TestId)


def test_fixtures_are_resolved(basic):
    """test-oracle-audit.8: the fixtures a test uses are listed; a fixture-free test lists none."""
    by_node = _by_node(_build(basic))

    used = by_node["tests/test_calc.py::test_sub_with_fixtures"].payload["fixtures"]
    assert {"tmp_path", "sample_value"} <= set(used)
    assert by_node["tests/test_calc.py::test_add"].payload["fixtures"] == []


def test_covered_modules_come_from_imports_of_source_modules(basic):
    """test-oracle-audit.8: covered modules are source-root modules the file imports, as dotted names.

    ``import pytest`` is not a source module and must not appear; ``from pkg
    import util`` reaches the module ``pkg.util``.
    """
    by_node = _by_node(_build(basic))

    assert by_node["tests/test_calc.py::test_add"].payload["covered_modules"] == ["pkg.calc"]
    assert by_node["tests/test_params.py::test_double[1]"].payload["covered_modules"] == ["pkg.util"]
    assert by_node["tests/test_cls.py::TestUtil::test_double_in_class"].payload["covered_modules"] == [
        "pkg.util"
    ]


def test_uncollectable_file_yields_error_record_and_does_not_abort(broken, schema_validator):
    """test-oracle-audit.10: an import-time failure gives a ``collection_error`` record; other files survive."""
    records = _build(broken)

    errors = [r for r in records if r.status == "error"]
    assert len(errors) == 1
    error = errors[0]
    assert error.stage == "inventory"
    assert error.reason == "collection_error"
    assert error.test_id.node_id == "tests/test_boom.py"
    for record in records:
        schema_validator(record.to_json())

    ok_ids = [r.test_id.node_id for r in records if r.status == "ok"]
    assert ok_ids == ["tests/test_good.py::test_add_works"]


def test_default_python_runs_collection_through_uv_project(basic, monkeypatch):
    """test-oracle-audit.8 (suite environment, D1): ``python=None`` collects via ``uv run --project``.

    ``subprocess.run`` is replaced by a recorder, so nothing is executed and the
    resulting (empty) collection output simply yields no records.
    """
    calls: list[list[str]] = []

    def fake_run(args, *a, **kw):
        calls.append([str(x) for x in args])
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    build_inventory(_suite("fx"), repo_root=basic)

    assert calls, "collection must run a subprocess"
    argv = calls[0]
    assert argv[:2] == ["uv", "run"]
    assert Path(argv[argv.index("--project") + 1]).resolve() == basic.resolve()
    assert "pytest" in argv
    assert "--collect-only" in argv


def test_inventory_json_lines_are_stable_text(basic):
    """test-oracle-audit.8: records serialise to identical JSON across runs (sort_keys)."""
    dump = lambda recs: [json.dumps(r.to_json(), sort_keys=True) for r in recs]

    assert dump(_build(basic)) == dump(_build(basic))
