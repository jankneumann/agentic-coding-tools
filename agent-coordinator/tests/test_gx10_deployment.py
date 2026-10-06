"""The GX-10 deployment's invariants, pinned.

Every assertion here corresponds to a specific failure the analyzer hit on this
host. They are cheap to check and expensive to rediscover: see the GX-10 case
study in the analyzer repo for what each one cost.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "gx10"
COMPOSE = DEPLOY / "docker-compose.coordinator.yml"
UNIT = DEPLOY / "systemd" / "aca-gx10-coordinator.service"
SECRETS_UNIT = DEPLOY / "systemd" / "aca-gx10-coordinator-secrets.service"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_it_is_a_separate_compose_project(compose: dict) -> None:
    """Sharing the analyzer's project name would let one `down` sweep both."""
    assert compose["name"] == "aca-gx10-coord"


def test_the_analyzer_owns_the_shared_networks(compose: dict) -> None:
    """Declaring them external joins them; omitting it creates a second,
    identically-named set and the coordinator comes up wired to nothing."""
    for name, expected in (("application", "aca-gx10_application"), ("egress", "aca-gx10_egress")):
        net = compose["networks"][name]
        assert net["external"] is True, name
        assert net["name"] == expected, name


def test_the_private_network_subnet_is_pinned(compose: dict) -> None:
    """netavark allocates from 10.89.0.0/16 and the analyzer holds .0, .1, .2.
    Letting podman choose eventually collides with a live network."""
    ipam = compose["networks"]["coord"]["ipam"]["config"][0]
    assert ipam["subnet"] == "10.89.3.0/24"
    assert compose["networks"]["coord"]["internal"] is True


def test_nothing_is_published_to_the_host(compose: dict) -> None:
    """The tunnel is the only inbound path; a published port is a second one."""
    for name, service in compose["services"].items():
        assert not service.get("ports"), f"{name} publishes a port"


def test_every_image_is_pinned_or_fails_closed(compose: dict) -> None:
    """An unpinned tag means the deployed artifact is decided at pull time."""
    for name, service in compose["services"].items():
        image = service["image"]
        assert image.startswith("${GX10_"), f"{name} does not come from a pinned variable"
        assert ":?" in image, f"{name} does not fail closed when the pin is unset"


def test_every_container_drops_all_capabilities(compose: dict) -> None:
    for name, service in compose["services"].items():
        assert service["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in service["security_opt"], name


def test_only_the_database_is_writable_at_the_root(compose: dict) -> None:
    """A read-only root is what makes the writable paths worth auditing."""
    assert compose["services"]["coordinator-postgres"]["read_only"] is False
    assert compose["services"]["coordinator-api"]["read_only"] is True
    assert compose["services"]["cloudflared"]["read_only"] is True


def test_the_api_workdir_survives_a_restart(compose: dict) -> None:
    """Saved views and audit rows are written there; a tmpfs would lose them."""
    volumes = compose["services"]["coordinator-api"]["volumes"]
    assert any("/srv/aca/coordinator-workdir:/app/workdir" in v for v in volumes)


def test_the_api_runs_as_the_pinned_uid(compose: dict) -> None:
    """`useradd --system` picks a varying id; the ownership preflight needs a
    fixed one, and the Dockerfile must agree with the compose file."""
    assert compose["services"]["coordinator-api"]["user"] == "10001:10001"
    dockerfile = (ROOT / "agent-coordinator" / "Dockerfile").read_text(encoding="utf-8")
    assert "--uid 10001" in dockerfile
    assert "--gid 10001" in dockerfile


def test_every_locally_called_host_bypasses_the_proxy(compose: dict) -> None:
    """HTTP_PROXY is set for egress, and httpx honours it. A host missing here
    has its request handed to Squid, which denies internal destinations -- so a
    purely local call fails on our own SSRF rule."""
    env = compose["services"]["coordinator-api"]["environment"]
    for key in ("NO_PROXY", "no_proxy"):
        bypass = set(env[key].split(","))
        assert {"coordinator-postgres", "langfuse-web"} <= bypass, key


def test_traces_go_to_the_shared_langfuse_under_its_own_identity(compose: dict) -> None:
    env = compose["services"]["coordinator-api"]["environment"]
    assert env["LANGFUSE_HOST"] == "http://langfuse-web:3000"
    assert env["OTEL_EXPORTER_OTLP_ENDPOINT"].startswith("http://langfuse-web:3000/")
    assert env["OTEL_SERVICE_NAME"] == "aca-gx10-coordinator"


def test_the_coordinator_never_reads_openbao_directly(compose: dict) -> None:
    """Secrets are rendered to an env file, so a compromised API container
    holds its own secrets and no vault token."""
    for name, service in compose["services"].items():
        env = service.get("environment") or {}
        assert not any(k.startswith("BAO_") or k.startswith("VAULT_") for k in env), name
        assert "stateful" not in (service.get("networks") or {}), (
            f"{name} can reach OpenBao's network directly"
        )


def test_the_tunnel_is_isolated_from_the_data_network(compose: dict) -> None:
    """It is the one container holding a connection that bypasses Squid, so it
    gets no route to the databases."""
    networks = set(compose["services"]["cloudflared"]["networks"])
    assert networks == {"coord", "egress"}


def test_the_unit_stops_with_the_analyzer_it_depends_on() -> None:
    """Without PartOf=, stopping the analyzer removes the networks from under a
    still-running coordinator, which reads as a coordinator bug."""
    unit = UNIT.read_text(encoding="utf-8")
    assert "Requires=aca-gx10.service" in unit
    assert "After=aca-gx10.service" in unit
    assert "PartOf=aca-gx10.service" in unit


def test_the_unit_does_not_let_systemd_kill_the_containers() -> None:
    """A failed oneshot ExecStart skips ExecStop; the default KillMode then
    SIGTERMs every conmon in the cgroup and waits out TimeoutStopSec."""
    unit = UNIT.read_text(encoding="utf-8")
    assert "KillMode=process" in unit
    assert "Type=oneshot" in unit
    assert "RemainAfterExit=yes" in unit


def test_the_unit_refuses_to_run_a_stale_installed_copy() -> None:
    """Three rounds of analyzer fixes had no effect against a stale unit in
    /etc/systemd/system while the repo copy was correct."""
    unit = UNIT.read_text(encoding="utf-8")
    assert "check_unit_current.sh" in unit


def _directives(path: Path) -> dict[str, str]:
    """Parse `Key=value` lines, ignoring comments.

    Matching raw text instead caught this file's own explanatory comment about
    the directive it was checking for -- the test passed judgement on prose.
    """
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")):
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def test_sandboxing_does_not_hide_the_interpreter() -> None:
    """ProtectHome=yes hid an interpreter under /root and took down three
    analyzer units with 203/EXEC."""
    for path in (UNIT, SECRETS_UNIT):
        directives = _directives(path)
        assert directives.get("ProtectHome") != "yes", path.name


def test_approle_credentials_arrive_as_systemd_credentials() -> None:
    """Role and secret id must not reach the environment or process table."""
    unit = SECRETS_UNIT.read_text(encoding="utf-8")
    assert "LoadCredential=coord-role-id:" in unit
    assert "LoadCredential=coord-secret-id:" in unit


def test_the_renderer_refuses_a_tunnel_config_exposing_a_secret_store() -> None:
    """On this host OpenBao is the real sealed instance for BOTH projects."""
    script = (DEPLOY / "openbao" / "render-coordinator-secrets.sh").read_text(encoding="utf-8")
    assert "8200" in script
    assert "must never be public" in script
