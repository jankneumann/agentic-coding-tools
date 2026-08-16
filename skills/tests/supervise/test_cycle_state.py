"""Deterministic state for the supervise cycle (supervisor roadmap ri-02).

These pin the two acceptance outcomes that a *scheduled* loop makes load-bearing
and a hand-invoked one never did:

* **Idempotency** — running the cycle twice over an unchanged tree must not
  duplicate candidate stubs, proposals, or roadmap items. Covered from both ends:
  the fingerprint detects "nothing changed", and stub keys suppress re-proposals
  even when something else did change.
* **The write boundary** — the supervisor archetype is ``write_capable: false``,
  so a supervise run writing source code is a contract violation, not a style
  question. ``audit_writes`` is the checkable form of that rule.

Plus the host-assisted invariant: no LLM SDK may appear in this skill's scripts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_SCRIPTS = Path(__file__).resolve().parents[2] / "supervise" / "scripts"
if str(_SCRIPTS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(_SCRIPTS))

import cycle_state  # noqa: E402
from cycle_state import (  # noqa: E402
    LEDGER_PATH,
    audit_writes,
    classify_write,
    compute_fingerprint,
    dedupe_stubs,
    is_unchanged,
    load_ledger,
    ready_across_roadmaps,
    record_cycle,
    stub_key,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _roadmap(repo: Path, roadmap_id: str, items: list[dict]) -> None:
    d = repo / "openspec" / "roadmaps" / roadmap_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "roadmap.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "roadmap_id": roadmap_id,
                "source_proposal": f"docs/proposals/{roadmap_id}.md",
                "status": "planning",
                "items": items,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _item(item_id: str, **kw) -> dict:
    d = {
        "item_id": item_id,
        "title": "Item",
        "status": "approved",
        "priority": 1,
        "effort": "M",
        "depends_on": kw.pop("depends_on", []),
        "acceptance_outcomes": ["done"],
    }
    d.update(kw)
    return d


def _stub(change_id: str | None = None, *, source: str = "report.md", findings=("F1",)) -> dict:
    stub: dict = {
        "schema_version": 1,
        "title": "T",
        "description": "D",
        "rationale": "R",
        "provenance": {"source_artifact": source, "finding_ids": list(findings)},
        "effort": "M",
        "priority": 1,
    }
    if change_id:
        stub["suggested_change_id"] = change_id
    return stub


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", str(r)], check=True, capture_output=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(r, "config", k, v)
    _roadmap(r, "alpha", [_item("ri-01")])
    (r / "README.md").write_text("x\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "init")
    return r


# --------------------------------------------------------------------------- #
# Idempotency: fingerprint
# --------------------------------------------------------------------------- #
class TestFingerprint:
    def test_stable_across_repeat_runs_on_unchanged_tree(self, repo: Path) -> None:
        assert compute_fingerprint(repo) == compute_fingerprint(repo)

    def test_changes_when_an_item_status_changes(self, repo: Path) -> None:
        before = compute_fingerprint(repo)
        _roadmap(repo, "alpha", [_item("ri-01", status="completed")])
        assert compute_fingerprint(repo) != before

    def test_changes_when_a_change_directory_appears(self, repo: Path) -> None:
        before = compute_fingerprint(repo)
        (repo / "openspec" / "changes" / "add-foo").mkdir(parents=True)
        assert compute_fingerprint(repo) != before

    def test_unchanged_only_after_the_cycle_is_recorded(self, repo: Path) -> None:
        assert is_unchanged(repo) is False
        record_cycle(repo, compute_fingerprint(repo), [])
        assert is_unchanged(repo) is True

    def test_a_recorded_cycle_stops_being_unchanged_once_the_tree_moves(
        self, repo: Path
    ) -> None:
        record_cycle(repo, compute_fingerprint(repo), [])
        _roadmap(repo, "alpha", [_item("ri-01"), _item("ri-02")])
        assert is_unchanged(repo) is False

    def test_committing_the_ledger_does_not_change_the_fingerprint(
        self, repo: Path
    ) -> None:
        """Regression (review finding): the fingerprint hashed the HEAD commit
        sha while the ledger is a tracked file, so record -> commit -> next cycle
        always saw a 'changed' tree and the unchanged-tree early exit could never
        fire after any recorded cycle. The tree component now excludes
        openspec/supervise/, making a ledger-only commit invisible."""
        record_cycle(repo, compute_fingerprint(repo), ["change:a"])
        before = compute_fingerprint(repo)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "record supervise cycle")
        assert compute_fingerprint(repo) == before
        assert is_unchanged(repo) is True

    def test_a_real_commit_still_changes_the_fingerprint(self, repo: Path) -> None:
        before = compute_fingerprint(repo)
        (repo / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "real change")
        assert compute_fingerprint(repo) != before


# --------------------------------------------------------------------------- #
# Idempotency: stub keys and dedupe
# --------------------------------------------------------------------------- #
class TestStubIdentity:
    def test_same_suggested_change_id_is_the_same_work(self) -> None:
        a = _stub("add-foo", source="a.md", findings=("F1",))
        b = _stub("add-foo", source="b.md", findings=("F9",))
        assert stub_key(a) == stub_key(b)

    def test_provenance_key_is_order_insensitive(self) -> None:
        a = _stub(source="r.md", findings=("F1", "F2"))
        b = _stub(source="r.md", findings=("F2", "F1"))
        assert stub_key(a) == stub_key(b)

    def test_distinct_provenance_yields_distinct_keys(self) -> None:
        assert stub_key(_stub(source="a.md")) != stub_key(_stub(source="b.md"))


class TestDedupe:
    def test_fresh_stub_survives(self) -> None:
        result = dedupe_stubs([_stub("add-foo")])
        assert len(result.fresh) == 1
        assert result.suppressed == []

    def test_already_surfaced_is_suppressed(self) -> None:
        stub = _stub("add-foo")
        result = dedupe_stubs([stub], seen_keys=[stub_key(stub)])
        assert result.fresh == []
        assert result.suppressed[0][1] == "already-surfaced"

    def test_existing_change_directory_suppresses(self) -> None:
        result = dedupe_stubs([_stub("add-foo")], existing_change_ids=["add-foo"])
        assert result.suppressed[0][1] == "change-exists"

    def test_roadmap_claim_suppresses(self) -> None:
        result = dedupe_stubs([_stub("add-foo")], claimed_ids=["add-foo"])
        assert result.suppressed[0][1] == "roadmap-claimed"

    def test_two_generators_proposing_the_same_work_collapse_to_one(self) -> None:
        result = dedupe_stubs([_stub("add-foo"), _stub("add-foo")])
        assert len(result.fresh) == 1
        assert result.suppressed[0][1] == "duplicate-in-batch"

    def test_a_second_cycle_over_the_same_findings_proposes_nothing(
        self, repo: Path
    ) -> None:
        """The end-to-end idempotency claim, in the shape a scheduled loop hits it."""
        stubs = [_stub("add-foo"), _stub("add-bar")]
        first = dedupe_stubs(stubs, seen_keys=load_ledger(repo).get("seen_keys", []))
        assert len(first.fresh) == 2
        record_cycle(repo, compute_fingerprint(repo), [stub_key(s) for s in first.fresh])

        second = dedupe_stubs(stubs, seen_keys=load_ledger(repo)["seen_keys"])
        assert second.fresh == []
        assert {r for _, r in second.suppressed} == {"already-surfaced"}


# --------------------------------------------------------------------------- #
# Ledger durability
# --------------------------------------------------------------------------- #
class TestLedger:
    def test_absent_ledger_reads_as_empty(self, repo: Path) -> None:
        assert load_ledger(repo)["seen_keys"] == []

    def test_malformed_ledger_degrades_rather_than_raising(self, repo: Path) -> None:
        path = repo / LEDGER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json", encoding="utf-8")
        assert load_ledger(repo)["seen_keys"] == []

    def test_recording_is_byte_stable_for_an_unchanged_tree(self, repo: Path) -> None:
        """A repeat run must not produce a spurious repository diff."""
        fp = compute_fingerprint(repo)
        record_cycle(repo, fp, ["change:add-foo"])
        first = (repo / LEDGER_PATH).read_bytes()
        record_cycle(repo, fp, ["change:add-foo"])
        assert (repo / LEDGER_PATH).read_bytes() == first

    def test_keys_accumulate_across_cycles(self, repo: Path) -> None:
        record_cycle(repo, compute_fingerprint(repo), ["change:a"])
        ledger = record_cycle(repo, compute_fingerprint(repo), ["change:b"])
        assert ledger["seen_keys"] == ["change:a", "change:b"]

    def test_wrong_typed_seen_keys_degrades_to_empty_not_garbage(self, repo: Path) -> None:
        """Regression (review finding): a string seen_keys was iterated
        character-by-character by dedupe and exploded into one-character keys by
        record_cycle's set() merge — degradation to garbage, not to empty."""
        path = repo / LEDGER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"seen_keys": "change:add-foo", "last_fingerprint": 7}),
            encoding="utf-8",
        )
        ledger = load_ledger(repo)
        assert ledger["seen_keys"] == []
        assert ledger["last_fingerprint"] is None
        merged = record_cycle(repo, compute_fingerprint(repo), ["change:b"])
        assert merged["seen_keys"] == ["change:b"]


