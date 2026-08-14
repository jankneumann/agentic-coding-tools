"""Tests for scripts/setup_cloud.py — registry-derived roster (design D7).

The script used to carry its own hand-maintained ``AGENTS`` roster, which
drifted from ``agents.yaml`` every time a vendor harness was added. These
tests pin the derivation instead:

- the roster equals ``load_agents_config()`` names, in registry order
- one ``--<agent-name>-key`` CLI flag per registry agent, derived mechanically
- the identities map has the ``{key: {agent_id, agent_type}}`` shape
- ``.env.cloud`` emits an alias per CLI-bearing agent command
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.agents_config import load_agents_config

# Load the script as a module (it's in scripts/, not src/, so it's not on sys.path)
_SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "setup_cloud.py"
_spec = importlib.util.spec_from_file_location("setup_cloud", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
setup_cloud = importlib.util.module_from_spec(_spec)
sys.modules["setup_cloud"] = setup_cloud
_spec.loader.exec_module(setup_cloud)


# =============================================================================
# Fixtures
# =============================================================================


CUSTOM_REGISTRY = """
agents:
  zeta-local:
    type: zeta
    profile: zeta_local
    trust_level: 3
    transport: mcp
    capabilities: [lock]
    description: Zeta local worker
    cli:
      command: zt
      dispatch_modes:
        review:
          args: ["--print"]
      model_flag: "--model"
  omega-remote:
    type: omega
    profile: omega_remote
    trust_level: 2
    transport: http
    capabilities: [lock]
    description: Omega remote agent without a CLI
"""


@pytest.fixture
def custom_registry(tmp_path: Path) -> Path:
    """A controlled two-agent registry: one CLI-bearing, one not."""
    path = tmp_path / "agents.yaml"
    path.write_text(CUSTOM_REGISTRY)
    return path


@pytest.fixture
def empty_secrets(tmp_path: Path) -> Path:
    """A non-existent secrets file so ``${VAR}`` interpolation is a no-op."""
    return tmp_path / "no-secrets.yaml"


def _keys_for(roster: list[object]) -> dict[str, str]:
    """Deterministic fake key per roster slot (no secrets module needed)."""
    return {slot.key_flag: f"key-{slot.name}" for slot in roster}  # type: ignore[attr-defined]


# =============================================================================
# Roster derivation
# =============================================================================


def test_roster_equals_registry_names() -> None:
    """The roster is exactly agents.yaml, in registry order."""
    expected = [agent.name for agent in load_agents_config()]
    assert [slot.name for slot in setup_cloud.load_roster()] == expected


def test_roster_carries_registry_types() -> None:
    expected = {agent.name: agent.type for agent in load_agents_config()}
    assert {slot.name: slot.type for slot in setup_cloud.load_roster()} == expected


def test_no_hardcoded_agents_list() -> None:
    """Regression guard: the hand-maintained roster must stay deleted."""
    assert not hasattr(setup_cloud, "AGENTS")
    assert "alias_map" not in _SCRIPT_PATH.read_text()


def test_docstring_records_pca03_retirement() -> None:
    doc = setup_cloud.__doc__ or ""
    assert "pca-03" in doc


def test_roster_from_custom_registry(custom_registry: Path, empty_secrets: Path) -> None:
    roster = setup_cloud.load_roster(custom_registry, secrets_path=empty_secrets)
    assert [slot.name for slot in roster] == ["zeta-local", "omega-remote"]
    assert [slot.command for slot in roster] == ["zt", None]


# =============================================================================
# Flag derivation
# =============================================================================


def test_key_flag_derivation_is_mechanical() -> None:
    assert setup_cloud.key_flag_for("antigravity-local") == "antigravity_local_key"
    assert setup_cloud.cli_flag_for("antigravity-local") == "--antigravity-local-key"


def test_parser_has_a_flag_per_registry_agent() -> None:
    roster = setup_cloud.load_roster()
    parser = setup_cloud.build_parser(roster)
    args = parser.parse_args(["--domain", "coord.example.invalid"])
    for slot in roster:
        assert hasattr(args, slot.key_flag), f"missing flag for {slot.name}"
        assert getattr(args, slot.key_flag) is None


def test_parser_accepts_supplied_keys() -> None:
    roster = setup_cloud.load_roster()
    parser = setup_cloud.build_parser(roster)
    args = parser.parse_args(
        ["--domain", "coord.example.invalid", "--claude-local-key", "supplied-key"]
    )
    assert args.claude_local_key == "supplied-key"


def test_parser_keeps_operator_flags() -> None:
    parser = setup_cloud.build_parser(setup_cloud.load_roster())
    args = parser.parse_args(
        [
            "--domain", "coord.example.invalid",
            "--railway",
            "--railway-service", "api",
            "--verify",
            "--output", "/dev/null",
        ]
    )
    assert args.railway is True
    assert args.railway_service == "api"
    assert args.verify is True
    assert args.output == "/dev/null"


def test_custom_registry_flags_are_generated(
    custom_registry: Path, empty_secrets: Path
) -> None:
    """A brand-new registry agent gets a flag with no code change."""
    roster = setup_cloud.load_roster(custom_registry, secrets_path=empty_secrets)
    parser = setup_cloud.build_parser(roster)
    args = parser.parse_args(
        ["--domain", "x.invalid", "--zeta-local-key", "zk", "--omega-remote-key", "ok"]
    )
    assert args.zeta_local_key == "zk"
    assert args.omega_remote_key == "ok"


# =============================================================================
# Identities
# =============================================================================


def test_identities_shape_matches_registry() -> None:
    roster = setup_cloud.load_roster()
    keys = _keys_for(roster)
    identities = setup_cloud.build_identities(roster, keys)

    assert len(identities) == len(roster)
    for slot in roster:
        entry = identities[keys[slot.key_flag]]
        assert entry == {"agent_id": slot.name, "agent_type": slot.type}


def test_identities_json_is_serializable() -> None:
    roster = setup_cloud.load_roster()
    identities = setup_cloud.build_identities(roster, _keys_for(roster))
    round_tripped = json.loads(json.dumps(identities, separators=(",", ":")))
    assert round_tripped == identities


def test_identities_skip_agents_without_keys() -> None:
    roster = setup_cloud.load_roster()
    keys = _keys_for(roster)
    dropped = roster[0]
    keys[dropped.key_flag] = ""
    identities = setup_cloud.build_identities(roster, keys)
    assert all(entry["agent_id"] != dropped.name for entry in identities.values())


# =============================================================================
# .env.cloud generation
# =============================================================================


def test_default_key_slot_is_local_claude_code() -> None:
    roster = setup_cloud.load_roster()
    default = setup_cloud.default_key_slot(roster)
    assert default is not None
    assert default.type == "claude_code"
    assert default.transport == "mcp"


def test_env_file_exports_shared_settings(tmp_path: Path) -> None:
    roster = setup_cloud.load_roster()
    keys = _keys_for(roster)
    out = tmp_path / ".env.cloud"
    setup_cloud.write_env_file("coord.example.invalid", keys, out, roster)
    text = out.read_text()

    assert 'export COORDINATION_API_URL="https://coord.example.invalid"' in text
    assert 'export COORDINATION_ALLOWED_HOSTS="coord.example.invalid"' in text
    assert "# export CF_ACCESS_CLIENT_ID=" in text

    default = setup_cloud.default_key_slot(roster)
    assert default is not None
    assert f'export COORDINATION_API_KEY="{keys[default.key_flag]}"' in text


def test_env_file_emits_alias_per_cli_command(tmp_path: Path) -> None:
    roster = setup_cloud.load_roster()
    keys = _keys_for(roster)
    out = tmp_path / ".env.cloud"
    setup_cloud.write_env_file("coord.example.invalid", keys, out, roster)
    text = out.read_text()

    aliases = setup_cloud.derive_aliases(roster)
    assert aliases, "registry declares CLI agents; aliases must be emitted"

    # One alias per distinct CLI command, no shadowing duplicates.
    names = [alias.name for alias in aliases]
    assert len(names) == len(set(names))
    assert {alias.slot.command for alias in aliases} == {
        agent.cli.command for agent in load_agents_config() if agent.cli
    }

    for alias in aliases:
        key = keys[alias.slot.key_flag]
        assert f"alias {alias.name}='COORDINATION_API_KEY=\"{key}\" {alias.slot.command}'" in text


def test_aliases_prefer_local_agents(tmp_path: Path) -> None:
    """`claude` is wrapped with the local agent's key, not the remote one."""
    roster = setup_cloud.load_roster()
    by_command = {alias.slot.command: alias.slot for alias in setup_cloud.derive_aliases(roster)}
    assert by_command["claude"].name == "claude-local"
    assert by_command["codex"].name == "codex-local"


