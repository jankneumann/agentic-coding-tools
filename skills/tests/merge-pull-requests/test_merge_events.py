"""The ``context_gate`` merge event (D7) — shape, additivity, and emission.

The advisory→blocking flip for the context drift gate is meant to be decided on
evidence, in the vocabulary ``architecture.config.yaml`` already uses for the
architecture gate (``clean_runs_before_flip: 3``). Counting clean runs requires a
durable per-run record, and this suite pins the record.

Organised by the claim each class makes:

* ``TestContextGateEventShape`` — the record carries the triggering event, the
  tree's outcome, the exit code that answered for that event, the base the
  verdict was taken against, and the inherited/introduced/indeterminate counts
  that make "is introduced drift trending down" answerable.
* ``TestPurelyAdditive`` — no existing reader changes. A ``merge`` row serialises
  to exactly the keys it serialised to before, and ``compute_metrics_summary``
  reads a log containing ``context_gate`` rows without noticing them.
* ``TestGateEmission`` — the gate emits one row per run, only when a destination
  is configured, never into the checkout it is grading, and never at the cost of
  its own verdict.

The suite directory has no ``conftest.py`` (unlike
``merge-pull-requests/scripts/tests``), so the module-level autouse fixture below
does that suite's job: ``merge_events.DEFAULT_LOG_PATH`` is relative and would
otherwise append to the repository's own tracked ``docs/merge-logs/metrics.jsonl``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_MERGE_SCRIPTS = _SKILLS_ROOT / "merge-pull-requests" / "scripts"
if str(_MERGE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_MERGE_SCRIPTS))

import merge_events  # noqa: E402
from merge_events import MergeEvent, emit_event, load_events  # noqa: E402
from merge_metrics import compute_metrics_summary  # noqa: E402

#: The keys a ``merge`` row serialised to before ``context_gate`` existed. Pinned
#: literally rather than derived, because the whole additivity claim is that this
#: set does not move when fields are added to the dataclass.
_MERGE_ROW_KEYS = frozenset({"event_type", "pr_number", "backend", "success", "timestamp"})


@pytest.fixture(autouse=True)
def _redirect_default_merge_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the implicit default log at tmp_path for every test in this module."""
    redirected = tmp_path / "default-merge-log" / "metrics.jsonl"
    monkeypatch.setattr(merge_events, "DEFAULT_LOG_PATH", redirected)
    return redirected


def _gate_event(**overrides: object) -> MergeEvent:
    """A ``context_gate`` event with every field supplied, overridable per test."""
    fields: dict[str, object] = {
        "outcome": "drift",
        "exit_code": 0,
        "gate_event": "pull_request",
        "source_revision": "a" * 40,
        "base_revision": "b" * 40,
        "base_resolved_from": "remote",
        "blocking_inherited": 2,
        "blocking_introduced": 0,
        "blocking_indeterminate": 1,
        "informational_inherited": 0,
        "informational_introduced": 1,
        "informational_indeterminate": 0,
    }
    fields.update(overrides)
    return merge_events.context_gate_event(**fields)  # type: ignore[arg-type]


