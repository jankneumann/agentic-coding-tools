"""Deterministic supervisor-record derivation, carry-forward, and mirroring."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "supervise" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "supervisor-record"
SCHEMAS = REPO_ROOT / "openspec" / "schemas"
if str(SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(SCRIPTS))

from cycle_state import (  # noqa: E402
    MIRROR_PATH,
    audit_writes,
    build_supervisor_record,
    compute_fingerprint,
    main,
    select_prior,
    write_mirror,
)

NOW = "2026-08-31T23:30:00Z"


def _install_schemas(repo: Path) -> None:
    schema_target = repo / "openspec" / "schemas"
    schema_target.mkdir(parents=True)
    for name in (
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
    ):
        shutil.copy2(SCHEMAS / name, schema_target / name)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(FIXTURES / "tree", target)
    _install_schemas(target)
    return target


def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestActiveChangeDerivation:
    def test_v4_v5_terminal_malformed_roadmap_and_registry_inputs(
        self, tree: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        record = build_supervisor_record(tree, now=NOW)

        assert [change["change_id"] for change in record["active_changes"]] == [
            "alpha-v4",
            "ambiguous-registry",
            "beta-v5",
            "escalated",
        ]
        by_id = {change["change_id"]: change for change in record["active_changes"]}
        assert by_id["alpha-v4"] == {
            "change_id": "alpha-v4",
            "current_phase": "PLAN_REVIEW",
            "phase_since": "2026-08-31T20:00:00Z",
            "branch": "openspec/alpha-v4",
            "worktree": ".git-worktrees/alpha-v4",
            "pending_gate": None,
            "roadmap_ref": "roadmap-one:ri-01",
            "last_handoff_id": "handoff-alpha",
        }
        assert by_id["beta-v5"]["pending_gate"] == {
            "gate": "proposal_approval",
            "requested_at": "2026-08-31T21:00:00Z",
        }
        assert by_id["beta-v5"]["roadmap_ref"] is None
        assert by_id["escalated"]["current_phase"] == "ESCALATE"
        assert by_id["ambiguous-registry"]["branch"] is None
        assert by_id["ambiguous-registry"]["worktree"] is None

        degraded = capsys.readouterr().err
        assert "Degraded:" in degraded
        assert "malformed" in degraded
        assert "beta-v5" in degraded
        assert "ambiguous-registry" in degraded

    def test_prior_active_changes_are_always_recomputed(self, tree: Path) -> None:
        prior = _json("full.json")
        prior["active_changes"] = [
            {"change_id": "gone", "current_phase": "PLAN"},
            {"change_id": "alpha-v4", "current_phase": "IMPLEMENT"},
        ]
        record = build_supervisor_record(tree, prior, now=NOW)
        by_id = {change["change_id"]: change for change in record["active_changes"]}
        assert "gone" not in by_id
        assert by_id["alpha-v4"]["current_phase"] == "PLAN_REVIEW"


class TestPriorCarryForward:
    def test_handoff_envelope_is_normalized_and_expired_decisions_are_dropped(
        self, tree: Path
    ) -> None:
        durable = _json("full.json")
        durable["standing_decisions"].append(
            {
                "id": "expired",
                "decided_at": "2026-01-01T00:00:00Z",
                "scope": "global",
                "decision": "old",
                "expires_at": "2026-08-31T23:29:59Z",
            }
        )
        prior = {"data": {"handoffs": [{"supervisor_record": durable}]}}

        record = build_supervisor_record(tree, prior, now=NOW)

        assert record["pending_gates"] == durable["pending_gates"]
        assert [d["id"] for d in record["standing_decisions"]] == [
            "decision-supervisor-record-envelope"
        ]
        assert record["back_edge"] == durable["back_edge"]
        _validator("supervisor-record.schema.json").validate(record)

    @pytest.mark.parametrize("prior_name", ["full.json", "mirror.json"])
    def test_direct_full_record_or_mirror_is_accepted(
        self, tree: Path, prior_name: str
    ) -> None:
        prior = _json(prior_name)
        record = build_supervisor_record(tree, prior, now=NOW)
        assert record["pending_gates"] == prior["pending_gates"]
        assert record["standing_decisions"] == prior["standing_decisions"]
        assert record["back_edge"] == prior["back_edge"]

    def test_deterministic_function_and_cli_output(
        self, tree: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        prior_path = tmp_path / "prior.json"
        prior_path.write_text(json.dumps(_json("mirror.json")), encoding="utf-8")
        assert build_supervisor_record(tree, _json("mirror.json"), now=NOW) == (
            build_supervisor_record(tree, _json("mirror.json"), now=NOW)
        )

        argv = [
            "--repo-root",
            str(tree),
            "supervisor-record",
            "--prior",
            str(prior_path),
            "--now",
            NOW,
        ]
        assert main(argv) == 0
        first = capsys.readouterr().out
        assert main(argv) == 0
        second = capsys.readouterr().out
        assert second == first
        _validator("supervisor-record.schema.json").validate(json.loads(first))


class TestMirror:
    def test_writes_only_sanitized_non_derivable_sections(self, tree: Path) -> None:
        record = _json("full.json")
        record["pending_gates"][0]["unknown"] = "drop me"
        record["standing_decisions"][0]["rationale"] = "safe\u0000text"
        record["back_edge"]["digested_stubs"][0]["unknown"] = "drop me"

        mirror = write_mirror(tree, record, now=NOW)

        stored = json.loads((tree / MIRROR_PATH).read_text(encoding="utf-8"))
        assert stored == mirror
        assert set(stored) == {
            "schema_version",
            "written_at",
            "pending_gates",
            "standing_decisions",
            "back_edge",
        }
        assert "active_changes" not in stored
        assert "unknown" not in stored["pending_gates"][0]
        assert stored["standing_decisions"][0]["rationale"] == "safetext"
        _validator("supervisor-record-mirror.schema.json").validate(stored)
        assert audit_writes([MIRROR_PATH]) == []

    def test_unchanged_write_is_a_noop_preserving_written_at(self, tree: Path) -> None:
        record = _json("full.json")
        first = write_mirror(tree, record, now="2026-08-31T23:30:00Z")
        first_bytes = (tree / MIRROR_PATH).read_bytes()
        second = write_mirror(tree, record, now="2026-09-01T00:30:00Z")
        assert second["written_at"] == first["written_at"]
        assert (tree / MIRROR_PATH).read_bytes() == first_bytes

    def test_mirror_is_excluded_from_the_cycle_fingerprint(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "T")
        (repo / "README.md").write_text("x\n", encoding="utf-8")
        _install_schemas(repo)
        write_mirror(repo, _json("full.json"), now=NOW)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "initial")
        before = compute_fingerprint(repo)
        changed = _json("full.json")
        changed["back_edge"]["last_fingerprint"] = "different"
        write_mirror(repo, changed, now="2026-09-01T00:00:00Z")
        assert compute_fingerprint(repo) == before


class TestPriorSelectionAndCommands:
    def test_newest_normalized_record_wins_and_missing_handoff_uses_mirror(self) -> None:
        handoff = _json("handoff-with-record.json")
        mirror = _json("mirror.json")
        mirror["written_at"] = "2026-09-01T00:00:00Z"
        assert select_prior(handoff, mirror) == mirror
        assert select_prior(None, mirror) == mirror
        handoff["supervisor_record"]["written_at"] = "2026-09-01T01:00:00Z"
        assert select_prior(handoff, mirror) == handoff["supervisor_record"]

    def test_mirror_and_rehydrate_subcommands(
        self, tree: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        record_path = tmp_path / "record.json"
        record_path.write_text(json.dumps(_json("full.json")), encoding="utf-8")
        assert main(
            [
                "--repo-root",
                str(tree),
                "mirror",
                "--record",
                str(record_path),
                "--now",
                NOW,
            ]
        ) == 0
        mirror = json.loads(capsys.readouterr().out)
        _validator("supervisor-record-mirror.schema.json").validate(mirror)

        handoff_path = tmp_path / "handoff.json"
        handoff_path.write_text(json.dumps(_json("handoff-with-record.json")), encoding="utf-8")
        assert main(
            [
                "--repo-root",
                str(tree),
                "rehydrate",
                "--handoff",
                str(handoff_path),
                "--now",
                NOW,
            ]
        ) == 0
        _validator("supervisor-record.schema.json").validate(
            json.loads(capsys.readouterr().out)
        )


class TestRecordValidationAndWriteSafety:
    def test_control_only_required_decision_field_is_dropped(self, tree: Path) -> None:
        prior = _json("mirror.json")
        prior["standing_decisions"] = [
            {
                "id": "\u0000",
                "decided_at": "2026-08-31T22:00:00Z",
                "scope": "global",
                "decision": "continue",
            }
        ]

        record = build_supervisor_record(tree, prior, now=NOW)

        assert record["standing_decisions"] == []
        _validator("supervisor-record.schema.json").validate(record)

    def test_future_record_version_is_rejected_without_overwriting_mirror(
        self, tree: Path
    ) -> None:
        write_mirror(tree, _json("full.json"), now=NOW)
        path = tree / MIRROR_PATH
        before = path.read_bytes()
        future = _json("full.json")
        future["schema_version"] = 2
        future["back_edge"]["last_fingerprint"] = "future"

        with pytest.raises(ValueError, match="unsupported supervisor record schema_version"):
            write_mirror(tree, future, now="2026-09-01T00:00:00Z")

        assert path.read_bytes() == before

    def test_mirror_write_rejects_symlink_destination(
        self, tree: Path, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside.json"
        outside.write_bytes(b"sentinel")
        path = tree / MIRROR_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(outside)

        with pytest.raises(ValueError, match="symlink"):
            write_mirror(tree, _json("full.json"), now=NOW)

        assert outside.read_bytes() == b"sentinel"


class TestRehydrateDegradation:
    def test_missing_handoff_and_mirror_reports_degraded(
        self, tree: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(
            [
                "--repo-root",
                str(tree),
                "rehydrate",
                "--handoff",
                str(tmp_path / "missing-handoff.json"),
                "--mirror",
                str(tmp_path / "missing-mirror.json"),
                "--now",
                NOW,
            ]
        ) == 0

        assert "Degraded: handoff" in capsys.readouterr().err

    def test_newer_mirror_reports_degraded(
        self, tree: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        handoff_path = tmp_path / "handoff.json"
        handoff_path.write_text(
            json.dumps(_json("handoff-with-record.json")), encoding="utf-8"
        )
        mirror = _json("mirror.json")
        mirror["written_at"] = "2026-09-01T00:00:00Z"
        mirror_path = tmp_path / "mirror.json"
        mirror_path.write_text(json.dumps(mirror), encoding="utf-8")

        assert main(
            [
                "--repo-root",
                str(tree),
                "rehydrate",
                "--handoff",
                str(handoff_path),
                "--mirror",
                str(mirror_path),
                "--now",
                NOW,
            ]
        ) == 0
        captured = capsys.readouterr()

        assert json.loads(captured.out)["pending_gates"] == mirror["pending_gates"]
        assert "Degraded: handoff" in captured.err
