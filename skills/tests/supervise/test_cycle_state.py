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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_SCHEMAS = Path(__file__).resolve().parents[3] / "openspec" / "schemas"
_SCRIPTS = Path(__file__).resolve().parents[2] / "supervise" / "scripts"
_SKILL_MD = _SCRIPTS.parent / "SKILL.md"
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
    audit_since_snapshot,
    ready_across_roadmaps,
    record_cycle,
    repository_snapshot,
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


def _install_schemas(repo: Path) -> None:
    """Copy the schemas write_mirror / load_roadmap / CheckpointManager validate against."""
    schema_target = repo / "openspec" / "schemas"
    schema_target.mkdir(parents=True, exist_ok=True)
    for name in (
        "supervisor-record.schema.json",
        "supervisor-record-mirror.schema.json",
        "roadmap.schema.json",
        "checkpoint.schema.json",
    ):
        shutil.copy2(_SCHEMAS / name, schema_target / name)


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

    def test_unstaged_tracked_change_changes_the_fingerprint(self, repo: Path) -> None:
        before = compute_fingerprint(repo)
        (repo / "README.md").write_text("unstaged\n", encoding="utf-8")
        assert compute_fingerprint(repo) != before

    def test_staged_tracked_change_changes_the_fingerprint(self, repo: Path) -> None:
        before = compute_fingerprint(repo)
        (repo / "README.md").write_text("staged\n", encoding="utf-8")
        _git(repo, "add", "README.md")
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

    def test_audit_since_snapshot_detects_new_source_write(self, repo: Path) -> None:
        before = repository_snapshot(repo)
        (repo / "README.md").write_text("supervisor edit\n", encoding="utf-8")
        assert audit_since_snapshot(repo, before) == ["README.md"]

    def test_audit_since_snapshot_allows_new_coordination_write(self, repo: Path) -> None:
        before = repository_snapshot(repo)
        path = repo / "openspec" / "priorities" / "today" / "report.md"
        path.parent.mkdir(parents=True)
        path.write_text("ranked\n", encoding="utf-8")
        assert audit_since_snapshot(repo, before) == []

    def test_audit_since_snapshot_ignores_preexisting_unchanged_edit(self, repo: Path) -> None:
        (repo / "README.md").write_text("operator edit\n", encoding="utf-8")
        before = repository_snapshot(repo)
        assert audit_since_snapshot(repo, before) == []

    def test_audit_since_snapshot_detects_further_edit_to_dirty_file(self, repo: Path) -> None:
        (repo / "README.md").write_text("operator edit\n", encoding="utf-8")
        before = repository_snapshot(repo)
        (repo / "README.md").write_text("supervisor edit\n", encoding="utf-8")
        assert audit_since_snapshot(repo, before) == ["README.md"]


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


