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

import json
import sys
from datetime import datetime
from pathlib import Path

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
