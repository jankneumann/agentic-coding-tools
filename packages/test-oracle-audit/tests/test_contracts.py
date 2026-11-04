"""Contract tests for records, vocabulary, thresholds and schema parity (task 1.1, wp-contracts).

Expectations derive from the spec requirement "Oracle-Source Vocabulary and Label Ledger"
(test-oracle-audit.1 .. .4), contracts/ and design D1 / D2 / D9 only.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest
from openspec_paths import change_dir, repo_root_from

from test_oracle_audit import records, thresholds, vocabulary
from test_oracle_audit.records import (
    STAGES,
    STATUSES,
    StageRecord,
    content_hash,
    content_hash_of_file,
    load_schema,
    read_records,
    split_node_id,
    to_entries,
    validate,
    write_records,
)
from test_oracle_audit.records import TestEntry as Entry
from test_oracle_audit.records import TestId as Tid

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "contracts"
RUNTIME_SCHEMAS = HERE.parent / "src" / "test_oracle_audit" / "schemas"
CHANGE_ID = "pilot-test-quality-audit"

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
SEVEN = (
    "spec",
    "property",
    "reference_impl",
    "external_contract",
    "characterization",
    "current_impl_output",
    "none",
)
OK_PAYLOADS = json.loads((FIX / "stage_ok_payloads.json").read_text())


def _tid(node_id: str = "tests/test_x.py::test_y", h: str = HASH_A) -> Tid:
    return Tid(node_id, h)


def _contracts_dir() -> Path:
    return change_dir(repo_root_from(__file__, 3), CHANGE_ID) / "contracts" / "schemas"


# --------------------------------------------------------------------------- identity


def test_test_id_serializes_and_validates():
    """TestId round-trips through JSON and matches the TestId $def. (test-oracle-audit.1)"""
    tid = _tid()
    data = tid.to_json()
    assert data == {"node_id": "tests/test_x.py::test_y", "content_hash": HASH_A}
    assert Tid.from_json(json.loads(json.dumps(data))) == tid


@pytest.mark.parametrize(
    ("node_id", "expected"),
    [
        ("tests/test_x.py::test_y", ("tests/test_x.py", None, "test_y")),
        ("tests/test_x.py::TestA::test_y", ("tests/test_x.py", "TestA", "test_y")),
    ],
)
def test_split_node_id(node_id, expected):
    """A node id splits into file path, optional class and function. (test-oracle-audit.1)"""
    assert split_node_id(node_id) == expected


def test_content_hash_format_and_lookup_error():
    """content_hash is 'sha256:<64 hex>' and a missing function is a LookupError. (test-oracle-audit.1)"""
    src = (FIX / "ledger_subject_original.py").read_text()
    h = content_hash(src, "test_y")
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
    int(h.removeprefix("sha256:"), 16)
    with pytest.raises(LookupError):
        content_hash(src, "test_does_not_exist")


def test_content_hash_of_file_matches_source_hash():
    """The file-based hash equals the source-based hash, for functions and methods. (test-oracle-audit.1)"""
    path = FIX / "ledger_subject_original.py"
    src = path.read_text()
    assert content_hash_of_file(path, "test_y") == content_hash(src, "test_y")
    assert content_hash_of_file(path, "test_method", "TestGroup") == content_hash(
        src, "test_method", "TestGroup"
    )


# --------------------------------------------------------------------------- stage records


@pytest.mark.parametrize("stage", sorted(OK_PAYLOADS))
def test_ok_record_for_each_stage_validates_and_round_trips(stage, schema_validator):
    """An ok StageRecord with the stage's payload validates against stage-record. (test-oracle-audit.1)"""
    rec = StageRecord(_tid(), stage, "ok", OK_PAYLOADS[stage])
    data = rec.to_json()
    schema_validator(data)
    assert data["schema_version"] == 1
    assert data["stage"] == stage
    assert data["status"] == "ok"
    assert data["test_id"] == {"node_id": "tests/test_x.py::test_y", "content_hash": HASH_A}
    assert data["payload"] == OK_PAYLOADS[stage]
    assert StageRecord.from_json(json.loads(json.dumps(data))) == rec


