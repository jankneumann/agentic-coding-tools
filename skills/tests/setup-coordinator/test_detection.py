"""Harness-detection contract for the setup-coordinator entrypoint.

Every case here is constructed: a temporary ``HOME``, a temporary ``PATH``, and
a roster written into ``tmp_path``. Asserting against the operator's real
machine would make the outcome depend on which CLIs happen to be installed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import setup_coordinator as sc


def _by_vendor(report: dict) -> dict[str, dict]:
    return {entry["vendor"]: entry for entry in report["vendors"]}


@pytest.fixture
def four_vendor_roster(agents_yaml, local_agent) -> Path:
    return agents_yaml(
        {
            "claude-local": local_agent("claude", agent_type="claude_code"),
            "codex-local": local_agent("codex", agent_type="codex"),
            "grok-local": local_agent("grok", agent_type="grok"),
            "antigravity-local": local_agent("agy", agent_type="antigravity"),
        }
    )


# --------------------------------------------------------------------------- #
# Task 1.3 — four states, and presence is not validity
# --------------------------------------------------------------------------- #


def test_vendor_fully_present_is_ready(
    four_vendor_roster, fake_home, make_executable
):
    """Scenario: Vendor fully present."""
    make_executable("claude")
    (fake_home / ".claude.json").write_text("{}", encoding="utf-8")

    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )

    claude = _by_vendor(report)["claude"]
    assert claude["state"] == "ready"
    assert claude["cli_on_path"] is True
    assert claude["config_present"] is True
    assert claude["config_artifact"] == ".claude.json"


def test_vendor_cli_absent_is_cli_missing_and_names_the_command(
    four_vendor_roster, fake_home, fake_path_dir
):
    """Scenario: Vendor CLI absent — the searched-for command is reported."""
    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )

    codex = _by_vendor(report)["codex"]
    assert codex["state"] == "cli_missing"
    assert codex["cli_on_path"] is False
    assert codex["cli_command"] == "codex"


def test_cli_present_without_declared_artifact_file_is_config_missing(
    four_vendor_roster, fake_home, make_executable
):
    make_executable("grok")

    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )

    grok = _by_vendor(report)["grok"]
    assert grok["state"] == "config_missing"
    assert grok["config_artifact"] == ".grok/auth.json"
    assert grok["config_present"] is False
    assert grok["remediation"]


def test_vendor_with_no_detectable_config_location_is_unknown(
    four_vendor_roster, fake_home, make_executable
):
    """Scenario: Vendor has no detectable config location.

    ``unknown`` must not collapse into ``config_missing``, and must not carry a
    login instruction — antigravity has no login command to instruct.
    """
    make_executable("agy")

    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )

    agy = _by_vendor(report)["antigravity"]
    assert agy["state"] == "unknown"
    assert agy["config_artifact"] is None
    assert agy["config_present"] is None
    assert agy["remediation"] is None


def test_vendor_absent_from_the_artifact_table_is_unknown_not_an_error(
    agents_yaml, local_agent, fake_home, make_executable
):
    """A roster gaining a sixth harness degrades to `unknown`, never a crash."""
    roster = agents_yaml({"newvendor-local": local_agent("newvendor")})
    make_executable("newvendor")

    report = sc.build_harness_report(env={"AGENTS_YAML": str(roster)}, home=fake_home)

    entry = _by_vendor(report)["newvendor"]
    assert entry["state"] == "unknown"
    assert entry["remediation"] is None


def test_presence_is_not_validity(four_vendor_roster, fake_home, make_executable):
    """Scenario: Presence is not validity."""
    make_executable("claude")
    (fake_home / ".claude.json").write_text("{}", encoding="utf-8")

    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )
    assert report["checked_validity"] is False

    rendered = sc.render_harness_report(report).lower()
    assert "valid" in rendered and "not" in rendered
    assert "expir" in rendered


def test_state_precedence_puts_cli_missing_ahead_of_unknown(
    four_vendor_roster, fake_home, fake_path_dir
):
    """`cli_missing` is decidable without the artifact table, so it wins."""
    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )
    assert _by_vendor(report)["antigravity"]["state"] == "cli_missing"


def test_summary_counts_match_the_vendor_entries(
    four_vendor_roster, fake_home, make_executable
):
    make_executable("claude")
    make_executable("agy")
    (fake_home / ".claude.json").write_text("{}", encoding="utf-8")

    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )
    summary = report["summary"]
    assert summary["total"] == len(report["vendors"]) == 4
    assert summary["ready"] == 1
    assert summary["unknown"] == 1
    assert summary["cli_missing"] == 2
    assert summary["config_missing"] == 0
    assert (
        summary["ready"] + summary["cli_missing"] + summary["config_missing"]
        + summary["unknown"] == summary["total"]
    )


def test_host_block_records_the_home_that_was_searched(
    four_vendor_roster, fake_home, fake_path_dir
):
    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )
    assert report["host"]["home"] == str(fake_home)
    assert report["host"]["platform"]


# --------------------------------------------------------------------------- #
# Task 1.3a — roster resolution and network abstinence
# --------------------------------------------------------------------------- #


def test_agents_yaml_env_wins_over_coordinator_dir(tmp_path, agents_yaml, local_agent):
    """Scenario: Agents file resolved from configuration."""
    explicit = agents_yaml({"claude-local": local_agent("claude")}, name="explicit.yaml")
    coordinator_dir = tmp_path / "coordinator"
    coordinator_dir.mkdir()
    (coordinator_dir / "agents.yaml").write_text("agents: {}\n", encoding="utf-8")

    resolved, tried = sc.resolve_agents_yaml(
        {"AGENTS_YAML": str(explicit), "COORDINATOR_DIR": str(coordinator_dir)}
    )

    assert resolved == explicit
    assert str(explicit) in tried


def test_coordinator_dir_is_used_when_agents_yaml_is_unset(tmp_path):
    coordinator_dir = tmp_path / "coordinator"
    coordinator_dir.mkdir()
    expected = coordinator_dir / "agents.yaml"
    expected.write_text("agents: {}\n", encoding="utf-8")

    resolved, _ = sc.resolve_agents_yaml({"COORDINATOR_DIR": str(coordinator_dir)})

    assert resolved == expected


def test_a_missing_agents_yaml_env_path_does_not_silently_win(tmp_path):
    """`load_agents_yaml` only honours an explicit path that exists.

    A resolver that returned the non-existent path anyway would hand
    `check_all_vendors` a path it rejects, and the network branch would run.
    """
    coordinator_dir = tmp_path / "coordinator"
    coordinator_dir.mkdir()
    fallback = coordinator_dir / "agents.yaml"
    fallback.write_text("agents: {}\n", encoding="utf-8")

    resolved, tried = sc.resolve_agents_yaml(
        {
            "AGENTS_YAML": str(tmp_path / "nope.yaml"),
            "COORDINATOR_DIR": str(coordinator_dir),
        }
    )

    assert resolved == fallback
    assert str(tmp_path / "nope.yaml") in tried


def test_unresolvable_roster_names_both_paths_and_exits_non_zero(
    tmp_path, fake_home, monkeypatch, capsys
):
    missing_explicit = tmp_path / "missing-agents.yaml"
    missing_dir = tmp_path / "missing-coordinator"

    resolved, tried = sc.resolve_agents_yaml(
        {"AGENTS_YAML": str(missing_explicit), "COORDINATOR_DIR": str(missing_dir)}
    )
    assert resolved is None
    assert str(missing_explicit) in tried
    assert str(missing_dir / "agents.yaml") in tried

    with pytest.raises(sc.RosterNotFoundError):
        sc.build_harness_report(
            env={"AGENTS_YAML": str(missing_explicit), "COORDINATOR_DIR": str(missing_dir)}
        )

    monkeypatch.setenv("AGENTS_YAML", str(missing_explicit))
    monkeypatch.setenv("COORDINATOR_DIR", str(missing_dir))
    exit_code = sc.main(["detect-harnesses"])
    captured = capsys.readouterr()
    assert exit_code != 0
    assert str(missing_explicit) in captured.err
    assert str(missing_dir / "agents.yaml") in captured.err


@pytest.fixture
def forbid_network(monkeypatch):
    """Fail loudly if any roster path reaches for the network."""
    import vendor_health

    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("roster resolution attempted a network request")

    monkeypatch.setattr(vendor_health, "urlopen", _explode)
    return _explode


def test_no_network_request_on_the_resolve_ok_path(
    four_vendor_roster, fake_home, fake_path_dir, forbid_network, monkeypatch
):
    """Scenario: Agent roster is never fetched over the network."""
    monkeypatch.setenv("COORDINATION_API_URL", "http://10.255.255.1:9")

    report = sc.build_harness_report(
        env={
            "AGENTS_YAML": str(four_vendor_roster),
            "COORDINATION_API_URL": "http://10.255.255.1:9",
        },
        home=fake_home,
    )
    assert len(report["vendors"]) == 4


def test_no_network_request_on_the_resolve_fail_path(
    tmp_path, fake_home, forbid_network, monkeypatch
):
    monkeypatch.setenv("COORDINATION_API_URL", "http://10.255.255.1:9")

    with pytest.raises(sc.RosterNotFoundError):
        sc.build_harness_report(
            env={
                "AGENTS_YAML": str(tmp_path / "absent.yaml"),
                "COORDINATOR_DIR": str(tmp_path / "absent-dir"),
                "COORDINATION_API_URL": "http://10.255.255.1:9",
            },
            home=fake_home,
        )


def test_resolution_never_falls_back_to_a_cwd_relative_roster(
    tmp_path, fake_home, monkeypatch
):
    """`load_agents_yaml`'s last resort is `$CWD/agent-coordinator/agents.yaml`."""
    cwd = tmp_path / "elsewhere"
    (cwd / "agent-coordinator").mkdir(parents=True)
    (cwd / "agent-coordinator" / "agents.yaml").write_text(
        "agents:\n  ghost-local:\n    type: ghost\n    cli:\n      command: ghost\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(cwd)

    with pytest.raises(sc.RosterNotFoundError):
        sc.build_harness_report(
            env={"COORDINATOR_DIR": str(tmp_path / "absent-dir")}, home=fake_home
        )


def test_resolution_refuses_cwd_roster_when_coordinator_dir_is_unset(
    tmp_path, fake_home, monkeypatch
):
    """The vulnerable configuration: BOTH env vars unset, cwd holding a roster.

    The sibling test above sets ``COORDINATOR_DIR``, which makes the base
    non-None and routes past the branch that defaults it. That left the real
    defect untestable: an implementation defaulting the base to a bare relative
    ``Path("agent-coordinator")`` passed the whole suite while succeeding from
    the repository root and failing from every other directory with identical
    environment.
    """
    cwd = tmp_path / "elsewhere"
    (cwd / "agent-coordinator").mkdir(parents=True)
    (cwd / "agent-coordinator" / "agents.yaml").write_text(
        "agents:\n  ghost-local:\n    type: ghost\n    cli:\n      command: ghost\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(cwd)

    with pytest.raises(sc.RosterNotFoundError):
        sc.build_harness_report(env={}, home=fake_home)


def test_unresolvable_roster_reports_both_locations_absolutely(
    tmp_path, fake_home, monkeypatch
):
    """The spec requires naming both locations tried, and a relative path is
    not a location -- it is a location plus an unstated working directory."""
    monkeypatch.chdir(tmp_path)

    _, tried = sc.resolve_agents_yaml(env={})
    assert len(tried) == 2, tried
    assert any("AGENTS_YAML" in t for t in tried), tried
    assert any("COORDINATOR_DIR" in t for t in tried), tried
    for entry in tried:
        assert not entry.startswith(("agent-coordinator", "./")), (
            f"{entry!r} is cwd-relative; the report must not depend on where "
            "the process happened to be started"
        )


# --------------------------------------------------------------------------- #
# Task 1.3b — roster filtering
# --------------------------------------------------------------------------- #


def test_remote_agents_are_excluded_and_vendors_are_not_double_counted(
    agents_yaml, local_agent, fake_home, fake_path_dir
):
    """Scenario: Remote and command-less agents are excluded."""
    roster = agents_yaml(
        {
            "claude-local": local_agent("claude"),
            "claude-remote": local_agent("claude"),
            "codex-local": local_agent("codex"),
            "codex-remote": local_agent("codex"),
        }
    )

    report = sc.build_harness_report(env={"AGENTS_YAML": str(roster)}, home=fake_home)

    assert sorted(entry["vendor"] for entry in report["vendors"]) == ["claude", "codex"]
    assert sorted(entry["agent_id"] for entry in report["vendors"]) == [
        "claude-local",
        "codex-local",
    ]


def test_agent_with_empty_cli_command_is_excluded(
    agents_yaml, fake_home, fake_path_dir
):
    """An empty command would emit `cli_command: ""`, failing the contract."""
    roster = agents_yaml(
        {
            "claude-local": {"type": "claude_code", "cli": {"command": "claude"}},
            "hollow-local": {"type": "hollow", "cli": {"command": ""}},
            "blank-local": {"type": "blank", "cli": {}},
        }
    )

    report = sc.build_harness_report(env={"AGENTS_YAML": str(roster)}, home=fake_home)

    assert [entry["vendor"] for entry in report["vendors"]] == ["claude"]


def test_vendor_key_is_the_agent_id_stem(agents_yaml, local_agent, fake_home, fake_path_dir):
    roster = agents_yaml({"antigravity-local": local_agent("agy", agent_type="antigravity")})

    report = sc.build_harness_report(env={"AGENTS_YAML": str(roster)}, home=fake_home)

    entry = report["vendors"][0]
    assert entry["vendor"] == "antigravity"
    assert entry["agent_id"] == "antigravity-local"
    assert entry["agent_type"] == "antigravity"


# --------------------------------------------------------------------------- #
# Task 1.4a — degradation reporting
# --------------------------------------------------------------------------- #


def test_unreadable_roster_degrades_rather_than_reporting_nothing(
    tmp_path, fake_home, fake_path_dir
):
    """Scenario: Degraded run is distinguishable from an empty one."""
    broken = tmp_path / "agents.yaml"
    broken.write_text("agents: [this: is: not: a: mapping\n", encoding="utf-8")

    report = sc.build_harness_report(env={"AGENTS_YAML": str(broken)}, home=fake_home)

    assert report["vendors"] == []
    assert report["degraded"] is True
    assert len(report["warnings"]) >= 1


def test_unavailable_sibling_module_degrades(
    four_vendor_roster, fake_home, fake_path_dir, monkeypatch
):
    def _unavailable(_path):
        raise ImportError("no module named 'vendor_health'")

    monkeypatch.setattr(sc, "_check_all_vendors", _unavailable)

    report = sc.build_harness_report(
        env={"AGENTS_YAML": str(four_vendor_roster)}, home=fake_home
    )

    assert report["vendors"] == []
    assert report["degraded"] is True
    assert any("vendor_health" in warning for warning in report["warnings"])


def test_complete_run_asserts_completeness(agents_yaml, fake_home, fake_path_dir):
    """Scenario: Complete run asserts completeness."""
    roster = agents_yaml({})

    report = sc.build_harness_report(env={"AGENTS_YAML": str(roster)}, home=fake_home)

    assert report["vendors"] == []
    assert report["degraded"] is False
    assert report["warnings"] == []


def test_a_degraded_empty_report_is_not_byte_equal_to_a_clean_empty_one(
    agents_yaml, tmp_path, fake_home, fake_path_dir, monkeypatch
):
    """The discriminating assertion: the two runs must not serialize alike."""
    clean_roster = agents_yaml({}, name="clean.yaml")
    clean = sc.build_harness_report(
        env={"AGENTS_YAML": str(clean_roster)}, home=fake_home
    )

    broken = tmp_path / "broken.yaml"
    broken.write_text("agents: [unbalanced\n", encoding="utf-8")
    degraded = sc.build_harness_report(env={"AGENTS_YAML": str(broken)}, home=fake_home)

    assert clean["vendors"] == degraded["vendors"] == []
    assert json.dumps(clean, sort_keys=True) != json.dumps(degraded, sort_keys=True)


# --------------------------------------------------------------------------- #
# Task 1.4b — the subcommand's exit contract
# --------------------------------------------------------------------------- #


def test_detect_exits_zero_when_every_vendor_is_absent(
    four_vendor_roster, fake_home, fake_path_dir, monkeypatch, capsys
):
    """Scenario: Detection exit status reflects reportability, not readiness."""
    monkeypatch.setenv("AGENTS_YAML", str(four_vendor_roster))

    exit_code = sc.main(["detect-harnesses", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert {entry["state"] for entry in payload["vendors"]} == {"cli_missing"}


def test_detect_exits_zero_on_a_degraded_report(tmp_path, fake_home, monkeypatch, capsys):
    broken = tmp_path / "agents.yaml"
    broken.write_text("agents: [unbalanced\n", encoding="utf-8")
    monkeypatch.setenv("AGENTS_YAML", str(broken))

    exit_code = sc.main(["detect-harnesses", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["degraded"] is True


def test_detect_exits_non_zero_only_when_no_report_can_be_produced(
    tmp_path, fake_home, monkeypatch, capsys
):
    monkeypatch.setenv("AGENTS_YAML", str(tmp_path / "absent.yaml"))
    monkeypatch.setenv("COORDINATOR_DIR", str(tmp_path / "absent-dir"))

    exit_code = sc.main(["detect-harnesses", "--json"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.out.strip() == ""
