"""Static-check stage tests (task 2.3; design D1).

Derived from the "Deterministic Static Test Checks" requirement of
``specs/test-oracle-audit/spec.md`` and the ``StaticPayload`` schema. The module
under test, ``test_oracle_audit.static_checks``, defines::

    RULE_IDS                      # the six stable rule ids
    run_static(entries: Sequence[TestEntry], *, repo_root: Path) -> list[StageRecord]

``run_static`` emits one ``static`` record per entry, payload ``{"rules": [...]}``
with the rule ids sorted, status ``ok``, ordered by node id. It is AST-only: the
test files are read from ``repo_root / entry.path`` and never imported.

Entries are built here from the fixture sources (not through the inventory
stage) so this suite is independent of ``inventory.py``. Source modules named by
``covered_modules`` (e.g. ``pkg.mod``) live at ``<repo_root>/src/pkg/mod.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from test_oracle_audit.records import TestEntry, TestId, content_hash, load_schema
from test_oracle_audit.static_checks import RULE_IDS, run_static

EXPECTED_RULES = {
    "assertion_free",
    "mock_assertion_dominant",
    "private_attribute_assert",
    "private_import",
    "mirrored_test_file",
    "unscoped_patch",
}


def _entries(root: Path, rel: str, covered: tuple[str, ...]) -> list[TestEntry]:
    """One TestEntry per ``test_*`` function (top level or in a class) of ``root/rel``."""
    source = (root / rel).read_text("utf-8")
    tree = ast.parse(source)
    found: list[tuple[str | None, ast.FunctionDef]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            found.append((None, node))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            found.extend(
                (node.name, n) for n in node.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
            )
    entries = []
    for cls, func in found:
        node_id = f"{rel}::{cls}::{func.name}" if cls else f"{rel}::{func.name}"
        entries.append(
            TestEntry(
                test_id=TestId(node_id, content_hash(source, func.name, cls)),
                path=rel,
                line_start=func.lineno,
                line_end=func.end_lineno or func.lineno,
                function_name=func.name,
                class_name=cls,
                covered_modules=covered,
            )
        )
    return entries


def _rules(root: Path, rel: str, covered: tuple[str, ...]) -> dict[str, list[str]]:
    """``{function_name: rules}`` for every test in ``rel`` (also checks the common record shape)."""
    entries = _entries(root, rel, covered)
    records = run_static(entries, repo_root=root)
    assert len(records) == len(entries)
    out = {}
    for record in records:
        assert record.stage == "static"
        assert record.status == "ok"
        out[record.test_id.node_id.split("::")[-1]] = record.payload["rules"]
    return out


@pytest.fixture
def rules_project(fixture_project):
    return fixture_project("static/rules")


MOD = ("pkg.mod",)


def test_rule_ids_are_the_six_stable_ids():
    """test-oracle-audit.11-.17: the six rule ids are stable and match the StaticPayload schema enum."""
    assert set(RULE_IDS) == EXPECTED_RULES
    assert len(RULE_IDS) == 6
    schema_enum = load_schema("stage-record")["$defs"]["StaticPayload"]["properties"]["rules"]["items"]["enum"]
    assert set(RULE_IDS) == set(schema_enum)


def test_records_validate_against_stage_record_schema(rules_project, schema_validator):
    """test-oracle-audit.14: every static record is schema-valid with a sorted, unique rule list."""
    entries = _entries(rules_project, "tests/test_combo.py", MOD)
    for record in run_static(entries, repo_root=rules_project):
        data = record.to_json()
        schema_validator(data)
        assert data["payload"]["rules"] == sorted(set(data["payload"]["rules"]))


# --- assertion_free ---------------------------------------------------------


def test_assertion_free_positive(rules_project):
    """test-oracle-audit.11: a test with no assert, raises/warns context or assert* call is flagged."""
    rules = _rules(rules_project, "tests/test_assertion_free.py", MOD)

    assert rules["test_no_assert"] == ["assertion_free"]


@pytest.mark.parametrize(
    "name",
    [
        "test_with_assert",
        "test_with_raises",
        "test_with_warns",
        "test_with_deprecated_call",
        "test_with_assert_method",
    ],
)
def test_assertion_free_negative(rules_project, name):
    """test-oracle-audit.11: any assert statement, pytest.raises/warns/deprecated_call, or assert* method call clears the rule."""
    rules = _rules(rules_project, "tests/test_assertion_free.py", MOD)

    assert "assertion_free" not in rules[name]
    assert rules[name] == []


# --- mock_assertion_dominant -----------------------------------------------


@pytest.mark.parametrize(
    "name", ["test_mock_heavy", "test_mock_called_attribute_only", "test_mock_not_called_only"]
)
def test_mock_assertion_dominant_positive(rules_project, name):
    """test-oracle-audit.12: mock-interaction assertions (assert_called*, call_count, call_args, called) outnumber the rest."""
    rules = _rules(rules_project, "tests/test_mock_dominant.py", MOD)

    assert rules[name] == ["mock_assertion_dominant"]


@pytest.mark.parametrize("name", ["test_mock_tie", "test_mock_minority"])
def test_mock_assertion_dominant_negative(rules_project, name):
    """test-oracle-audit.12: equal or fewer mock assertions than other assertions does not fire (strictly greater)."""
    rules = _rules(rules_project, "tests/test_mock_dominant.py", MOD)

    assert rules[name] == []


# --- private_attribute_assert ----------------------------------------------


@pytest.mark.parametrize("name", ["test_private_assert", "test_private_in_assert_method"])
def test_private_attribute_assert_positive(rules_project, name):
    """test-oracle-audit.13: asserting on ``obj._x`` (in an assert or an assert* argument) is flagged."""
    rules = _rules(rules_project, "tests/test_private_attr.py", MOD)

    assert rules[name] == ["private_attribute_assert"]


@pytest.mark.parametrize("name", ["test_private_outside_assert", "test_dunder_attribute", "test_self_private"])
def test_private_attribute_assert_negative(rules_project, name):
    """test-oracle-audit.13: private access outside assertions, dunder attributes, and ``self._x`` do not fire."""
    rules = _rules(rules_project, "tests/test_private_attr.py", MOD)

    assert rules[name] == []


# --- private_import ---------------------------------------------------------


@pytest.mark.parametrize("name", ["test_calls_private_helper", "test_private_module_attribute"])
def test_private_import_positive(rules_project, name):
    """test-oracle-audit.15: ``from pkg.mod import _helper`` (called) and ``m._secret`` via ``import pkg.mod as m`` fire."""
    rules = _rules(rules_project, "tests/test_private_import.py", MOD)

    assert rules[name] == ["private_import"]


@pytest.mark.parametrize("name", ["test_public_only", "test_test_helper_private_name", "test_dunder_import"])
def test_private_import_negative(rules_project, name):
    """test-oracle-audit.15: public names, dunder names, and private names from a *test* module do not fire."""
    rules = _rules(rules_project, "tests/test_private_import_negative.py", MOD)

    assert rules[name] == []


# --- mirrored_test_file -----------------------------------------------------


def test_mirrored_test_file_positive_imported_names(rules_project):
    """test-oracle-audit.16: every public function of the mirrored module is called in exactly one test; fires for every test."""
    rules = _rules(rules_project, "tests/test_mirror.py", ("pkg.mirror",))

    assert rules == {"test_alpha": ["mirrored_test_file"], "test_beta": ["mirrored_test_file"]}


def test_mirrored_test_file_positive_attribute_calls(rules_project):
    """test-oracle-audit.16: calls through ``module.func`` attribute access count as calls by name."""
    rules = _rules(rules_project, "tests/test_mirror_attr.py", ("pkg.mirror_attr",))

    assert rules == {"test_alpha": ["mirrored_test_file"], "test_beta": ["mirrored_test_file"]}


def test_mirrored_test_file_negative_public_function_uncalled(rules_project):
    """test-oracle-audit.16: a public function (gamma) that no test calls means the file is not a mirror."""
    rules = _rules(rules_project, "tests/test_partial.py", ("pkg.partial",))

    assert rules == {"test_alpha": [], "test_beta": []}


def test_mirrored_test_file_negative_function_in_two_tests(rules_project):
    """test-oracle-audit.16: a public function called in two tests (not exactly one) does not fire."""
    rules = _rules(rules_project, "tests/test_shared.py", ("pkg.shared",))

    assert rules == {"test_first": [], "test_second": []}


def test_mirrored_rule_needs_the_name_to_resolve_to_a_covered_module(rules_project):
    """test-oracle-audit.16: with no covered module named like the file, the rule cannot fire."""
    rules = _rules(rules_project, "tests/test_mirror.py", ("pkg.other",))

    assert rules == {"test_alpha": [], "test_beta": []}


# --- unscoped_patch ---------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "test_patch_stdlib",
        "test_patch_builtin",
        "test_patch_uncovered_module",
        "test_patch_object_stdlib",
        "test_patch_decorator",
    ],
)
def test_unscoped_patch_positive(rules_project, name):
    """test-oracle-audit.17: patching stdlib/builtin names or an uncovered module is flagged (patch, patch.object, monkeypatch.setattr)."""
    rules = _rules(rules_project, "tests/test_unscoped_patch.py", MOD)

    assert rules[name] == ["unscoped_patch"]


@pytest.mark.parametrize("name", ["test_patch_in_scope", "test_monkeypatch_in_scope"])
def test_unscoped_patch_negative(rules_project, name):
    """test-oracle-audit.17: patching a name inside a covered module (pkg.mod) does not fire."""
    rules = _rules(rules_project, "tests/test_unscoped_patch.py", MOD)

    assert rules[name] == []


# --- combination, behaviour-only, ordering ----------------------------------


def test_multiple_rules_are_all_recorded_sorted(rules_project):
    """test-oracle-audit.13, test-oracle-audit.17: a test firing two rules lists both, sorted by id."""
    rules = _rules(rules_project, "tests/test_combo.py", MOD)

    assert rules["test_combo"] == ["private_attribute_assert", "unscoped_patch"]


def test_behaviour_only_test_fires_no_rule(rules_project):
    """test-oracle-audit.14: calling public functions and asserting on return values: empty rule list, status ok."""
    entries = _entries(rules_project, "tests/test_behaviour_only.py", MOD)
    records = run_static(entries, repo_root=rules_project)

    assert len(records) == 2
    for record in records:
        assert record.status == "ok"
        assert record.payload == {"rules": []}


def test_output_is_deterministic_and_sorted_by_node_id(rules_project):
    """test-oracle-audit.11-.17: record order does not depend on input order; sorted by node id."""
    entries = _entries(rules_project, "tests/test_private_attr.py", MOD) + _entries(
        rules_project, "tests/test_mock_dominant.py", MOD
    )

    forward = run_static(entries, repo_root=rules_project)
    backward = run_static(list(reversed(entries)), repo_root=rules_project)

    assert [r.to_json() for r in forward] == [r.to_json() for r in backward]
    node_ids = [r.test_id.node_id for r in forward]
    assert node_ids == sorted(node_ids)
    assert len(node_ids) == len(entries)


# --- never imports test modules ---------------------------------------------


def test_static_checks_never_import_test_modules(fixture_project):
    """test-oracle-audit.18: a test module raising RuntimeError at import is still analysed (every test recorded)."""
    root = fixture_project("static/import_boom")
    entries = _entries(root, "tests/test_boom.py", ("pkg.calc",))
    assert {e.function_name for e in entries} == {"test_unchecked", "test_checked"}

    records = run_static(entries, repo_root=root)

    assert {r.test_id.node_id for r in records} == {e.test_id.node_id for e in entries}
    by_name = {r.test_id.node_id.split("::")[-1]: r for r in records}
    assert all(r.status == "ok" for r in records)
    assert by_name["test_unchecked"].payload["rules"] == ["assertion_free"]
    assert by_name["test_checked"].payload["rules"] == []
    assert not [m for m in sys.modules if m.endswith("test_boom")]