class TestContextGateEventShape:
    def test_event_type_is_context_gate(self) -> None:
        assert _gate_event().event_type == merge_events.CONTEXT_GATE_EVENT_TYPE
        assert merge_events.CONTEXT_GATE_EVENT_TYPE == "context_gate"

    def test_record_carries_the_verdict_and_its_event(self) -> None:
        row = _gate_event(outcome="drift", exit_code=0, gate_event="pull_request").to_dict()
        # ``outcome`` describes the tree, ``exit_code`` answers for the event, and
        # they legitimately disagree on a pull request carrying inherited drift.
        # A record that kept only one of them could not tell that case apart from
        # a clean tree, which is exactly the run the flip needs to count.
        assert row["gate_outcome"] == "drift"
        assert row["gate_exit_code"] == 0
        assert row["gate_event"] == "pull_request"

    def test_record_carries_the_base_the_verdict_was_taken_against(self) -> None:
        row = _gate_event().to_dict()
        assert row["gate_source_revision"] == "a" * 40
        assert row["gate_base_revision"] == "b" * 40
        assert row["gate_base_resolved_from"] == "remote"

    def test_record_carries_attribution_counts_for_both_groups(self) -> None:
        row = _gate_event().to_dict()
        assert row["gate_blocking_inherited"] == 2
        assert row["gate_blocking_introduced"] == 0
        assert row["gate_blocking_indeterminate"] == 1
        assert row["gate_informational_inherited"] == 0
        assert row["gate_informational_introduced"] == 1
        assert row["gate_informational_indeterminate"] == 0

    def test_zero_counts_are_recorded_rather_than_dropped(self) -> None:
        """``to_dict`` drops ``None``; it must not drop a genuine zero.

        "Three clean runs in a row" is a claim about runs that counted zero
        introduced findings. If a zero serialised as an absent key, a clean run
        would be indistinguishable from a run that never measured, and the flip
        criterion would be counting silence.
        """
        row = _gate_event(
            blocking_inherited=0,
            blocking_introduced=0,
            blocking_indeterminate=0,
            informational_inherited=0,
            informational_introduced=0,
            informational_indeterminate=0,
        ).to_dict()
        for key in (
            "gate_blocking_inherited",
            "gate_blocking_introduced",
            "gate_blocking_indeterminate",
            "gate_informational_inherited",
            "gate_informational_introduced",
            "gate_informational_indeterminate",
        ):
            assert row[key] == 0

    def test_success_mirrors_a_green_exit_code(self) -> None:
        assert _gate_event(exit_code=0).success is True
        assert _gate_event(exit_code=2).success is False
        assert _gate_event(exit_code=1).success is False

    def test_no_event_supplied_is_an_absent_key_not_a_placeholder(self) -> None:
        """The strict no-event rule is a real state; it is recorded as absence."""
        row = _gate_event(gate_event=None).to_dict()
        assert "gate_event" not in row

    def test_a_run_with_no_pull_request_records_the_documented_sentinel(self) -> None:
        event = _gate_event()
        assert event.pr_number == merge_events.NO_PULL_REQUEST
        assert event.backend == merge_events.CONTEXT_GATE_BACKEND

    def test_timestamp_is_iso_8601(self) -> None:
        datetime.fromisoformat(_gate_event().timestamp)

    def test_round_trips_through_jsonl(self, tmp_path: Path) -> None:
        log = tmp_path / "metrics.jsonl"
        emit_event(_gate_event(), log_path=log)
        rows = load_events(log_path=log, event_type="context_gate")
        assert len(rows) == 1
        assert rows[0] == json.loads(_gate_event(**{}).to_json()) | {
            "timestamp": rows[0]["timestamp"]
        }


class TestPurelyAdditive:
    def test_a_merge_row_serialises_to_the_same_keys_as_before(self) -> None:
        row = MergeEvent(
            event_type="merge", pr_number=42, backend="direct", success=True
        ).to_dict()
        assert set(row) == _MERGE_ROW_KEYS

    def test_context_gate_fields_are_absent_from_every_other_event_type(self) -> None:
        row = MergeEvent(
            event_type="revert", pr_number=7, backend="train", success=False
        ).to_dict()
        assert not [key for key in row if key.startswith("gate_")]

    def test_metrics_summary_reads_a_log_of_gate_rows_without_noticing_them(
        self, tmp_path: Path
    ) -> None:
        """``merge_metrics`` switches on known types; an unknown one is inert."""
        log = tmp_path / "metrics.jsonl"
        emit_event(
            MergeEvent(event_type="merge", pr_number=1, backend="direct", success=True),
            log_path=log,
        )
        emit_event(_gate_event(), log_path=log)

        summary = compute_metrics_summary(log_path=log)
        assert summary["total_events"] == 2
        assert summary["merge_count"] == 1
        assert summary["merge_success_rate"] == 1.0
        assert summary["backend_counts"] == {"direct": 1}


# --------------------------------------------------------------------------- #
# Emission from the gate (task 6.2)
# --------------------------------------------------------------------------- #
_GATE_SCRIPTS = _SKILLS_ROOT / "project-context-refresh" / "scripts"
if str(_GATE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GATE_SCRIPTS))

import gate  # noqa: E402
import orchestrator  # noqa: E402
import results as R  # noqa: E402
from _runtime import ChangeKind, Remediation, RepositoryArtifact  # noqa: E402

_FULL_SHA = "c" * 40


