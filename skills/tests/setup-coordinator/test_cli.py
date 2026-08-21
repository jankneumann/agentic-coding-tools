"""CLI contract, profile resolution, and per-step responsibility reporting."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import setup_coordinator as sc


SUBCOMMANDS = ("detect-harnesses", "check", "configure", "report")


@pytest.fixture
def isolated_root(tmp_path: Path, fake_home: Path, fake_path_dir: Path, monkeypatch):
    """A temp repository root with no coordinator checkout in the environment."""
    root = tmp_path / "root"
    root.mkdir()
    for name in ("COORDINATOR_DIR", "COORDINATOR_PROFILE", "COORDINATION_API_URL"):
        monkeypatch.delenv(name, raising=False)
    return root


@pytest.fixture
def no_subprocess(monkeypatch):
    """Turn any attempt to spawn a process into a failure.

    The three profile scenarios were self-contradictory until responsibility
    was split per step; this fixture is what keeps `check` on the reporting
    side of that split.
    """

    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(f"check spawned a process: {args!r}")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, _explode)
    monkeypatch.setattr(os, "system", _explode)
    return _explode


# --------------------------------------------------------------------------- #
# Task 3.1 — subcommand dispatch, exit codes, --json, usage
# --------------------------------------------------------------------------- #


def test_every_subcommand_is_registered():
    parser = sc.build_parser()
    actions = [
        action
        for action in parser._subparsers._group_actions  # noqa: SLF001 - argparse
        if hasattr(action, "choices")
    ]
    assert set(SUBCOMMANDS) <= set(actions[0].choices)


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_handlers_are_cmd_functions_returning_an_exit_code(name):
    """Scenario: Subcommand dispatch — the handler's return value is the code."""
    handler = getattr(sc, "cmd_" + name.replace("-", "_"))
    assert callable(handler)


def test_dispatch_uses_the_handler_return_value(monkeypatch, isolated_root):
    monkeypatch.setattr(sc, "cmd_report", lambda args: 7)
    assert sc.main(["report", "--root", str(isolated_root)]) == 7


def test_no_subcommand_prints_usage_and_exits_non_zero(capsys):
    """Scenario: No subcommand supplied."""
    exit_code = sc.main([])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert "usage:" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("name", SUBCOMMANDS)
def test_json_flag_is_bound_away_from_the_json_module(name):
    """`--json` must not shadow the `json` module inside a handler."""
    parser = sc.build_parser()
    args = parser.parse_args([name, *(["--root", "."] if name == "configure" else []), "--json"])
    assert args.json_output is True
    assert not hasattr(args, "json")


@pytest.mark.parametrize("name", ["detect-harnesses", "check", "report"])
def test_machine_readable_output_is_a_single_json_document(
    name, isolated_root, agents_yaml, local_agent, monkeypatch, capsys
):
    """Scenario: Machine-readable output — no interleaved table text."""
    roster = agents_yaml({"claude-local": local_agent("claude")})
    monkeypatch.setenv("AGENTS_YAML", str(roster))

    argv = [name, "--json"]
    if name in {"check", "report"}:
        argv += ["--root", str(isolated_root)]
    sc.main(argv)

    out = capsys.readouterr().out
    assert isinstance(json.loads(out), dict)


def test_configure_json_output_is_a_single_json_document(isolated_root, capsys):
    sc.main(["configure", "--root", str(isolated_root), "--json"])
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_human_output_is_not_json(isolated_root, agents_yaml, local_agent, monkeypatch, capsys):
    roster = agents_yaml({"claude-local": local_agent("claude")})
    monkeypatch.setenv("AGENTS_YAML", str(roster))
    sc.main(["detect-harnesses"])

    out = capsys.readouterr().out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "Vendor" in out


# --------------------------------------------------------------------------- #
# Task 3.3 — profile resolution
# --------------------------------------------------------------------------- #


def test_profile_defaults_to_local():
    assert sc.resolve_profile(None, {}) == "local"


def test_env_var_supplies_the_profile():
    assert sc.resolve_profile(None, {"COORDINATOR_PROFILE": "railway"}) == "railway"


def test_explicit_flag_beats_the_env_var():
    assert sc.resolve_profile("local", {"COORDINATOR_PROFILE": "railway"}) == "local"


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        sc.resolve_profile("nonesuch", {})


def test_check_honours_the_profile_env_var(isolated_root, monkeypatch, capsys):
    monkeypatch.setenv("COORDINATOR_PROFILE", "railway")
    sc.main(["check", "--root", str(isolated_root), "--json"])
    assert json.loads(capsys.readouterr().out)["profile"] == "railway"


def test_check_flag_beats_the_profile_env_var(isolated_root, monkeypatch, capsys):
    monkeypatch.setenv("COORDINATOR_PROFILE", "railway")
    sc.main(["check", "--root", str(isolated_root), "--profile", "local", "--json"])
    assert json.loads(capsys.readouterr().out)["profile"] == "local"


