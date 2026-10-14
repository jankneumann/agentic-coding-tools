"""Label ledger tests (task 1.1, wp-contracts): spec "Oracle-Source Vocabulary and Label Ledger".

Scenarios test-oracle-audit.1 (label recorded with content hash), .2 (stale on edit),
.3 (whitespace-only edits keep a label current), .4 (unknown label rejected) and .5 (test
files and pytest configuration untouched). Design D1, D2 and D9.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime
from pathlib import Path

import jsonschema
import pytest

from test_oracle_audit.ledger import LabelLedger, LabelState
from test_oracle_audit.records import content_hash, content_hash_of_file, validate

FIX = Path(__file__).resolve().parent / "fixtures" / "contracts"
ORIGINAL = (FIX / "ledger_subject_original.py").read_text()
WHITESPACE = (FIX / "ledger_subject_whitespace_edit.py").read_text()
LOGIC = (FIX / "ledger_subject_logic_edit.py").read_text()

NODE = "tests/test_x.py::test_y"
METHOD_NODE = "tests/test_x.py::TestGroup::test_method"
SEVEN = (
    "spec",
    "property",
    "reference_impl",
    "external_contract",
    "characterization",
    "current_impl_output",
    "none",
)


def _expected_hash(source: str, function_name: str) -> str:
    """sha256 of the ast.unparse-normalized function, computed independently of the package."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return "sha256:" + hashlib.sha256(ast.unparse(node).encode("utf-8")).hexdigest()
    raise AssertionError(function_name)


# --------------------------------------------------------------------------- scenario .1


def test_label_is_recorded_with_the_test_content_hash():
    """Labelling records node id, ast.unparse sha256, label, labeller and timestamp. (test-oracle-audit.1)"""
    h = content_hash(ORIGINAL, "test_y")
    assert h == _expected_hash(ORIGINAL, "test_y")
    ledger = LabelLedger()
    entry = ledger.add(NODE, h, "spec", "alice")
    assert entry.node_id == NODE
    assert entry.content_hash == h
    assert entry.label == "spec"
    assert entry.labeller == "alice"
    datetime.fromisoformat(entry.labelled_at)  # a parseable timestamp


def test_ledger_json_validates_against_label_ledger_schema():
    """A populated ledger serializes to JSON that satisfies label-ledger.schema.json. (test-oracle-audit.1)"""
    ledger = LabelLedger()
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice", note="from scenario 3")
    ledger.add(
        METHOD_NODE,
        content_hash(ORIGINAL, "test_method", "TestGroup"),
        "characterization",
        "alice",
    )
    data = ledger.to_json()
    validate(data, "label-ledger")
    assert data["schema_version"] == 1
    assert list(data["vocabulary"]) == list(SEVEN)
    assert [e["node_id"] for e in data["entries"]] == [NODE, METHOD_NODE]
    first = data["entries"][0]
    assert set(first) == {"node_id", "content_hash", "label", "labeller", "labelled_at", "note"}
    assert first["note"] == "from scenario 3"
    assert "note" not in data["entries"][1]


def test_empty_ledger_validates():
    """An empty ledger is a valid ledger. (test-oracle-audit.1)"""
    data = LabelLedger().to_json()
    validate(data, "label-ledger")
    assert data["entries"] == []


def test_explicit_timestamp_is_kept():
    """labelled_at supplied by the caller is recorded verbatim. (test-oracle-audit.1)"""
    ledger = LabelLedger()
    entry = ledger.add(
        NODE, content_hash(ORIGINAL, "test_y"), "none", "bob", labelled_at="2026-02-03T04:05:06Z"
    )
    assert entry.labelled_at == "2026-02-03T04:05:06Z"
    assert ledger.to_json()["entries"][0]["labelled_at"] == "2026-02-03T04:05:06Z"


@pytest.mark.parametrize("label", SEVEN)
def test_every_vocabulary_value_can_be_recorded(label):
    """All seven vocabulary values are accepted as labels. (test-oracle-audit.1)"""
    ledger = LabelLedger()
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), label, "alice")
    validate(ledger.to_json(), "label-ledger")


def test_sample_and_entry_type_are_carried_into_the_json():
    """The optional sample block and entry_type survive serialization (D9, reuse by ri-08). (test-oracle-audit.1)"""
    sample = {"seed": 7, "n": 2, "strata": {"flagged-bottom": [NODE], "unflagged-top": [METHOD_NODE]}}
    ledger = LabelLedger(entry_type="replay_output", sample=sample)
    data = ledger.to_json()
    validate(data, "label-ledger")
    assert data["entry_type"] == "replay_output"
    assert data["sample"] == sample