def _drift(producer_id: str, path: str) -> Any:
    return R.drift(
        producer_id,
        "1",
        artifacts=(
            RepositoryArtifact(path=path, change=ChangeKind.MODIFIED, sha256="0" * 64),
        ),
        validations=[R.failed_validation(R.vid(producer_id, "render"), "would change")],
        remediation=[Remediation(summary=f"re-run {producer_id}")],
    )


def _checker(*producer_results: Any):
    def _run(repository, **_kwargs):  # noqa: ANN001, ANN003
        outcome, _error = orchestrator.decide_outcome(producer_results, None)
        return orchestrator.RefreshResult(
            operation_id=None,
            outcome=outcome,
            producer_results=tuple(producer_results),
            semantic_index=None,
        )

    return _run


def _impact_runner(argv):  # noqa: ANN001
    return 0, json.dumps({"packages": []})


def _run_gate(repository: Path, *producer_results: Any, **kwargs: Any):
    kwargs.setdefault("revision", _FULL_SHA)
    kwargs.setdefault("changed_files", ())
    kwargs.setdefault("check_runner", _checker(*producer_results))
    kwargs.setdefault("context_impact_runner", _impact_runner)
    return gate.run_gate(repository, **kwargs)


def _dirty_checkout(root: Path) -> Path:
    """A git checkout with one uncommitted edit and one untracked file."""
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    tracked = root / "tracked.md"
    tracked.write_text("committed\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(root), "add", "tracked.md"], check=True, capture_output=True
    )
    tracked.write_text("uncommitted edit\n", encoding="utf-8")
    (root / "scratch.txt").write_text("untracked\n", encoding="utf-8")
    return root


def _digest_tree(root: Path) -> dict[str, str]:
    """Digest every path under *root*, tracked and untracked, excluding ``.git``."""
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts[:1]:
            continue
        rel = str(path.relative_to(root))
        digests[rel] = "<dir>" if path.is_dir() else hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return digests