class TestWorkflowContract:
    @staticmethod
    def _section(text: str, start: str, end: str) -> str:
        return text.split(start, 1)[1].split(end, 1)[0]

    def test_cycle_wires_fingerprint_record_and_write_audit(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        assert "snapshot-writes" in text
        assert "audit-since" in text
        assert "--repo-root . fingerprint" in text
        assert "record --keys \"$SUPERVISE_KEYS\"" in text

    def test_dry_run_forbids_artifact_writing_child_skills(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        assert "MUST NOT invoke" in text
        assert "/bug-scrub" in text
        assert "/explore-feature" in text
        assert "/prioritize-proposals" in text

    def test_rehydrate_restores_the_latest_durable_supervisor_record(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        rehydrate = self._section(text, "### 1. Rehydrate", "### 2. Sense")
        normalized = " ".join(rehydrate.split())

        assert "try_handoff_read(limit=1, supervisor_only=true)" in rehydrate
        assert "supervisor-record" in rehydrate
        assert "newer ordinary handoff" in normalized
        assert "Coordinator unreachable" in rehydrate
        assert "newer `written_at`" in rehydrate
        assert "Degraded: handoff" in rehydrate

    def test_digest_renders_supervisor_pending_gates_with_deadlines(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        digest = self._section(text, "### 5. Digest, then stop", "On approval")

        assert "pending_gates" in digest
        assert "deadline" in digest
        assert "Needs a decision" in digest
        assert "active_changes" in digest
        assert "Ready now" in digest

    def test_intake_writes_mirror_before_audit_then_handoff(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        intake = self._section(text, "## Verb: `intake`", "## Verb: `cycle`")

        assert intake.index("supervisor-record") < intake.index("mirror --record")
        assert intake.index("mirror --record") < intake.index("audit-since")
        assert intake.index("audit-since") < intake.index("try_handoff_write(")

    def test_non_dry_run_cycle_writes_mirror_before_audit_then_handoff(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        closing = self._section(text, "### 5. Digest, then stop", "On approval")

        assert "non-`--dry-run`" in closing
        # ri-04: the final-record step now re-selects the prior via `rehydrate
        # --handoff` rather than `supervisor-record --prior` (D7) -- writing
        # from the pre-gate snapshot would overwrite the router's own mirror
        # projection from this cycle's gate-check.
        assert closing.index("rehydrate --handoff") < closing.index("mirror --record")
        assert closing.index("mirror --record") < closing.index("audit-since")
        assert closing.index("audit-since") < closing.index("try_handoff_write(")

    def test_dry_run_writes_neither_supervisor_store(self) -> None:
        text = _SKILL_MD.read_text(encoding="utf-8")
        closing = self._section(text, "### 5. Digest, then stop", "On approval")

        assert "Under `--dry-run`, write neither the mirror nor a supervisor handoff." in closing


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


# --------------------------------------------------------------------------- #
# D1/D7 (ri-04): _GATES tracks shared.trust_posture.Gate; decision_id survives
# the pendingGate allowlist cleaner through a write_mirror round trip.
# --------------------------------------------------------------------------- #
class TestPendingGateDecisionIdRoundTrip:
    def test_roadmap_approval_gate_is_accepted_by_the_gate_set(self) -> None:
        """D1: _GATES must track shared.trust_posture.Gate, not a hand-copied
        literal — otherwise a ninth gate added to the enum silently fails to
        validate here even though every schema now accepts it."""
        assert "roadmap_approval" in cycle_state._GATES

    def test_roadmap_approval_entry_with_decision_id_survives_write_mirror(
        self, repo: Path
    ) -> None:
        _install_schemas(repo)
        record = {
            "schema_version": 1,
            "written_at": "2026-09-01T00:00:00Z",
            "pending_gates": [
                {
                    "gate": "roadmap_approval",
                    "change_id": "demo-change",
                    "requested_at": "2026-09-01T00:00:00Z",
                    "deadline": "2026-09-08T00:00:00Z",
                    "decision_id": "11111111-1111-4111-8111-111111111111",
                }
            ],
            "standing_decisions": [],
            "back_edge": {
                "last_digest_at": None,
                "last_fingerprint": None,
                "digested_stubs": [],
            },
        }

        mirror = cycle_state.write_mirror(repo, record, now="2026-09-01T00:00:00Z")

        entry = mirror["pending_gates"][0]
        assert entry["gate"] == "roadmap_approval"
        assert entry["decision_id"] == "11111111-1111-4111-8111-111111111111"


# --------------------------------------------------------------------------- #
# gate-check / gate-answer / gate-log (D5, D6) -- ri-04 tasks 2.7-2.9
# --------------------------------------------------------------------------- #
def _gated_repo(repo: Path) -> Path:
    """The base `repo` fixture's roadmap has no change_id; roadmap_approval's
    parked-entry projection needs one (D7)."""
    _install_schemas(repo)
    _roadmap(repo, "alpha", [_item("ri-01", change_id="demo-change")])
    return repo


def _write_posture(repo: Path, gate: str, disposition: str, **extra: object) -> None:
    lines = ["---", "schema_version: 1", "gates:", f"  {gate}:", f"    disposition: {disposition}"]
    for key, value in extra.items():
        lines.append(f"    {key}: {value}")
    lines.append("---\n")
    (repo / "TRUST_POSTURE.md").write_text("\n".join(lines), encoding="utf-8")


class TestGateCheckCli:
    def test_auto_posture_exits_proceed_and_prints_the_ref(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)
        _write_posture(repo, "roadmap_approval", "auto")

        rc = cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])

        assert rc == cycle_state.GATE_EXIT_PROCEED
        payload = json.loads(capsys.readouterr().out)
        assert payload["gate"] == "roadmap_approval"
        assert payload["outcome"] == "proceed"
        assert payload["roadmap_approval_ref"] == f"gate-decision:{payload['decision_id']}"

    def test_reused_proceed_still_exits_proceed(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)
        _write_posture(repo, "roadmap_approval", "auto")
        cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])
        capsys.readouterr()

        rc = cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])

        assert rc == cycle_state.GATE_EXIT_PROCEED

    def test_absent_posture_blocks_and_prints_pending_gate_entry(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)

        rc = cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])

        assert rc == cycle_state.GATE_EXIT_PARKED
        payload = json.loads(capsys.readouterr().out)
        assert payload["gate"] == "roadmap_approval"
        assert payload["change_id"] == "demo-change"
        assert payload["deadline"]
        assert payload["source"] == "supervise"

    def test_rejected_prior_record_exits_terminal_block(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)
        cycle_state.main(
            ["--repo-root", str(repo), "gate-answer", "--roadmap", "alpha",
             "--gate", "roadmap_approval", "--decision", "rejected"]
        )
        capsys.readouterr()

        rc = cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])

        assert rc == cycle_state.GATE_EXIT_TERMINAL_BLOCK

    def test_bootstraps_a_missing_checkpoint_instead_of_raising(self, repo: Path) -> None:
        repo = _gated_repo(repo)
        assert not (repo / "openspec" / "roadmaps" / "alpha" / "checkpoint.json").exists()

        rc = cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])

        assert rc in (cycle_state.GATE_EXIT_PARKED, cycle_state.GATE_EXIT_PROCEED, cycle_state.GATE_EXIT_TERMINAL_BLOCK)
        assert (repo / "openspec" / "roadmaps" / "alpha" / "checkpoint.json").exists()

    def test_has_no_dry_run_flag(self) -> None:
        with pytest.raises(SystemExit):
            cycle_state.main(["gate-check", "--roadmap", "alpha", "--dry-run"])