# --------------------------------------------------------------------------- #
# Ready set honours typed external edges (ri-17)
# --------------------------------------------------------------------------- #
class TestReadySet:
    def test_in_roadmap_dependency_gates_readiness(self, repo: Path) -> None:
        _roadmap(repo, "alpha", [_item("ri-01"), _item("ri-02", depends_on=["ri-01"])])
        ready = ready_across_roadmaps(repo)["alpha"]
        assert [i["item_id"] for i in ready] == ["ri-01"]

    def test_external_prerequisite_suppresses_until_it_completes(self, repo: Path) -> None:
        _roadmap(repo, "beta", [_item("bi-01", status="approved")])
        _roadmap(
            repo,
            "alpha",
            [_item("ri-01", external_depends_on=["beta:bi-01"])],
        )
        assert ready_across_roadmaps(repo)["alpha"] == []

        # The prerequisite completes in its own roadmap; no edit to alpha.
        _roadmap(repo, "beta", [_item("bi-01", status="completed")])
        assert [i["item_id"] for i in ready_across_roadmaps(repo)["alpha"]] == ["ri-01"]

    def test_superseded_by_edge_excludes_even_an_approved_item(self, repo: Path) -> None:
        """Regression (review finding): the first draft hand-rolled the admission
        rule and admitted items carrying a superseded_by edge, which both
        Roadmap.ready_items and the orchestrator exclude — the digest would have
        listed work another roadmap's item already owns as 'Ready now'."""
        _roadmap(repo, "beta", [_item("bi-01")])
        _roadmap(
            repo,
            "alpha",
            [_item("ri-01", status="approved", superseded_by=["beta:bi-01"])],
        )
        assert ready_across_roadmaps(repo)["alpha"] == []

    def test_in_progress_items_appear_in_the_frontier(self, repo: Path) -> None:
        _roadmap(repo, "alpha", [_item("ri-01", status="in_progress")])
        assert [i["item_id"] for i in ready_across_roadmaps(repo)["alpha"]] == ["ri-01"]

    def test_ready_items_are_priority_ordered(self, repo: Path) -> None:
        _roadmap(
            repo,
            "alpha",
            [_item("ri-01", priority=3), _item("ri-02", priority=1)],
        )
        assert [i["item_id"] for i in ready_across_roadmaps(repo)["alpha"]] == [
            "ri-02",
            "ri-01",
        ]