def test_every_schema_stage_has_a_payload_fixture():
    """The fixture set covers exactly the stage enum of the schema. (test-oracle-audit.1)"""
    schema_stages = set(load_schema("stage-record")["properties"]["stage"]["enum"])
    assert schema_stages == set(OK_PAYLOADS) == set(STAGES)
    assert set(STATUSES) == {"ok", "degraded", "skipped", "error"}


def test_judged_record_defaults_to_judgment_evidence(schema_validator):
    """Judged records carry evidence_class 'judgment' by default. (test-oracle-audit.1)"""
    data = StageRecord(_tid(), "judged", "ok", OK_PAYLOADS["judged"]).to_json()
    assert data["evidence_class"] == "judgment"
    schema_validator(data)


def test_judged_record_without_judgment_evidence_is_rejected(schema_validator):
    """The schema rejects a judged record whose evidence_class is not judgment. (test-oracle-audit.1)"""
    data = StageRecord(_tid(), "judged", "ok", OK_PAYLOADS["judged"]).to_json()
    wrong = copy.deepcopy(data)
    wrong["evidence_class"] = "deterministic"
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(wrong)
    missing = copy.deepcopy(data)
    del missing["evidence_class"]
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(missing)


@pytest.mark.parametrize("stage", sorted(OK_PAYLOADS))
def test_ok_record_with_wrong_payload_is_rejected(stage, schema_validator):
    """An ok record's payload must match its stage's $defs payload. (test-oracle-audit.1)"""
    data = StageRecord(_tid(), stage, "ok", OK_PAYLOADS[stage]).to_json()
    data["payload"] = {}
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(data)


def test_ok_record_payload_of_another_stage_is_rejected(schema_validator):
    """A static payload is not acceptable on an ok mutation record. (test-oracle-audit.1)"""
    data = StageRecord(_tid(), "mutation", "ok", OK_PAYLOADS["mutation"]).to_json()
    data["payload"] = OK_PAYLOADS["static"]
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(data)


@pytest.mark.parametrize("status", ["degraded", "skipped", "error"])
def test_non_ok_record_needs_a_reason(status, schema_validator):
    """A non-ok StageRecord requires a reason, both in the dataclass and the schema. (test-oracle-audit.1)"""
    with pytest.raises(ValueError):
        StageRecord(_tid(), "mutation", status, {})
    data = StageRecord(_tid(), "mutation", status, {}, reason="mutmut_probe_failed").to_json()
    assert data["reason"] == "mutmut_probe_failed"
    schema_validator(data)
    del data["reason"]
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(data)


def test_degraded_record_may_carry_a_partial_payload(schema_validator):
    """Degraded records are exempt from the stage payload shape. (test-oracle-audit.1)"""
    rec = StageRecord(_tid(), "mutation", "degraded", {"backend": "ast"}, reason="no_backend")
    schema_validator(rec.to_json())


def test_unknown_stage_or_status_is_rejected():
    """StageRecord rejects stage or status values outside the schema enums. (test-oracle-audit.1)"""
    with pytest.raises(ValueError):
        StageRecord(_tid(), "bogus", "ok", {})
    with pytest.raises(ValueError):
        StageRecord(_tid(), "static", "bogus", {}, reason="x")


def test_stage_record_schema_rejects_unknown_top_level_field(schema_validator):
    """stage-record has additionalProperties false. (test-oracle-audit.1)"""
    data = StageRecord(_tid(), "static", "ok", OK_PAYLOADS["static"]).to_json()
    data["extra"] = 1
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(data)