class TestGateEmission:
    """The gate records one row per run — without paying for it in its verdict."""

    def test_no_destination_means_no_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Implementation Rule 4: new configuration defaults to current behaviour."""
        monkeypatch.delenv(gate.GATE_METRICS_PATH_ENV, raising=False)
        repo = _dirty_checkout(tmp_path / "repo")
        before = _digest_tree(repo)

        result = _run_gate(repo, _drift("documentation.inventory", "docs/a.md"))

        assert result.exit_code == 2
        assert _digest_tree(repo) == before
        assert not list(repo.rglob("metrics.jsonl"))

    def test_a_configured_destination_receives_one_row_per_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(gate.GATE_METRICS_PATH_ENV, raising=False)
        repo = _dirty_checkout(tmp_path / "repo")
        destination = tmp_path / "outside" / "metrics.jsonl"

        result = _run_gate(
            repo,
            _drift("documentation.inventory", "docs/a.md"),
            metrics_path=destination,
        )
        _run_gate(
            repo,
            _drift("documentation.inventory", "docs/a.md"),
            metrics_path=destination,
        )

        rows = load_events(log_path=destination, event_type="context_gate")
        assert len(rows) == 2
        row = rows[0]
        assert row["gate_outcome"] == result.report["outcome"] == "drift"
        assert row["gate_exit_code"] == result.exit_code == 2
        assert row["gate_source_revision"] == result.report["source_revision"]
        assert "gate_event" not in row
        # One blocking finding, and the counters cover the whole vocabulary so a
        # zero is recorded rather than omitted.
        assert (
            row["gate_blocking_inherited"]
            + row["gate_blocking_introduced"]
            + row["gate_blocking_indeterminate"]
        ) == len(result.report["blocking_drift"]) == 1
        assert row["gate_informational_inherited"] == 0
        assert row["gate_informational_introduced"] == 0
        assert row["gate_informational_indeterminate"] == 0

    def test_the_environment_variable_configures_the_destination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CI has no gate flag to pass; the environment is the only seam it has."""
        repo = _dirty_checkout(tmp_path / "repo")
        destination = tmp_path / "outside" / "metrics.jsonl"
        monkeypatch.setenv(gate.GATE_METRICS_PATH_ENV, str(destination))

        _run_gate(
            repo,
            R.fresh(
                "documentation.inventory",
                "1",
                validations=[R.passed("documentation.inventory-check", "clean")],
            ),
            event="merge_group",
        )

        rows = load_events(log_path=destination, event_type="context_gate")
        assert len(rows) == 1
        assert rows[0]["gate_event"] == "merge_group"
        assert rows[0]["gate_outcome"] == "fresh"
        assert rows[0]["success"] is True

    def test_a_destination_inside_the_checkout_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """"Gate leaves the checkout unchanged" outranks recording the run.

        Pointed at the tree it is grading, the gate declines rather than writes:
        the read-only scenario digests the checkout tracked and untracked before
        and after, and a JSONL append is exactly the kind of "small" write that
        would make the gate the reason ``main`` is dirty.
        """
        monkeypatch.delenv(gate.GATE_METRICS_PATH_ENV, raising=False)
        repo = _dirty_checkout(tmp_path / "repo")
        before = _digest_tree(repo)

        result = _run_gate(
            repo,
            _drift("documentation.inventory", "docs/a.md"),
            metrics_path=repo / "docs" / "merge-logs" / "metrics.jsonl",
        )

        assert result.exit_code == 2
        assert _digest_tree(repo) == before
        assert not (repo / "docs").exists()
        assert "refusing to record gate metrics" in capsys.readouterr().err

    def test_an_unwritable_destination_cannot_change_the_verdict(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A missing or unwritable events file is telemetry's problem, not the gate's."""
        monkeypatch.delenv(gate.GATE_METRICS_PATH_ENV, raising=False)
        repo = _dirty_checkout(tmp_path / "repo")
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("in the way\n", encoding="utf-8")

        with_metrics = _run_gate(
            repo,
            _drift("documentation.inventory", "docs/a.md"),
            metrics_path=blocker / "nested" / "metrics.jsonl",
        )
        without_metrics = _run_gate(repo, _drift("documentation.inventory", "docs/a.md"))

        assert with_metrics.exit_code == without_metrics.exit_code == 2
        assert with_metrics.report == without_metrics.report
        # And the write really was attempted and really did fail, so this test
        # cannot pass by quietly not emitting at all.
        assert "NotADirectoryError" in capsys.readouterr().err

    def test_an_emitter_that_raises_cannot_change_the_verdict(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Every failure mode, not just the anticipated ones, stops at the seam."""
        repo = _dirty_checkout(tmp_path / "repo")

        def _boom(_metrics_path):  # noqa: ANN001
            raise RuntimeError("metrics sink exploded")

        monkeypatch.setattr(gate, "_metrics_destination", _boom)
        result = _run_gate(repo, _drift("documentation.inventory", "docs/a.md"))

        assert result.exit_code == 2
        assert result.report["outcome"] == "drift"
        assert "metrics sink exploded" in capsys.readouterr().err

    def test_a_reported_but_non_blocking_run_records_both_numbers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pull-request case the flip exists to measure: drift, exit 0.

        Rendered directly rather than through a synthetic ancestry fixture --
        what is under test here is that the record keeps ``outcome`` and
        ``exit_code`` apart, not how attribution reached its answer.
        """
        monkeypatch.delenv(gate.GATE_METRICS_PATH_ENV, raising=False)
        destination = tmp_path / "outside" / "metrics.jsonl"
        report = {
            "source_revision": _FULL_SHA,
            "tree": {"base_resolved_revision": "d" * 40, "base_resolved_from": "remote"},
            "outcome": "drift",
            "exit_code": 0,
            "blocking_drift": [
                {"producer_id": "documentation.inventory", "attribution": "inherited"},
                {"producer_id": "api.contracts", "attribution": "indeterminate"},
            ],
            "informational_drift": [
                {"producer_id": "openspec.projection", "attribution": "introduced"}
            ],
        }

        written = gate.emit_gate_metrics(
            tmp_path / "repo",
            report,
            event="pull_request",
            metrics_path=destination,
        )

        assert written == destination.resolve()
        (row,) = load_events(log_path=destination)
        assert row["gate_outcome"] == "drift"
        assert row["gate_exit_code"] == 0
        assert row["success"] is True
        assert row["gate_event"] == "pull_request"
        assert row["gate_base_revision"] == "d" * 40
        assert row["gate_base_resolved_from"] == "remote"
        assert row["gate_blocking_inherited"] == 1
        assert row["gate_blocking_indeterminate"] == 1
        assert row["gate_blocking_introduced"] == 0
        assert row["gate_informational_introduced"] == 1