# --------------------------------------------------------------------------- #
# Write boundary — the archetype's write_capable:false, made checkable
# --------------------------------------------------------------------------- #
class TestWriteBoundary:
    @pytest.mark.parametrize(
        "path",
        [
            "openspec/roadmaps/alpha/roadmap.yaml",
            "openspec/changes/add-foo/proposal.md",
            "openspec/priorities/2026-08-16/report.md",
            "openspec/supervise/cycle-ledger.json",
            "docs/proposals/thing.md",
        ],
    )
    def test_coordination_artifacts_are_allowed(self, path: str) -> None:
        assert classify_write(path) == "allowed"

    @pytest.mark.parametrize(
        "path",
        [
            "skills/autopilot/scripts/autopilot.py",
            "agent-coordinator/src/work_queue.py",
            "apps/kanban-viz/src/App.tsx",
            "Makefile",
            "openspec/specs/agent-coordinator/spec.md",
            "openspec/changes/add-foo/specs/cap/spec.md",
        ],
    )
    def test_implementation_and_specs_are_forbidden(self, path: str) -> None:
        assert classify_write(path) == "forbidden"

    @pytest.mark.parametrize(
        "path",
        [
            "../openspec/roadmaps/x.yaml",
            "openspec/roadmaps/../../agent-coordinator/src/x.py",
            "openspec/roadmaps/../../../etc/passwd",
            "/etc/passwd",
            "./openspec/../skills/autopilot/scripts/autopilot.py",
            "..",
            "C:\\repo\\openspec\\roadmaps\\x.yaml",
        ],
    )
    def test_traversal_and_absolute_paths_are_forbidden(self, path: str) -> None:
        """Regression (review finding): lstrip('./') is a character strip, not a
        prefix strip, and no '..' resolution ran — both verified traversal forms
        classified 'allowed', silently defeating the write-boundary audit."""
        assert classify_write(path) == "forbidden"

    def test_normalized_inside_path_is_still_allowed(self) -> None:
        # Normalization must not over-reject: a '..' that stays inside an
        # allowed prefix is fine.
        assert classify_write("openspec/roadmaps/a/../b/roadmap.yaml") == "allowed"

    def test_audit_reports_only_the_violations(self) -> None:
        violations = audit_writes(
            [
                "openspec/roadmaps/alpha/roadmap.yaml",
                "agent-coordinator/src/memory.py",
                "skills/supervise/SKILL.md",
            ]
        )
        assert violations == [
            "agent-coordinator/src/memory.py",
            "skills/supervise/SKILL.md",
        ]

    def test_a_clean_run_audits_empty(self) -> None:
        assert audit_writes(["openspec/supervise/cycle-ledger.json"]) == []