def test_test_id_hash_pattern_is_enforced(schema_validator):
    """content_hash must match ^sha256:[0-9a-f]{64}$. (test-oracle-audit.1)"""
    data = StageRecord(_tid(), "static", "ok", OK_PAYLOADS["static"]).to_json()
    data["test_id"]["content_hash"] = "md5:abc"
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(data)


# --------------------------------------------------------------------------- inventory entries


def _entry(node="tests/test_x.py::TestA::test_y", h=HASH_A) -> Entry:
    return Entry(
        test_id=Tid(node, h),
        path="tests/test_x.py",
        line_start=10,
        line_end=14,
        function_name="test_y",
        class_name="TestA",
        fixtures=("tmp_path", "monkeypatch"),
        covered_modules=("evaluation.metrics",),
    )


def test_test_entry_round_trips_through_an_inventory_record(schema_validator):
    """TestEntry <-> inventory StageRecord, and the record validates. (test-oracle-audit.1)"""
    entry = _entry()
    rec = entry.to_record()
    assert rec.stage == "inventory"
    assert rec.status == "ok"
    data = rec.to_json()
    schema_validator(data)
    assert data["payload"]["path"] == "tests/test_x.py"
    assert (data["payload"]["line_start"], data["payload"]["line_end"]) == (10, 14)
    assert list(data["payload"]["fixtures"]) == ["tmp_path", "monkeypatch"]
    assert list(data["payload"]["covered_modules"]) == ["evaluation.metrics"]
    assert Entry.from_record(StageRecord.from_json(json.loads(json.dumps(data)))) == entry


def test_to_entries_rebuilds_entries_from_records():
    """to_entries turns inventory records back into TestEntry objects. (test-oracle-audit.1)"""
    first = _entry("tests/test_x.py::TestA::test_y", HASH_A)
    second = _entry("tests/test_x.py::TestA::test_z", HASH_B)
    out = list(to_entries([first.to_record(), second.to_record()]))
    assert out == [first, second]


# --------------------------------------------------------------------------- JSONL io


def test_write_and_read_records_round_trip(tmp_path):
    """write_records emits one JSON line per record; read_records restores them. (test-oracle-audit.1)"""
    recs = [
        StageRecord(_tid("tests/test_x.py::test_a"), "static", "ok", OK_PAYLOADS["static"]),
        StageRecord(_tid("tests/test_x.py::test_b", HASH_B), "mutation", "skipped", {}, reason="dry_run"),
        StageRecord(_tid("tests/test_x.py::test_c"), "judged", "ok", OK_PAYLOADS["judged"]),
    ]
    out = tmp_path / "static.jsonl"
    write_records(out, recs)
    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    assert len(lines) == 3
    for ln in lines:
        validate(json.loads(ln), "stage-record")
    assert list(read_records(out)) == recs


# --------------------------------------------------------------------------- other schemas


def test_every_contract_schema_is_a_valid_json_schema():
    """Each contract file is itself a valid draft 2020-12 schema. (test-oracle-audit.1)"""
    files = sorted(_contracts_dir().glob("*.schema.json"))
    assert len(files) == 4
    for f in files:
        jsonschema.Draft202012Validator.check_schema(json.loads(f.read_text()))


def test_load_schema_covers_the_core_schemas():
    """load_schema serves the four validated contracts by name. (test-oracle-audit.1)"""
    for name in ("stage-record", "label-ledger", "mutation-result", "analysis-report"):
        assert name in records.SCHEMA_NAMES
        assert isinstance(load_schema(name), dict)


def test_mutation_result_instance_validates(schema_validator):
    """A per-mutant record with per-test attribution validates. (test-oracle-audit.1)"""
    inst = json.loads((FIX / "mutation_result_valid.json").read_text())
    schema_validator(inst, "mutation-result")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(status="mystery"),
        lambda d: d.update(backend="other"),
        lambda d: d.update(extra=1),
        lambda d: d.pop("seed"),
        lambda d: d.update(killed_by=["a", "a"]),
    ],
    ids=["status", "backend", "extra-field", "missing-seed", "duplicate-killed-by"],
)
def test_mutation_result_violations_are_rejected(mutate, schema_validator):
    """mutation-result rejects out-of-contract values. (test-oracle-audit.1)"""
    inst = json.loads((FIX / "mutation_result_valid.json").read_text())
    mutate(inst)
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(inst, "mutation-result")