def test_default_entry_type_is_pytest_test():
    """entry_type defaults to pytest_test. (test-oracle-audit.1)"""
    assert LabelLedger().to_json().get("entry_type", "pytest_test") == "pytest_test"


# --------------------------------------------------------------------------- scenario .2


def test_label_goes_stale_when_the_test_logic_changes():
    """A logic edit changes the hash; the entry is reported stale. (test-oracle-audit.2)"""
    entry = LabelLedger().add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice")
    edited = content_hash(LOGIC, "test_y")
    assert edited != entry.content_hash
    assert LabelLedger.state(entry, edited) == LabelState.STALE
    assert LabelLedger.state(entry, entry.content_hash) == LabelState.CURRENT


def test_stale_method_label_is_detected_for_class_members():
    """Staleness works for methods addressed through their class. (test-oracle-audit.2)"""
    entry = LabelLedger().add(
        METHOD_NODE, content_hash(ORIGINAL, "test_method", "TestGroup"), "property", "alice"
    )
    edited = content_hash(LOGIC, "test_method", "TestGroup")
    assert LabelLedger.state(entry, edited) == LabelState.STALE


def test_stale_entries_are_excluded_from_current_labels():
    """The analysis view (current_labels) drops stale entries. (test-oracle-audit.2)"""
    ledger = LabelLedger()
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice")
    ledger.add(METHOD_NODE, content_hash(ORIGINAL, "test_method", "TestGroup"), "property", "alice")
    current = ledger.current_labels(
        {
            NODE: content_hash(LOGIC, "test_y"),  # edited -> stale
            METHOD_NODE: content_hash(ORIGINAL, "test_method", "TestGroup"),  # untouched
        }
    )
    assert set(current) == {METHOD_NODE}
    assert current[METHOD_NODE].label == "property"


def test_entry_for_a_test_absent_from_current_hashes_is_not_current():
    """A labelled test that no longer exists contributes no current label. (test-oracle-audit.2)"""
    ledger = LabelLedger()
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice")
    assert ledger.current_labels({}) == {}


def test_first_current_entry_per_node_wins():
    """With several labellers, the first current entry is used; stale ones are skipped (D9). (test-oracle-audit.2)"""
    h_old = content_hash(ORIGINAL, "test_y")
    h_new = content_hash(LOGIC, "test_y")
    ledger = LabelLedger()
    ledger.add(NODE, h_old, "none", "alice")  # stale once the test is edited
    ledger.add(NODE, h_new, "spec", "alice")  # relabelled after the edit
    ledger.add(NODE, h_new, "characterization", "bob")  # a later second opinion
    current = ledger.current_labels({NODE: h_new})
    assert current[NODE].label == "spec"
    assert current[NODE].labeller == "alice"


# --------------------------------------------------------------------------- scenario .3


def test_whitespace_and_comment_edits_keep_the_hash():
    """Whitespace/comment-only edits leave the content hash unchanged. (test-oracle-audit.3)"""
    assert content_hash(WHITESPACE, "test_y") == content_hash(ORIGINAL, "test_y")
    assert content_hash(WHITESPACE, "test_method", "TestGroup") == content_hash(
        ORIGINAL, "test_method", "TestGroup"
    )


def test_label_stays_current_after_a_whitespace_only_edit():
    """The label remains current when only formatting changed. (test-oracle-audit.3)"""
    ledger = LabelLedger()
    entry = ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice")
    after = content_hash(WHITESPACE, "test_y")
    assert LabelLedger.state(entry, after) == LabelState.CURRENT
    assert ledger.current_labels({NODE: after})[NODE].label == "spec"


def test_hash_changes_for_logic_but_not_for_other_functions_in_the_module():
    """Only the labelled function's own source feeds its hash. (test-oracle-audit.3)"""
    # A comment added to a different function must not move test_y's hash.
    variant = ORIGINAL.replace("[2, 4]", "[2, 4]  # unrelated comment")
    assert content_hash(variant, "test_y") == content_hash(ORIGINAL, "test_y")
    assert content_hash(LOGIC, "test_y") != content_hash(ORIGINAL, "test_y")


def test_content_hash_of_file_tracks_edits(tmp_path):
    """content_hash_of_file reflects the file on disk: formatting-stable, logic-sensitive. (test-oracle-audit.2, test-oracle-audit.3)"""
    path = tmp_path / "test_subject.py"
    path.write_text(ORIGINAL)
    before = content_hash_of_file(path, "test_y")
    path.write_text(WHITESPACE)
    assert content_hash_of_file(path, "test_y") == before
    path.write_text(LOGIC)
    assert content_hash_of_file(path, "test_y") != before


