"""Nightly config loading and guard order (task 5.1)."""

from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from agent_scenarios import FakeExecutor, Outcome
from agent_scenarios.executor import ScenarioExecutor
from agent_scenarios.nightly import ConfigError, NightlyConfig, load_config, run_nightly
from agent_scenarios.results_store import JsonlResultsStore, RunRecord, lock_path_for
from tests.test_schemas import load_schema


def scenario_yaml(sid: str, skill: str = "plan-feature", vendors: tuple[str, ...] = ("claude", "codex")) -> str:
    return yaml.safe_dump({
        "id": sid, "name": sid, "task_prompt": f"/{skill} go", "skill_under_test": skill,
        "vendors": list(vendors), "fixture": {"files": {"README.md": "x"}},
        "goal_gates": {"verify": [{"id": "wrote-out", "check": "file", "path": "out.txt"}]},
    })


def make_suite(root: Path, ids: tuple[str, ...] = ("a-one", "b-two"),
               vendors: tuple[str, ...] = ("claude", "codex")) -> Path:
    d = root / "scenarios"
    d.mkdir(exist_ok=True)
    for sid in ids:
        (d / f"{sid}.scenario.yaml").write_text(scenario_yaml(sid, vendors=vendors))
    return d


def config_dict(root: Path, **over: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "enabled": True,
        "disable_file": str(root / "DISABLED"),
        "scenarios_dir": str(root / "scenarios"),
        "repo_root": str(root / "repo"),
        "vendors": ["claude", "codex"],
        "vendor_commands": {"claude": "claude -p {prompt}", "codex": "codex exec {prompt}"},
        "results": {"path": str(root / "state" / "results.jsonl")},
    }
    cfg.update(over)
    return cfg


def write_config(root: Path, **over: Any) -> Path:
    path = root / "nightly.yaml"
    path.write_text(yaml.safe_dump(config_dict(root, **over)))
    return path


class Factory:
    """executor_factory that records whether it was ever called."""

    def __init__(self, executor: ScenarioExecutor | None = None) -> None:
        self.calls = 0
        self.executor = executor or FakeExecutor({"a-one": Outcome(write_files={"out.txt": "x"}),
                                                  "b-two": Outcome(write_files={"out.txt": "x"})})

    def __call__(self, cfg: NightlyConfig) -> ScenarioExecutor:
        self.calls += 1
        return self.executor


def run_records(root: Path) -> list[RunRecord]:
    store = JsonlResultsStore(root / "state" / "results.jsonl")
    return [r for r in store.iter_records() if isinstance(r, RunRecord)]


# --- guard 0: invalid config ---------------------------------------------------------


