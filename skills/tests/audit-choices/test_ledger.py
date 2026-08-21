"""Tests for the ledger writer (skills/audit-choices/scripts/choices_ledger.py).

Design D2 (choices.json is the source of truth; choices.md is rendered from
it), D3 (content-derived stable_id), D4 (six-field artifact header copied
from skills/prioritize-proposals/scripts/artifact_header.py).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "decision-choices.schema.json"
sys.path.insert(0, str(SCRIPTS_DIR))

import choices_ledger  # noqa: E402


def _provenance(files=None, commits=None):
    return {
        "commits": commits or ["abc1234"],
        "files": files or ["skills/example/scripts/client.py"],
    }


def _entry_kwargs(**overrides):
    base = dict(
        choice="Chose per-request retry budget of 3",
        scenario=(
            "WHEN a downstream call times out THEN the client retries up to 3 "
            "times with backoff instead of failing fast."
        ),
        gap="The design left retry policy on downstream timeouts unspecified.",
        reach="Future callers inherit a 3-retry default unless overridden.",
        verdict="sound",
        verdict_rationale="Matches the conservative default used elsewhere.",
        confidence="medium",
        provenance=_provenance(),
        self_reported=True,
    )
    base.update(overrides)
    return base


class TestStableId:
    def test_stable_id_idempotent(self):
        id1 = choices_ledger.compute_stable_id(
            choice="Chose retry budget of 3",
            files=["a.py", "b.py"],
            gap="retry policy unspecified",
        )
        id2 = choices_ledger.compute_stable_id(
            choice="Chose retry budget of 3",
            files=["a.py", "b.py"],
            gap="retry policy unspecified",
        )
        assert id1 == id2

    def test_stable_id_changes_with_gap_text(self):
        id1 = choices_ledger.compute_stable_id(
            choice="Chose retry budget of 3", files=["a.py"], gap="gap one"
        )
        id2 = choices_ledger.compute_stable_id(
            choice="Chose retry budget of 3", files=["a.py"], gap="gap two"
        )
        assert id1 != id2

    def test_stable_id_matches_schema_pattern(self):
        sid = choices_ledger.compute_stable_id(choice="X", files=["f.py"], gap="g")
        assert 16 <= len(sid) <= 64
        assert all(c in "0123456789abcdef" for c in sid)

    def test_stable_id_insensitive_to_file_order_and_case(self):
        id1 = choices_ledger.compute_stable_id(
            choice="Choice Text", files=["b.py", "a.py"], gap="Gap Text"
        )
        id2 = choices_ledger.compute_stable_id(
            choice="  choice text  ", files=["a.py", "b.py"], gap="  gap text  "
        )
        assert id1 == id2


class TestHeader:
    def test_header_has_six_fields(self):
        header = choices_ledger.make_header(
            now=datetime(2026, 8, 21, tzinfo=timezone.utc),
            git_sha="a" * 40,
            run_id="run-001",
        )
        assert set(header.keys()) == {
            "schema_version",
            "generated_at",
            "git_sha",
            "generator",
            "run_id",
            "event_kind",
        }

    def test_generator_starts_with_audit_choices(self):
        header = choices_ledger.make_header(
            now=datetime(2026, 8, 21, tzinfo=timezone.utc), git_sha="a" * 40, run_id="r"
        )
        assert header["generator"].startswith("audit-choices@")

    def test_event_kind_is_choices_ledger(self):
        header = choices_ledger.make_header(
            now=datetime(2026, 8, 21, tzinfo=timezone.utc), git_sha="a" * 40, run_id="r"
        )
        assert header["event_kind"] == "choices-ledger"

    def test_rejects_naive_datetime(self):
        with pytest.raises(ValueError):
            choices_ledger.make_header(now=datetime(2026, 8, 21), git_sha="a" * 40, run_id="r")


class TestWriteLedger:
    def _header(self):
        return choices_ledger.make_header(
            now=datetime(2026, 8, 21, tzinfo=timezone.utc), git_sha="a" * 40, run_id="run-001"
        )

    def test_writing_produces_schema_valid_json(self, tmp_path):
        ledger_path = tmp_path / "choices.json"
        entry = choices_ledger.Entry(**_entry_kwargs(session_log_ref="my-change#D1")).to_dict()
        doc = choices_ledger.write_ledger(
            ledger_path,
            header=self._header(),
            change_id="my-change",
            audited_range={"base_sha": "b" * 40, "head_sha": "c" * 40},
            entries=[entry],
        )
        assert ledger_path.exists()
        on_disk = json.loads(ledger_path.read_text())
        assert on_disk == doc
        schema = json.loads(SCHEMA_PATH.read_text())
        Draft202012Validator(schema).validate(on_disk)

    def test_rewriting_with_unchanged_entry_does_not_duplicate(self, tmp_path):
        ledger_path = tmp_path / "choices.json"
        entry = choices_ledger.Entry(**_entry_kwargs(session_log_ref="my-change#D1")).to_dict()
        choices_ledger.write_ledger(
            ledger_path,
            header=self._header(),
            change_id="my-change",
            audited_range={"base_sha": "b" * 40, "head_sha": "c" * 40},
            entries=[entry],
        )
        doc2 = choices_ledger.write_ledger(
            ledger_path,
            header=self._header(),
            change_id="my-change",
            audited_range={"base_sha": "b" * 40, "head_sha": "c" * 40},
            entries=[entry],
        )
        assert len(doc2["entries"]) == 1

    def test_rewriting_with_new_stable_id_appends(self, tmp_path):
        ledger_path = tmp_path / "choices.json"
        entry1 = choices_ledger.Entry(**_entry_kwargs(session_log_ref="my-change#D1")).to_dict()
        entry2 = choices_ledger.Entry(
            **_entry_kwargs(choice="A different decision entirely", session_log_ref="my-change#D2")
        ).to_dict()
        choices_ledger.write_ledger(
            ledger_path,
            header=self._header(),
            change_id="my-change",
            audited_range={"base_sha": "b" * 40, "head_sha": "c" * 40},
            entries=[entry1],
        )
        doc2 = choices_ledger.write_ledger(
            ledger_path,
            header=self._header(),
            change_id="my-change",
            audited_range={"base_sha": "b" * 40, "head_sha": "c" * 40},
            entries=[entry2],
        )
        assert len(doc2["entries"]) == 2
        assert entry1["stable_id"] != entry2["stable_id"]