# --------------------------------------------------------------------------- #
# Collection-order independence
# --------------------------------------------------------------------------- #
class TestImportIsolation:
    def test_cycle_state_survives_a_foreign_models_module(self) -> None:
        """Regression (review finding): cycle_state imported the bare name
        'models' via sys.path insertion, so whichever test tree loaded its own
        'models' first poisoned sys.modules and collection of this suite failed
        under the documented all-tests command. cycle_state now loads
        roadmap-runtime models by file path under a unique module name."""
        import types

        foreign = types.ModuleType("models")  # simulates another tree's models
        previous = sys.modules.get("models")
        sys.modules["models"] = foreign
        try:
            import importlib

            importlib.reload(cycle_state)
            # The reload must succeed and still resolve the real runtime symbols.
            assert cycle_state.ItemStatus.APPROVED.value == "approved"
        finally:
            if previous is not None:
                sys.modules["models"] = previous
            else:
                del sys.modules["models"]
            importlib.reload(cycle_state)


# --------------------------------------------------------------------------- #
# Host-assisted invariant (mirrors autopilot-roadmap's source-contribution test)
# --------------------------------------------------------------------------- #
class TestHostAssistedInvariant:
    def test_no_llm_sdk_in_supervise_scripts(self) -> None:
        forbidden = ("anthropic", "openai", "google.generativeai", "llm_client")
        for source in (_SCRIPTS).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            for token in forbidden:
                assert f"import {token}" not in text, f"{source}: imports {token}"
                assert f"from {token}" not in text, f"{source}: imports from {token}"

    def test_scripts_make_no_network_calls(self) -> None:
        forbidden = ("import requests", "import httpx", "urllib.request")
        for source in (_SCRIPTS).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            for token in forbidden:
                assert token not in text, f"{source}: reaches the network via {token}"


# --------------------------------------------------------------------------- #
# CLI surface
# --------------------------------------------------------------------------- #
class TestCli:
    def test_audit_writes_exits_nonzero_on_violation(self, repo: Path) -> None:
        rc = cycle_state.main(
            ["--repo-root", str(repo), "audit-writes", "agent-coordinator/src/x.py"]
        )
        assert rc == 1

    def test_audit_writes_exits_zero_when_clean(self, repo: Path) -> None:
        rc = cycle_state.main(
            ["--repo-root", str(repo), "audit-writes", "openspec/roadmaps/a/roadmap.yaml"]
        )
        assert rc == 0

    def test_dedupe_reads_a_stub_file(self, repo: Path, tmp_path: Path) -> None:
        stubs = tmp_path / "stubs.json"
        stubs.write_text(json.dumps([_stub("add-foo")]), encoding="utf-8")
        rc = cycle_state.main(
            ["--repo-root", str(repo), "dedupe", "--stubs", str(stubs)]
        )
        assert rc == 0