# --------------------------------------------------------------------------- scenario .4


def test_unknown_label_is_rejected_naming_the_allowed_values():
    """An out-of-vocabulary label raises ValueError listing all seven values. (test-oracle-audit.4)"""
    ledger = LabelLedger()
    with pytest.raises(ValueError) as exc:
        ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "gold_standard", "alice")
    for allowed in SEVEN:
        assert allowed in str(exc.value)
    assert ledger.to_json()["entries"] == []


def test_loading_a_ledger_file_with_an_unknown_label_fails(tmp_path):
    """A hand-edited ledger with an invalid label does not load silently. (test-oracle-audit.4)"""
    ledger = LabelLedger()
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice")
    data = ledger.to_json()
    data["entries"][0]["label"] = "gold_standard"
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        LabelLedger.load(path)


# --------------------------------------------------------------------------- persistence


def test_save_and_load_round_trip(tmp_path):
    """save then load restores the same entries. (test-oracle-audit.1)"""
    path = tmp_path / "docs" / "labels.json"
    ledger = LabelLedger(path=path)
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice", note="n")
    ledger.add(METHOD_NODE, content_hash(ORIGINAL, "test_method", "TestGroup"), "none", "bob")
    ledger.save()
    on_disk = json.loads(path.read_text())
    validate(on_disk, "label-ledger")
    loaded = LabelLedger.load(path)
    assert loaded.to_json() == ledger.to_json()


def test_save_to_an_explicit_path(tmp_path):
    """save(path) writes the schema-valid ledger there. (test-oracle-audit.1)"""
    ledger = LabelLedger()
    ledger.add(NODE, content_hash(ORIGINAL, "test_y"), "reference_impl", "alice")
    out = tmp_path / "labels.json"
    ledger.save(out)
    validate(json.loads(out.read_text()), "label-ledger")
    assert LabelLedger.load(out).to_json()["entries"][0]["label"] == "reference_impl"


def test_loading_a_missing_file_gives_an_empty_ledger(tmp_path):
    """A ledger path that does not exist yet loads as empty. (test-oracle-audit.1)"""
    ledger = LabelLedger.load(tmp_path / "nope" / "labels.json")
    assert ledger.to_json()["entries"] == []


def test_loaded_ledger_can_be_appended_to_and_resaved(tmp_path):
    """Load, add, save keeps earlier entries (append-only workflow of `label record`). (test-oracle-audit.1)"""
    path = tmp_path / "labels.json"
    first = LabelLedger.load(path)
    first.add(NODE, content_hash(ORIGINAL, "test_y"), "spec", "alice")
    first.save(path)
    second = LabelLedger.load(path)
    second.add(METHOD_NODE, content_hash(ORIGINAL, "test_method", "TestGroup"), "none", "alice")
    second.save(path)
    nodes = [e["node_id"] for e in LabelLedger.load(path).to_json()["entries"]]
    assert nodes == [NODE, METHOD_NODE]


def test_sample_survives_save_and_load(tmp_path):
    """The seeded sample block is persisted with the ledger (D9). (test-oracle-audit.1)"""
    sample = {"seed": 3, "n": 1, "strata": {"s": [NODE]}}
    path = tmp_path / "labels.json"
    LabelLedger(sample=sample).save(path)
    assert LabelLedger.load(path).to_json()["sample"] == sample


# --------------------------------------------------------------------------- scenario .5


def test_ledger_operations_leave_test_files_and_pytest_config_untouched(tmp_path):
    """Labelling hashes a test file but never writes to it, conftest.py or pyproject.toml. (test-oracle-audit.5)"""
    project = tmp_path / "proj"
    (project / "tests").mkdir(parents=True)
    files = {
        project / "tests" / "test_x.py": ORIGINAL,
        project / "tests" / "conftest.py": "import pytest\n",
        project / "pyproject.toml": "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
    }
    for path, text in files.items():
        path.write_text(text)
    before = {p: p.read_bytes() for p in files}
    mtimes = {p: p.stat().st_mtime_ns for p in files}

    ledger_path = tmp_path / "out" / "labels.json"
    ledger = LabelLedger.load(ledger_path)
    ledger.add(NODE, content_hash_of_file(project / "tests" / "test_x.py", "test_y"), "spec", "alice")
    ledger.save(ledger_path)
    LabelLedger.load(ledger_path).current_labels(
        {NODE: content_hash_of_file(project / "tests" / "test_x.py", "test_y")}
    )

    assert {p: p.read_bytes() for p in files} == before
    assert {p: p.stat().st_mtime_ns for p in files} == mtimes
    assert sorted(p.name for p in project.rglob("*") if p.is_file()) == sorted(p.name for p in files)
