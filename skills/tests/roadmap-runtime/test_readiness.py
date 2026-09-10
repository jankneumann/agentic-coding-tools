"""Canonical cross-roadmap readiness and ownership tests (ri-16)."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from models import Checkpoint, CheckpointPhase, Effort, FailedItem, ItemStatus, Roadmap, RoadmapItem
from readiness import _get_ready_items
from resolve_readiness import main, readiness_exit_code, render_readiness, resolve_readiness


ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "openspec" / "schemas"
CONTRACT = (
    ROOT
    / "openspec"
    / "changes"
    / "add-cross-roadmap-readiness-resolver"
    / "contracts"
    / "readiness-result.schema.json"
)


def _item(item_id: str, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "item_id": item_id,
        "title": f"Item {item_id}",
        "status": "approved",
        "priority": 1,
        "effort": "M",
        "depends_on": [],
        "acceptance_outcomes": ["done"],
    }
    item.update(overrides)
    return item


def _write_roadmap(
    repo: Path,
    workspace: str,
    items: list[dict[str, object]],
    *,
    roadmap_id: str | None = None,
) -> Path:
    path = repo / "openspec" / "roadmaps" / workspace / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "roadmap_id": roadmap_id or workspace,
                "source_proposal": f"docs/proposals/{workspace}.md",
                "status": "approved",
                "policy": {"default_action": "wait_if_budget_exceeded"},
                "items": items,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _write_checkpoint(
    repo: Path,
    workspace: str,
    *,
    roadmap_id: str | None = None,
    current_item_id: str = "ri-01",
    completed: list[str] | None = None,
    failed: list[str] | None = None,
) -> Path:
    path = repo / "openspec" / "roadmaps" / workspace / "checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "roadmap_id": roadmap_id or workspace,
                "current_item_id": current_item_id,
                "phase": "completed" if completed else "planning",
                "created_at": "2026-01-01T00:00:00+00:00",
                "completed_items": completed or [],
                "failed_items": [
                    {
                        "item_id": item_id,
                        "reason": "failed",
                        "failed_at": "2026-01-01T00:00:00+00:00",
                    }
                    for item_id in (failed or [])
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _install_schemas(repo: Path) -> None:
    target = repo / "openspec" / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("roadmap.schema.json", "checkpoint.schema.json"):
        shutil.copy2(SCHEMAS / name, target / name)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _install_schemas(repo)
    return repo


class TestSharedAdmissionRule:
    def test_preserves_checkpoint_and_external_admission_contract(self) -> None:
        roadmap = Roadmap(
            schema_version=1,
            roadmap_id="alpha",
            source_proposal="p.md",
            items=[
                RoadmapItem("ri-01", "done", ItemStatus.APPROVED, 1, Effort.S),
                RoadmapItem(
                    "ri-02",
                    "ready",
                    ItemStatus.IN_PROGRESS,
                    2,
                    Effort.M,
                    depends_on=["ri-01"],
                    external_depends_on=["beta:ri-09"],
                ),
                RoadmapItem(
                    "ri-03",
                    "superseded",
                    ItemStatus.APPROVED,
                    1,
                    Effort.S,
                    superseded_by=["beta:ri-10"],
                ),
            ],
        )
        checkpoint = Checkpoint(
            schema_version=1,
            roadmap_id="alpha",
            current_item_id="ri-02",
            phase=CheckpointPhase.IMPLEMENTING,
            created_at="2026-01-01T00:00:00+00:00",
            completed_items=["ri-01"],
            failed_items=[],
        )

        assert _get_ready_items(roadmap, checkpoint) == []
        ready = _get_ready_items(roadmap, checkpoint, {"beta:ri-09"})
        assert [item.item_id for item in ready] == ["ri-02"]

        checkpoint.failed_items = [
            FailedItem("ri-02", "failed", "2026-01-01T00:00:00+00:00")
        ]
        assert _get_ready_items(roadmap, checkpoint, {"beta:ri-09"}) == []

    def test_definition_and_import_ownership_is_exact(self) -> None:
        definitions: list[Path] = []
        for path in (ROOT / "skills").glob("**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_get_ready_items"
                for node in ast.walk(tree)
            ):
                definitions.append(path.relative_to(ROOT))

        assert definitions == [Path("skills/roadmap-runtime/scripts/readiness.py")]
        for relative in (
            "skills/autopilot-roadmap/scripts/orchestrator.py",
            "skills/roadmap-runtime/scripts/resolve_readiness.py",
        ):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            assert any(
                isinstance(node, ast.ImportFrom)
                and node.module == "readiness"
                and any(alias.name == "_get_ready_items" for alias in node.names)
                for node in ast.walk(tree)
            ), relative


class TestRepositoryReadiness:
    def test_missing_checkpoints_use_definition_state_and_rank_globally(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "zeta", [_item("ri-02", priority=2)])
        _write_roadmap(repo, "alpha", [_item("ri-09", priority=1)])

        result = resolve_readiness(repo)

        assert [(row["roadmap_id"], row["item_id"]) for row in result["ready"]] == [
            ("alpha", "ri-09"),
            ("zeta", "ri-02"),
        ]
        assert result["stale"] is False
        assert [d["code"] for d in result["diagnostics"]] == [
            "checkpoint_absent",
            "checkpoint_absent",
        ]
        Draft202012Validator(json.loads(CONTRACT.read_text())).validate(result)

    def test_checkpoint_completion_unblocks_external_dependency_despite_status_lag(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "beta", [_item("ri-01", status="approved")])
        _write_checkpoint(repo, "beta", completed=["ri-01"])
        _write_roadmap(
            repo,
            "alpha",
            [_item("ri-04", external_depends_on=["beta:ri-01"])],
        )

        result = resolve_readiness(repo)

        assert [(row["roadmap_id"], row["item_id"]) for row in result["ready"]] == [
            ("alpha", "ri-04")
        ]
        assert result["stale"] is True
        assert any(
            d["roadmap_id"] == "beta"
            and d["code"] == "roadmap_checkpoint_divergence"
            for d in result["diagnostics"]
        )
        assert readiness_exit_code(result) == 0

    def test_matching_checkpoint_failed_item_never_counts_as_complete(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "beta", [_item("ri-01", status="in_progress")])
        _write_checkpoint(repo, "beta", failed=["ri-01"])
        _write_roadmap(
            repo,
            "alpha",
            [_item("ri-04", external_depends_on=["beta:ri-01"])],
        )

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert readiness_exit_code(result) == 0

    def test_hard_invalid_checkpoint_withholds_workspace_and_completion(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "beta", [_item("ri-01")])
        _write_checkpoint(repo, "beta", roadmap_id="wrong", completed=["ri-01"])
        _write_roadmap(
            repo,
            "alpha",
            [_item("ri-04", external_depends_on=["beta:ri-01"])],
        )

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert any(d["code"] == "checkpoint_roadmap_mismatch" for d in result["diagnostics"])
        assert readiness_exit_code(result) == 2

    def test_unknown_current_or_terminal_item_is_hard_invalid(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "alpha", [_item("ri-01")])
        _write_checkpoint(
            repo,
            "alpha",
            current_item_id="ri-99",
            completed=["ri-98"],
        )

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert any(d["code"] == "checkpoint_unknown_item" for d in result["diagnostics"])
        assert readiness_exit_code(result) == 2

    def test_terminal_conflict_is_hard_invalid(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "alpha", [_item("ri-01")])
        _write_checkpoint(repo, "alpha", completed=["ri-01"], failed=["ri-01"])

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert any(d["code"] == "checkpoint_terminal_conflict" for d in result["diagnostics"])
        assert readiness_exit_code(result) == 2

    def test_malformed_checkpoint_is_hard_invalid(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "alpha", [_item("ri-01")])
        checkpoint = repo / "openspec" / "roadmaps" / "alpha" / "checkpoint.json"
        checkpoint.write_text("{not json", encoding="utf-8")

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert any(d["code"] == "checkpoint_invalid" for d in result["diagnostics"])
        assert readiness_exit_code(result) == 2

    def test_malformed_and_duplicate_roadmaps_fail_closed(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        malformed = repo / "openspec" / "roadmaps" / "broken" / "roadmap.yaml"
        malformed.parent.mkdir(parents=True)
        malformed.write_text("items: [", encoding="utf-8")
        _write_roadmap(repo, "one", [_item("ri-01")], roadmap_id="same")
        _write_roadmap(repo, "two", [_item("ri-02")], roadmap_id="same")

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert {d["code"] for d in result["diagnostics"]} >= {
            "roadmap_invalid",
            "duplicate_roadmap_id",
        }
        assert readiness_exit_code(result) == 2

    def test_duplicate_item_ids_make_a_roadmap_invalid(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(
            repo,
            "alpha",
            [_item("ri-01", title="first"), _item("ri-01", title="second")],
        )

        result = resolve_readiness(repo)

        assert result["ready"] == []
        assert any(
            diagnostic["code"] == "roadmap_invalid"
            and "duplicate item ids" in diagnostic["detail"]
            for diagnostic in result["diagnostics"]
        )
        assert readiness_exit_code(result) == 2

    def test_cli_emits_json_and_returns_nonzero_for_invalid_input(
        self, tmp_path: Path, capsys
    ) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "alpha", [_item("ri-01")])
        checkpoint = repo / "openspec" / "roadmaps" / "alpha" / "checkpoint.json"
        checkpoint.write_text("{not json", encoding="utf-8")

        assert main(["--repo-root", str(repo)]) == 2
        output = capsys.readouterr().out
        assert output.endswith("\n")
        assert json.loads(output)["diagnostics"][0]["code"] == "checkpoint_invalid"

    def test_output_and_fingerprint_are_stable_and_ignore_advisory_files(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        _write_roadmap(repo, "alpha", [_item("ri-01")])

        first = render_readiness(repo)
        assert render_readiness(repo) == first
        learning = repo / "openspec" / "roadmaps" / "alpha" / "learnings" / "ri-01.md"
        learning.parent.mkdir()
        learning.write_text("advisory\n", encoding="utf-8")
        assert render_readiness(repo) == first

        _write_checkpoint(repo, "alpha", completed=["ri-01"])
        second = render_readiness(repo)
        assert second != first
        assert json.loads(second)["source_fingerprint"] != json.loads(first)["source_fingerprint"]

    def test_yaml_key_order_and_dependency_order_do_not_change_fingerprint(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        path = _write_roadmap(
            repo,
            "alpha",
            [
                _item("ri-01", status="completed"),
                _item("ri-02", depends_on=["ri-03", "ri-01"]),
                _item("ri-03", status="completed"),
            ],
        )
        before = resolve_readiness(repo)["source_fingerprint"]
        data = yaml.safe_load(path.read_text())
        data["items"][1]["depends_on"] = ["ri-01", "ri-03"]
        path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
        assert resolve_readiness(repo)["source_fingerprint"] == before