def test_minimal_analysis_report_validates(schema_validator):
    """A minimal analysis report validates against analysis-report. (test-oracle-audit.1)"""
    schema_validator(json.loads((FIX / "analysis_report_minimal.json").read_text()), "analysis-report")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(advisory=False),
        lambda d: d["open_decisions"].pop(),
        lambda d: d.pop("disagreements"),
        lambda d: d["metrics"][0].pop("value"),
        lambda d: d["metrics"][1].update(value=0.5),
    ],
    ids=[
        "not-advisory",
        "one-open-decision",
        "no-disagreements",
        "ok-metric-no-value",
        "insufficient-with-value",
    ],
)
def test_analysis_report_violations_are_rejected(mutate, schema_validator):
    """analysis-report rejects reports that overclaim or omit required parts. (test-oracle-audit.1)"""
    inst = json.loads((FIX / "analysis_report_minimal.json").read_text())
    mutate(inst)
    with pytest.raises(jsonschema.ValidationError):
        schema_validator(inst, "analysis-report")


# --------------------------------------------------------------------------- vocabulary


def test_vocabulary_has_exactly_the_seven_values():
    """The oracle-source vocabulary is the closed seven-value set. (test-oracle-audit.2)"""
    assert len(vocabulary.ORACLE_SOURCES) == 7
    assert set(vocabulary.ORACLE_SOURCES) == set(SEVEN)
    assert len(set(vocabulary.ORACLE_SOURCES)) == 7


def test_vocabulary_binary_partition():
    """intent-derived = spec/property/reference_impl/external_contract; the rest are not. (test-oracle-audit.2)"""
    intent = {"spec", "property", "reference_impl", "external_contract"}
    not_intent = {"characterization", "current_impl_output", "none"}
    assert set(vocabulary.INTENT_DERIVED) == intent
    assert set(vocabulary.NOT_INTENT_DERIVED) == not_intent
    assert set(vocabulary.INTENT_DERIVED).isdisjoint(vocabulary.NOT_INTENT_DERIVED)
    assert set(vocabulary.INTENT_DERIVED) | set(vocabulary.NOT_INTENT_DERIVED) == set(
        vocabulary.ORACLE_SOURCES
    )


def test_impl_derived_is_the_declared_and_undeclared_pair():
    """Design D2: impl-derived = characterization (declared) + current_impl_output (undeclared); 'none' is no oracle. (test-oracle-audit.2)"""
    assert set(vocabulary.IMPL_DERIVED) == {"characterization", "current_impl_output"}
    assert set(vocabulary.IMPL_DERIVED) <= set(vocabulary.NOT_INTENT_DERIVED)


@pytest.mark.parametrize("label", SEVEN)
def test_is_intent_derived_follows_the_partition(label):
    """is_intent_derived agrees with the D2 split for every value. (test-oracle-audit.2)"""
    vocabulary.validate_label(label)
    assert vocabulary.is_intent_derived(label) is (
        label in {"spec", "property", "reference_impl", "external_contract"}
    )


@pytest.mark.parametrize("bad", ["Spec", "oracle", "", "specs", "unknown"])
def test_validate_label_rejects_values_outside_the_vocabulary(bad):
    """An unknown label raises ValueError naming all allowed values. (test-oracle-audit.4)"""
    with pytest.raises(ValueError) as exc:
        vocabulary.validate_label(bad)
    for allowed in SEVEN:
        assert allowed in str(exc.value)


# --------------------------------------------------------------------------- thresholds


