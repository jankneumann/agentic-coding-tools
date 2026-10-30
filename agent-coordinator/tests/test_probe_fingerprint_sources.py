"""Every real lane fingerprints identically across the three config sources (task 6.1).

Sources: the raw ``agents.yaml`` cli block, ``get_dispatch_configs()`` (defaults
filled in), and the dispatcher's own loader into its mirror ``CliConfig`` — the
reader ``discover_reviewers`` fingerprints.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from src.agents_config import (
    get_dispatch_configs,
    load_agents_config,
    reset_agents_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_YAML = REPO_ROOT / "agent-coordinator" / "agents.yaml"
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"


@pytest.fixture(scope="module")
def modules():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import review_dispatcher
        import vendor_probe
    finally:
        sys.path.remove(str(SCRIPTS))
    return review_dispatcher, vendor_probe


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    reset_agents_config()
    secrets = tmp_path_factory.mktemp("sec") / ".secrets.yaml"
    secrets.write_text("{}")
    raw = yaml.safe_load(AGENTS_YAML.read_text())["agents"]
    entries = load_agents_config(AGENTS_YAML, secrets_path=secrets)
    payload = get_dispatch_configs(entries)["agents"]
    return raw, {a["agent_id"]: a for a in payload}


def _raw_lanes(raw):
    return {aid: a["cli"] for aid, a in raw.items() if a.get("cli")}


def test_real_agents_yaml_declares_cli_lanes(sources):
    raw, _ = sources
    assert len(_raw_lanes(raw)) >= 5


def test_fingerprint_and_required_flags_match_across_sources(modules, sources):
    rd, vp = modules
    raw, dispatch = sources
    lanes = _raw_lanes(raw)

    # Mirror loader fed by the coordinator payload, and by raw yaml dicts.
    from_payload = rd.ReviewOrchestrator.from_config_dict({"agents": list(dispatch.values())})
    from_raw = rd.ReviewOrchestrator.from_config_dict(
        {
            "agents": [
                {"agent_id": aid, "type": raw[aid].get("type", "x"), "cli": cli}
                for aid, cli in lanes.items()
            ]
        }
    )

    for agent_id, cli in lanes.items():
        views = {
            "raw": cli,
            "dispatch-configs": dispatch[agent_id]["cli"],
            "mirror(payload)": rd._cli_probe_view(from_payload.adapters[agent_id].cli_config),
            "mirror(raw)": rd._cli_probe_view(from_raw.adapters[agent_id].cli_config),
        }
        fingerprints = {name: vp.lane_fingerprint(v) for name, v in views.items()}
        assert len(set(fingerprints.values())) == 1, (agent_id, fingerprints)
        for mode in cli["dispatch_modes"]:
            flags = {name: vp.mode_required_flags(v, mode) for name, v in views.items()}
            assert all(f == flags["raw"] for f in flags.values()), (agent_id, mode, flags)
            helps = {name: vp.mode_help_argv(v, mode) for name, v in views.items()}
            assert all(h == helps["raw"] for h in helps.values()), (agent_id, mode, helps)


def test_declared_probe_blocks_survive_every_source(modules, sources):
    rd, _ = modules
    raw, dispatch = sources
    from_payload = rd.ReviewOrchestrator.from_config_dict({"agents": list(dispatch.values())})
    for agent_id, cli in _raw_lanes(raw).items():
        assert dispatch[agent_id]["cli"].get("probe") == cli.get("probe")
        assert from_payload.adapters[agent_id].cli_config.probe == cli.get("probe")