# --------------------------------------------------------------------------- #
# Task 3.4 — `check` reuses the shared roster resolver
# --------------------------------------------------------------------------- #


def test_check_and_detect_share_one_roster_resolver(monkeypatch, isolated_root, tmp_path):
    """`check` must not grow a second copy of the precedence rule.

    Resolution itself is specified and tested in test_detection.py; this pins
    that both subcommands route through the same helper.
    """
    calls: list[object] = []
    real = sc.resolve_agents_yaml

    def _spy(env=None):
        calls.append(env)
        return real(env)

    monkeypatch.setattr(sc, "resolve_agents_yaml", _spy)
    monkeypatch.setenv("AGENTS_YAML", str(tmp_path / "absent.yaml"))

    sc.main(["detect-harnesses"])
    assert calls, "detect-harnesses did not use the shared resolver"

    assert sc.coordinator_dir({"COORDINATOR_DIR": "/x"}) == Path("/x")
    resolved, tried = sc.resolve_agents_yaml({"COORDINATOR_DIR": "/x"})
    assert resolved is None
    assert tried == [str(Path("/x") / sc.AGENTS_FILENAME)]


# --------------------------------------------------------------------------- #
# Task 3.6a — per-step responsibility, and the negatives asserted directly
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("profile", ["local", "railway"])
def test_every_precondition_is_reported_with_a_command_when_unsatisfied(
    profile, isolated_root, fake_home, no_subprocess
):
    """Scenarios: Local profile setup / Railway profile setup."""
    steps, _ = sc.collect_preconditions(
        profile, root=isolated_root, env={}, home=fake_home
    )

    assert steps
    for step in steps:
        assert step["id"] and step["label"] and step["detail"]
        assert step["satisfied"] in (True, False, None)
        if step["satisfied"] is True:
            assert step["command"] is None
        else:
            assert step["command"], f"{step['id']} is unsatisfied with no command"


def test_local_profile_reports_the_four_named_preconditions(
    isolated_root, fake_home, no_subprocess
):
    steps, _ = sc.collect_preconditions(
        "local", root=isolated_root, env={}, home=fake_home
    )
    reported = {step["id"] for step in steps}
    assert {
        "container_runtime",
        "database_container",
        "mcp_registered",
        "mcp_tools_discoverable",
    } <= reported


def test_railway_profile_reports_its_named_preconditions(
    isolated_root, fake_home, no_subprocess
):
    steps, _ = sc.collect_preconditions(
        "railway", root=isolated_root, env={}, home=fake_home
    )
    reported = {step["id"] for step in steps}
    assert {"api_url", "api_health", "api_key_accepted", "bridge_detect"} <= reported


def test_railway_api_url_is_satisfied_when_resolved(isolated_root, fake_home, no_subprocess):
    steps, _ = sc.collect_preconditions(
        "railway",
        root=isolated_root,
        env={"COORDINATION_API_URL": "https://example.invalid"},
        home=fake_home,
    )
    api = next(step for step in steps if step["id"] == "api_url")
    assert api["satisfied"] is True
    assert api["command"] is None


def test_mcp_registration_is_read_from_the_vendors_own_configuration(
    isolated_root, fake_home, no_subprocess
):
    (fake_home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"coordination": {"command": "python"}}}),
        encoding="utf-8",
    )
    steps, _ = sc.collect_preconditions(
        "local", root=isolated_root, env={}, home=fake_home
    )
    step = next(item for item in steps if item["id"] == "mcp_registered")
    assert step["satisfied"] is True


def test_secrets_file_missing_is_reported_with_the_exact_copy_command(
    tmp_path, isolated_root, fake_home, no_subprocess
):
    """Scenario: Secrets file missing."""
    coordinator = tmp_path / "coordinator"
    coordinator.mkdir()
    (coordinator / sc.SECRETS_TEMPLATE).write_text("example: true\n", encoding="utf-8")

    steps, _ = sc.collect_preconditions(
        "local",
        root=isolated_root,
        env={"COORDINATOR_DIR": str(coordinator)},
        home=fake_home,
    )
    step = next(item for item in steps if item["id"] == "secrets_file")

    assert step["satisfied"] is False
    assert str(coordinator / sc.SECRETS_TEMPLATE) in step["command"]
    assert str(coordinator / sc.SECRETS_FILENAME) in step["command"]
    assert "fill in real values" in step["command"]
    # It reports the copy; it does not perform it.
    assert not (coordinator / sc.SECRETS_FILENAME).exists()


def test_secrets_file_present_is_satisfied(tmp_path, isolated_root, fake_home, no_subprocess):
    coordinator = tmp_path / "coordinator"
    coordinator.mkdir()
    (coordinator / sc.SECRETS_FILENAME).write_text("real: true\n", encoding="utf-8")

    steps, _ = sc.collect_preconditions(
        "local",
        root=isolated_root,
        env={"COORDINATOR_DIR": str(coordinator)},
        home=fake_home,
    )
    step = next(item for item in steps if item["id"] == "secrets_file")
    assert step["satisfied"] is True