def test_aliases_only_for_cli_bearing_agents(
    custom_registry: Path, empty_secrets: Path, tmp_path: Path
) -> None:
    roster = setup_cloud.load_roster(custom_registry, secrets_path=empty_secrets)
    aliases = setup_cloud.derive_aliases(roster)
    assert [(alias.name, alias.slot.name) for alias in aliases] == [("czt", "zeta-local")]

    out = tmp_path / ".env.cloud"
    setup_cloud.write_env_file("x.invalid", _keys_for(roster), out, roster)
    text = out.read_text()
    assert "alias czt=" in text
    assert "omega" not in text


def test_env_file_omits_aliases_for_missing_keys(tmp_path: Path) -> None:
    roster = setup_cloud.load_roster()
    keys = _keys_for(roster)
    aliases = setup_cloud.derive_aliases(roster)
    keys[aliases[0].slot.key_flag] = ""
    out = tmp_path / ".env.cloud"
    setup_cloud.write_env_file("coord.example.invalid", keys, out, roster)
    assert f"alias {aliases[0].name}=" not in out.read_text()


# =============================================================================
# End-to-end generation path (no network, no Railway)
# =============================================================================


def test_main_generates_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / ".env.cloud"
    monkeypatch.setattr(
        sys,
        "argv",
        ["setup_cloud.py", "--domain", "https://coord.example.invalid/", "--output", str(out)],
    )
    setup_cloud.main()
    captured = capsys.readouterr().out

    text = out.read_text()
    assert 'export COORDINATION_API_URL="https://coord.example.invalid"' in text

    roster = setup_cloud.load_roster()
    # Summary table lists every registry agent, and the printed identities map
    # covers the full roster.
    for slot in roster:
        assert slot.name in captured
    identities_line = next(
        line for line in captured.splitlines()
        if "COORDINATION_API_KEY_IDENTITIES=" in line
    )
    identities = json.loads(identities_line.split("=", 1)[1])
    assert sorted(entry["agent_id"] for entry in identities.values()) == sorted(
        slot.name for slot in roster
    )