@pytest.mark.parametrize(
    "over",
    [
        {"vendor_commands": {"claude": "claude -p {prompt}"}},  # codex lacks a command
        {"vendors": ["claude"]},  # allowlist < 2
        {"env_set": {"GH_TOKEN": "x"}},
        {"env_set": {"COORDINATION_API_URL": "http://real"}},
        {"env_set": {"COORDINATOR_URL": "http://real"}},
        {"env_scrub": ["MY_SECRET"], "env_set": {"MY_SECRET": "x"}},
        {"gaps": {"api_key_env": "MY_GAP_KEY"}, "env_set": {"MY_GAP_KEY": "x"}},
        {"gaps": {"coordinator_url_env": "MY_GAP_URL"}, "env_set": {"MY_GAP_URL": "x"}},
        {"caps": {"max_pairs": 0}},
        {"unknown_key": 1},
    ],
)
def test_invalid_config_exits_2_and_writes_nothing(
    tmp_path: Path, over: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    make_suite(tmp_path)
    factory = Factory()
    code = run_nightly(write_config(tmp_path, **over), executor_factory=factory)
    assert code == 2
    assert factory.calls == 0
    assert not (tmp_path / "state").exists()
    assert "invalid" in capsys.readouterr().err


def test_unparsable_and_missing_config(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("enabled: [unclosed")
    assert run_nightly(bad) == 2
    assert run_nightly(tmp_path / "missing.yaml") == 2
    with pytest.raises(ConfigError):
        load_config(bad)


def test_config_omitting_caps_enabled_and_kill_file_takes_defaults(tmp_path: Path) -> None:
    raw = config_dict(tmp_path)
    for key in ("caps", "enabled", "disable_file"):
        raw.pop(key, None)
    path = tmp_path / "min.yaml"
    path.write_text(yaml.safe_dump(raw))
    cfg = load_config(path)
    assert cfg.enabled is False
    assert cfg.caps.model_dump() == {"max_pairs": 30, "max_pairs_per_vendor": 15,
                                     "max_wall_clock_minutes": 240, "per_pair_timeout_seconds": 1200}
    assert cfg.disable_file == "~/.config/agent-scenarios/DISABLED"
    assert cfg.retain_failed_runs == 7


def test_pydantic_config_agrees_with_json_schema(tmp_path: Path) -> None:
    schema = load_schema("nightly-config.schema.json")
    valid = config_dict(tmp_path)
    jsonschema.validate(valid, schema)
    NightlyConfig.model_validate(valid)
    invalid = config_dict(tmp_path, env_set={"GH_TOKEN": "x"})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
    with pytest.raises(ValueError):
        NightlyConfig.model_validate(invalid)


# --- guards 1-5 ------------------------------------------------------------------------


def test_disabled_by_default_builds_no_executor(tmp_path: Path) -> None:
    make_suite(tmp_path)
    factory = Factory()
    assert run_nightly(write_config(tmp_path, enabled=False), executor_factory=factory) == 0
    assert factory.calls == 0
    recs = run_records(tmp_path)
    assert [r.status for r in recs] == ["disabled"]
    assert list(JsonlResultsStore(tmp_path / "state" / "results.jsonl").iter_results()) == []


def test_kill_file_disables_an_enabled_config(tmp_path: Path) -> None:
    make_suite(tmp_path)
    (tmp_path / "DISABLED").write_text("")
    factory = Factory()
    assert run_nightly(write_config(tmp_path), executor_factory=factory) == 0
    assert factory.calls == 0
    assert [r.status for r in run_records(tmp_path)] == ["disabled"]


def test_overlapping_run_is_locked(tmp_path: Path) -> None:
    make_suite(tmp_path)
    lock = lock_path_for(tmp_path / "state" / "results.jsonl")
    lock.parent.mkdir(parents=True)
    factory = Factory()
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run_nightly(write_config(tmp_path), executor_factory=factory) == 0
    assert factory.calls == 0
    assert [r.status for r in run_records(tmp_path)] == ["locked"]


def test_fewer_than_two_effective_vendors_is_config_error(tmp_path: Path) -> None:
    make_suite(tmp_path, vendors=("claude",))
    factory = Factory()
    assert run_nightly(write_config(tmp_path), executor_factory=factory) == 2
    assert factory.calls == 0
    assert [r.status for r in run_records(tmp_path)] == ["config_error"]


@pytest.mark.parametrize(
    "caps",
    [{"max_pairs": 3}, {"max_pairs_per_vendor": 1}],
)
def test_over_cap_plan_refuses_to_start(tmp_path: Path, caps: dict[str, int]) -> None:
    make_suite(tmp_path)  # 2 scenarios x 2 vendors = 4 pairs, 2 per vendor
    factory = Factory()
    assert run_nightly(write_config(tmp_path, caps=caps), executor_factory=factory) == 2
    assert factory.calls == 0
    recs = run_records(tmp_path)
    assert [r.status for r in recs] == ["cap_exceeded"] and recs[0].planned_pairs == 4
    assert list(JsonlResultsStore(tmp_path / "state" / "results.jsonl").iter_results()) == []
    assert not (tmp_path / "state" / "workspaces").exists()


def test_missing_suite_is_config_error(tmp_path: Path) -> None:
    (tmp_path / "scenarios").mkdir()
    assert run_nightly(write_config(tmp_path), executor_factory=Factory()) == 2
    assert [r.status for r in run_records(tmp_path)] == ["config_error"]


# --- dry run ---------------------------------------------------------------------------


@pytest.mark.parametrize("enabled", [True, False])
def test_dry_run_plans_without_executing(
    tmp_path: Path, enabled: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    make_suite(tmp_path)
    (tmp_path / "DISABLED").write_text("")
    factory = Factory()
    code = run_nightly(write_config(tmp_path, enabled=enabled), dry=True, executor_factory=factory)
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["enabled"] is enabled and out["kill_file_present"] is True
    assert out["effective_vendors"] == ["claude", "codex"]
    assert out["planned_pairs"] == [["a-one", "claude"], ["a-one", "codex"],
                                    ["b-two", "claude"], ["b-two", "codex"]]
    assert out["cap_evaluation"]["ok"] is True
    assert factory.calls == 0
    assert not (tmp_path / "state").exists()  # no record, no lock, nothing


def test_dry_run_over_cap_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_suite(tmp_path)
    code = run_nightly(write_config(tmp_path, caps={"max_pairs": 1}), dry=True)
    assert code == 2
    assert json.loads(capsys.readouterr().out)["cap_evaluation"]["exceeded"]
    assert not (tmp_path / "state").exists()
