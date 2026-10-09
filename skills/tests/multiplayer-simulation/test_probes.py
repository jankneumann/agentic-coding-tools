"""Probe seam tests (S.1-S.5; design D4). The registry starts empty."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest

from mpsim import probes
from mpsim.errors import UsageError
from mpsim.probes import Collision, ProbeResult
from mpsim.runner import run
from mpsim.scenarios import scenario_ids

HARNESS = Path(__file__).resolve().parent
COLLISION_SCENARIOS = ("same-requirement-collision", "different-requirement-control")


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(probes.REGISTRY)
    probes.REGISTRY.clear()
    yield
    probes.REGISTRY.clear()
    probes.REGISTRY.update(saved)


class StubProbe:
    def __init__(self, probe_id="stub", *, level="requirement", other_change="sim-alice-notes"):
        self.probe_id = probe_id
        self._collision = Collision(level, other_change, "Note Titles")

    def detect(self, view, change_id):
        return ProbeResult(self.probe_id, "ok", [self._collision], None)


class RaisingProbe:
    probe_id = "raiser"

    def detect(self, view, change_id):
        raise RuntimeError("boom")


class HangingProbe:
    probe_id = "hanger"

    def detect(self, view, change_id):
        threading.Event().wait(30)
        return ProbeResult(self.probe_id, "ok", [], None)


def _hash_tree(*dirs: Path) -> dict[str, str]:
    digests = {}
    for root in dirs:
        for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            digests[str(path.relative_to(HARNESS))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def test_no_probe_is_registered_at_import_time():
    import importlib
    import sys

    sys.modules.pop("mpsim.probes", None)
    fresh = importlib.import_module("mpsim.probes")
    try:
        assert fresh.REGISTRY == {}
    finally:
        sys.modules["mpsim.probes"] = probes


def test_requirement_level_collision_sets_collision_detected():
    probes.register(StubProbe())
    result = run("same-requirement-collision")
    assert result.exit_code == 0
    report = result.report
    assert report["collision_detected"] is True
    assert [p["probe_id"] for p in report["probes"]] == ["stub"]
    assert report["probes"][0]["status"] == "ok"
    assert report["probes"][0]["collisions"] == [
        {"level": "requirement", "other_change": "sim-alice-notes", "requirement": "Note Titles"}
    ]


def test_non_requirement_level_collision_does_not_count_as_detection():
    probes.register(StubProbe(level="file"))
    report = run("same-requirement-collision").report
    assert report["collision_detected"] is False
    assert report["probes"][0]["status"] == "ok"


def test_collision_against_an_unrelated_change_does_not_count():
    probes.register(StubProbe(other_change="sim-somebody-else"))
    assert run("same-requirement-collision").report["collision_detected"] is False


def test_raising_probe_is_recorded_as_error_and_run_completes():
    probes.register(RaisingProbe())
    result = run("same-requirement-collision")
    assert result.exit_code == 0
    entry = result.report["probes"][0]
    assert entry["probe_id"] == "raiser"
    assert entry["status"] == "error"
    assert entry["error"] and "boom" in entry["error"]
    assert result.report["collision_detected"] is False


def test_probe_exceeding_the_timeout_is_recorded_as_error(monkeypatch):
    monkeypatch.setattr(probes, "PER_PROBE_TIMEOUT", 0.2)
    probes.register(HangingProbe())
    result = run("same-requirement-collision")
    assert result.exit_code == 0
    entry = result.report["probes"][0]
    assert entry["status"] == "error"
    assert "timeout" in entry["error"].lower()


def test_unknown_probe_id_is_a_usage_error():
    with pytest.raises(UsageError, match="does-not-exist"):
        run("same-requirement-collision", probe_ids=["does-not-exist"])


def test_probe_selection_restricts_the_run():
    probes.register(StubProbe("one"))
    probes.register(StubProbe("two"))
    report = run("same-requirement-collision", probe_ids=["two"]).report
    assert [p["probe_id"] for p in report["probes"]] == ["two"]


def test_no_probe_flag_runs_every_registered_probe():
    probes.register(StubProbe("one"))
    probes.register(StubProbe("two"))
    report = run("same-requirement-collision").report
    assert [p["probe_id"] for p in report["probes"]] == ["one", "two"]


def test_registering_a_probe_edits_no_scenario_definition():
    watched = [HARNESS / "mpsim" / "scenarios", HARNESS / "evaluation" / "scenarios"]
    watched = [d for d in watched if d.exists()]
    before = _hash_tree(*watched)
    probes.register(StubProbe())
    for scenario_id in scenario_ids():
        report = run(scenario_id).report
        if scenario_id in COLLISION_SCENARIOS:
            assert [p["probe_id"] for p in report["probes"]] == ["stub"], scenario_id
    assert _hash_tree(*watched) == before
    assert before, "expected scenario files to hash"


def test_duplicate_registration_is_rejected():
    probes.register(StubProbe("dup"))
    with pytest.raises(ValueError):
        probes.register(StubProbe("dup"))