def test_load_thresholds_default_provides_required_keys():
    """The shipped config loads and carries both display thresholds. (test-oracle-audit.2)"""
    cfg = thresholds.load_thresholds()
    for key in ("judged_impl_derived_p", "co_change_high"):
        assert 0.0 <= cfg[key] <= 1.0


def test_load_thresholds_from_explicit_path():
    """load_thresholds(path) reads the given file. (test-oracle-audit.2)"""
    cfg = thresholds.load_thresholds(FIX / "thresholds_ok.json")
    assert cfg["judged_impl_derived_p"] == pytest.approx(0.35)
    assert cfg["co_change_high"] == pytest.approx(0.65)


def test_load_thresholds_missing_key_names_it():
    """A missing required key raises KeyError naming that key. (test-oracle-audit.2)"""
    with pytest.raises(KeyError) as exc:
        thresholds.load_thresholds(FIX / "thresholds_missing_key.json")
    assert "co_change_high" in str(exc.value)


def test_load_thresholds_names_every_missing_key(tmp_path):
    """With no keys at all, both required names appear in the error. (test-oracle-audit.2)"""
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(KeyError) as exc:
        thresholds.load_thresholds(p)
    assert "co_change_high" in str(exc.value)
    assert "judged_impl_derived_p" in str(exc.value)


def test_tercile_cutpoints_split_a_known_list_into_thirds():
    """33.3rd/66.7th percentiles with linear interpolation on 1..9. (test-oracle-audit.2)"""
    values = [float(v) for v in range(1, 10)]
    t1, t2 = thresholds.tercile_cutpoints(values)
    assert t1 == pytest.approx(3.664, abs=0.01)
    assert t2 == pytest.approx(6.336, abs=0.01)
    labels = [thresholds.tercile_of(v, (t1, t2)) for v in values]
    assert labels == ["bottom"] * 3 + ["middle"] * 3 + ["top"] * 3


def test_tercile_cutpoints_interpolate_linearly_and_ignore_order():
    """Ten values 1..10, shuffled, give 3.997 / 7.003 (linear interpolation). (test-oracle-audit.2)"""
    t1, t2 = thresholds.tercile_cutpoints([7, 1, 10, 3, 5, 9, 2, 8, 4, 6])
    assert t1 == pytest.approx(3.997, abs=0.01)
    assert t2 == pytest.approx(7.003, abs=0.01)
    assert t1 <= t2


def test_tercile_cutpoints_reject_empty_input():
    """No values means no cut-points: ValueError. (test-oracle-audit.2)"""
    with pytest.raises(ValueError):
        thresholds.tercile_cutpoints([])


def test_tercile_of_boundaries():
    """bottom is <= t1, middle is <= t2, otherwise top. (test-oracle-audit.2)"""
    cuts = (3.0, 6.0)
    assert thresholds.tercile_of(0.0, cuts) == "bottom"
    assert thresholds.tercile_of(3.0, cuts) == "bottom"
    assert thresholds.tercile_of(3.1, cuts) == "middle"
    assert thresholds.tercile_of(6.0, cuts) == "middle"
    assert thresholds.tercile_of(6.1, cuts) == "top"


# --------------------------------------------------------------------------- schema parity


def test_runtime_schema_copies_are_byte_identical_to_contracts():
    """Runtime schema copies mirror the change's contracts/schemas byte for byte. (test-oracle-audit.1)"""
    contracts = _contracts_dir()
    assert contracts.is_dir(), f"contracts directory not found: {contracts}"
    contract_files = {p.name for p in contracts.iterdir() if p.is_file() and p.suffix == ".json"}
    runtime_files = {p.name for p in RUNTIME_SCHEMAS.iterdir() if p.is_file() and p.suffix == ".json"}
    assert runtime_files, "no runtime schema copies found"
    assert runtime_files == contract_files
    for name in sorted(runtime_files):
        assert (RUNTIME_SCHEMAS / name).read_bytes() == (contracts / name).read_bytes(), name
