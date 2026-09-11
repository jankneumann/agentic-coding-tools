"""Tests for the read-only needs-user reader
(skills/audit-choices/scripts/needs_user.py). Design F3.

Spec: skill-workflow.9, skill-workflow.10, skill-workflow.11 (reader half).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "skills" / "audit-choices" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import choices_ledger  # noqa: E402
import needs_user  # noqa: E402


def _entry(choice: str, verdict: str, confidence: str) -> dict:
    return {
        "choice": choice,
        "scenario": f"WHEN {choice} THEN it happens.",
        "gap": f"The design left {choice} unspecified.",
        "reach": "Future callers inherit this.",
        "verdict": verdict,
        "verdict_rationale": "Because the evidence says so.",
        "confidence": confidence,
        "provenance": {"commits": ["a" * 40], "files": ["skills/example/client.py"]},
        "self_reported": False,
    }


def _write_ledger(change_dir: Path, entries: list[dict]) -> Path:
    change_dir.mkdir(parents=True, exist_ok=True)
    header = choices_ledger.make_header(
        now=datetime(2026, 9, 11, tzinfo=timezone.utc), git_sha="b" * 40, run_id="run-001"
    )
    doc = choices_ledger.build_document(
        header=header,
        change_id="my-change",
        audited_range={"base_sha": "a" * 40, "head_sha": "b" * 40},
        entries=[choices_ledger.Entry.from_dict(e).to_dict() if "stable_id" not in e else e for e in entries],
    )
    path = change_dir / "choices.json"
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


class TestAbsentLedger:
    def test_text_mode_is_silent(self, tmp_path, capsys):
        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "text"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert out.out == ""
        assert out.err == ""

    def test_json_mode_prints_empty_array(self, tmp_path, capsys):
        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "json"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(out.out) == []


class TestLedgerWithNoNeedsUser:
    def test_text_mode_is_silent(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        _write_ledger(change_dir, [_entry("Chose sound thing", "sound", "high")])

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "text"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert out.out == ""

    def test_json_mode_prints_empty_array(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        _write_ledger(change_dir, [_entry("Chose sound thing", "sound", "high")])

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "json"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(out.out) == []


class TestMixedLedger:
    def test_text_mode_lists_only_needs_user_least_confident_first(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        _write_ledger(
            change_dir,
            [
                _entry("Sound decision", "sound", "high"),
                _entry("High-confidence needs-user decision", "needs-user", "high"),
                _entry("Low-confidence needs-user decision", "needs-user", "low"),
                _entry("Unsound decision", "unsound", "medium"),
            ],
        )

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "text"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        lines = out.out.splitlines()
        assert len(lines) == 2
        assert "low" in lines[0]
        assert "Low-confidence needs-user decision" in lines[0]
        assert "high" in lines[1]
        assert "High-confidence needs-user decision" in lines[1]
        # stable_id[:12], confidence, headline — one line per entry
        for line in lines:
            parts = line.split(None, 2)
            assert len(parts) == 3
            assert len(parts[0]) == 12

    def test_json_mode_lists_only_needs_user_least_confident_first(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        _write_ledger(
            change_dir,
            [
                _entry("Sound decision", "sound", "high"),
                _entry("High-confidence needs-user decision", "needs-user", "high"),
                _entry("Low-confidence needs-user decision", "needs-user", "low"),
            ],
        )

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "json"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        payload = json.loads(out.out)
        assert [e["choice"] for e in payload] == [
            "Low-confidence needs-user decision",
            "High-confidence needs-user decision",
        ]
        assert all(e["verdict"] == "needs-user" for e in payload)


class TestMalformedButReadableLedger:
    """Finding 3 (impl-round-1): `needs_user.py` caught `JSONDecodeError`/
    `OSError`, but a *readable* ledger with malformed content still raised —
    one shape via a plain `TypeError` iterating `None`, the other via
    `choices_ledger.rank_entries`'s dict lookup on an unhashable type. F3
    requires the reader to never raise and always exit 0."""

    def test_null_entries_does_not_raise(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / "choices.json").write_text(json.dumps({"entries": None}))

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "text"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert out.out == ""

    def test_null_entries_json_mode_prints_empty_array(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / "choices.json").write_text(json.dumps({"entries": None}))

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "json"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(out.out) == []

    def test_list_valued_confidence_does_not_raise(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        entry = _entry("Chose something", "needs-user", "low")
        entry["confidence"] = ["low", "medium"]  # malformed: list, not str
        (change_dir / "choices.json").write_text(
            json.dumps({"entries": [entry]})
        )

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "text"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert out.out == ""

    def test_list_valued_confidence_warns_once(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        entry = _entry("Chose something", "needs-user", "low")
        entry["confidence"] = ["low", "medium"]
        (change_dir / "choices.json").write_text(
            json.dumps({"entries": [entry]})
        )

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "json"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(out.out) == []
        assert out.err.strip() != ""
        assert len(out.err.strip().splitlines()) == 1


class TestUnreadableLedger:
    def test_text_mode_warns_once_and_exits_zero(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / "choices.json").write_text("{not valid json")

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "text"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert out.out == ""
        assert out.err.strip() != ""
        assert len(out.err.strip().splitlines()) == 1

    def test_json_mode_prints_empty_array_and_warns(self, tmp_path, capsys):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / "choices.json").write_text("{not valid json")

        exit_code = needs_user.main(
            ["--change-id", "my-change", "--repo-root", str(tmp_path), "--format", "json"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(out.out) == []
        assert out.err.strip() != ""


class TestOpensNoFileForWriting:
    def test_ledger_file_is_untouched(self, tmp_path):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        ledger_path = _write_ledger(change_dir, [_entry("Chose sound thing", "sound", "high")])
        before = ledger_path.stat().st_mtime_ns
        before_contents = ledger_path.read_bytes()

        needs_user.main(["--change-id", "my-change", "--repo-root", str(tmp_path)])

        assert ledger_path.stat().st_mtime_ns == before
        assert ledger_path.read_bytes() == before_contents

    def test_no_new_file_created_in_repo_root(self, tmp_path):
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        _write_ledger(change_dir, [_entry("Chose sound thing", "needs-user", "low")])
        before = {p for p in tmp_path.rglob("*") if p.is_file()}

        needs_user.main(["--change-id", "my-change", "--repo-root", str(tmp_path)])

        after = {p for p in tmp_path.rglob("*") if p.is_file()}
        assert after == before


@pytest.mark.parametrize("argv_format", [None, "text"])
def test_cli_entrypoint_exit_code(tmp_path, argv_format, capsys, monkeypatch):
    """`needs_user.py` is invocable as a script and always exits 0."""
    argv = ["needs_user.py", "--change-id", "my-change", "--repo-root", str(tmp_path)]
    if argv_format:
        argv += ["--format", argv_format]
    monkeypatch.setattr(sys, "argv", argv)
    exit_code = needs_user._cli()
    assert exit_code == 0