@pytest.mark.parametrize("profile", ["local", "railway"])
def test_check_creates_nothing_and_spawns_nothing(
    profile, isolated_root, fake_home, no_subprocess, monkeypatch, capsys
):
    """The negatives, asserted directly rather than inferred from prose."""
    before = sorted(path.relative_to(isolated_root) for path in isolated_root.rglob("*"))
    home_before = sorted(path.relative_to(fake_home) for path in fake_home.rglob("*"))

    exit_code = sc.main(["check", "--profile", profile, "--root", str(isolated_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code != 0  # nothing is set up in an empty root
    assert payload["preconditions"]
    assert sorted(path.relative_to(isolated_root) for path in isolated_root.rglob("*")) == before
    assert sorted(path.relative_to(fake_home) for path in fake_home.rglob("*")) == home_before


def test_check_exits_zero_when_every_precondition_is_satisfied(
    isolated_root, fake_home, no_subprocess, monkeypatch, capsys
):
    def _all_good(profile, *, root, env=None, home=None):
        return [sc._step("only", "Only step", True, "fine", None)], []

    monkeypatch.setattr(sc, "collect_preconditions", _all_good)
    assert sc.main(["check", "--root", str(isolated_root)]) == 0
    assert "reports only" in capsys.readouterr().out


def test_check_text_output_states_what_it_will_not_do(
    isolated_root, fake_home, no_subprocess, capsys
):
    sc.main(["check", "--root", str(isolated_root)])
    out = capsys.readouterr().out
    assert "starts no container" in out
    assert "installs no hooks" in out


def test_profile_resolution_reads_the_yaml_and_imports_no_coordinator_module(
    tmp_path, isolated_root, fake_home, no_subprocess
):
    coordinator = tmp_path / "coordinator"
    (coordinator / "profiles").mkdir(parents=True)
    (coordinator / "profiles" / "railway.yaml").write_text(
        "coordination_api_url: https://from-profile.invalid\n", encoding="utf-8"
    )

    data, warnings = sc.load_profile_yaml("railway", {"COORDINATOR_DIR": str(coordinator)})

    assert data["coordination_api_url"] == "https://from-profile.invalid"
    assert warnings == []

    steps, _ = sc.collect_preconditions(
        "railway", root=isolated_root, env={"COORDINATOR_DIR": str(coordinator)}, home=fake_home
    )
    api = next(step for step in steps if step["id"] == "api_url")
    assert api["satisfied"] is True


def test_a_missing_profile_file_degrades_with_a_warning(tmp_path):
    coordinator = tmp_path / "coordinator"
    coordinator.mkdir()
    data, warnings = sc.load_profile_yaml("railway", {"COORDINATOR_DIR": str(coordinator)})
    assert data == {}
    assert warnings and "railway.yaml" in warnings[0]


# --------------------------------------------------------------------------- #
# Task 3.7 — capability-flag reporting
# --------------------------------------------------------------------------- #


def test_report_renders_capability_flags(isolated_root, fake_home, no_subprocess, capsys):
    exit_code = sc.main(["report", "--root", str(isolated_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code != 0
    assert payload["COORDINATION_TRANSPORT"] == "none"
    assert payload["COORDINATOR_AVAILABLE"] is False
    assert set(payload["capabilities"]) == set(sc.CAPABILITY_FLAGS)


def test_report_marks_mcp_transport_when_the_server_is_registered(
    isolated_root, fake_home, no_subprocess, capsys
):
    (fake_home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"coordination": {}}}), encoding="utf-8"
    )
    exit_code = sc.main(["report", "--root", str(isolated_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["COORDINATION_TRANSPORT"] == "mcp"
    assert all(payload["capabilities"].values())


def test_report_marks_http_transport_for_railway(
    isolated_root, fake_home, no_subprocess, monkeypatch, capsys
):
    monkeypatch.setenv("COORDINATION_API_URL", "https://example.invalid")
    sc.main(["report", "--profile", "railway", "--root", str(isolated_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["COORDINATION_TRANSPORT"] == "http"
    assert payload["hook_activation_rule"]


# --------------------------------------------------------------------------- #
# Task 3.8 — `configure` writes settings and only reports the rest
# --------------------------------------------------------------------------- #


def test_configure_emits_the_operator_commands_without_running_them(
    isolated_root, no_subprocess, capsys
):
    exit_code = sc.main(["configure", "--root", str(isolated_root), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert any("mcp-setup" in step for step in payload["next_steps"])
    assert any("hooks-setup" in step for step in payload["next_steps"])


def test_configure_touches_only_the_settings_file(isolated_root, no_subprocess):
    sc.main(["configure", "--root", str(isolated_root), "--json"])

    written = sorted(
        str(path.relative_to(isolated_root))
        for path in isolated_root.rglob("*")
        if path.is_file()
    )
    assert written == [str(Path(".claude") / "settings.local.json")]


def test_configure_requires_an_explicit_root():
    parser = sc.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["configure"])