class TestGateAnswerCli:
    def test_roadmap_approval_originates_a_record_with_no_prior_park(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)

        rc = cycle_state.main(
            ["--repo-root", str(repo), "gate-answer", "--roadmap", "alpha",
             "--gate", "roadmap_approval", "--decision", "approved", "--note", "direct invocation"]
        )

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["outcome"] == "proceed"
        assert payload["resolution"] == "console_approved"
        assert payload["roadmap_approval_ref"] == f"gate-decision:{payload['decision_id']}"

    def test_other_gate_without_a_parked_record_is_refused(self, repo: Path) -> None:
        repo = _gated_repo(repo)

        rc = cycle_state.main(
            ["--repo-root", str(repo), "gate-answer", "--roadmap", "alpha",
             "--gate", "pr_creation", "--decision", "approved", "--dispatch-id", "d-1"]
        )

        assert rc == 2


class TestGateLogCli:
    def test_empty_workspace_prints_empty_array(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)

        rc = cycle_state.main(["--repo-root", str(repo), "gate-log", "--roadmap", "alpha"])

        assert rc == 0
        assert json.loads(capsys.readouterr().out) == []

    def test_one_entry_per_evaluate_none_for_reuse(self, repo: Path, capsys) -> None:
        repo = _gated_repo(repo)
        _write_posture(repo, "roadmap_approval", "auto")
        cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])
        cycle_state.main(["--repo-root", str(repo), "gate-check", "--roadmap", "alpha"])
        capsys.readouterr()

        rc = cycle_state.main(["--repo-root", str(repo), "gate-log", "--roadmap", "alpha"])

        assert rc == 0
        log = json.loads(capsys.readouterr().out)
        assert len(log) == 1
        assert log[0]["origin"] == "checkpoint"
