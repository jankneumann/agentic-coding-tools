"""Production sandbox activation tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shared.sandbox_activation import (
    SandboxActivation,
    SandboxActivationError,
    SandboxActivationContext,
    SandboxDegradation,
    activate_sandbox,
    resolve_activation_context,
    resolve_requested_isolation,
)
from shared.sandbox_profile import PreflightResult, RuntimePaths, SandboxProfileError

import pytest


def test_standalone_context_resolves_exact_lane_mode_override(tmp_path: Path) -> None:
    agents = tmp_path / "agents.yaml"
    agents.write_text(
        """
agents:
  codex-local:
    type: codex
    location: local
    isolation: worktree
    policy_vendor: openai
    catalog_vendor: codex
    endpoint_kind: vendor-cli
    cli:
      command: codex
      api_key_env: OPENAI_API_KEY
      state_env_keys: [CODEX_HOME]
      dispatch_modes:
        review:
          args: []
          isolation: sandbox
          enforcement_scope: execution
          write_capable: false
""",
        encoding="utf-8",
    )

    context = resolve_activation_context(
        agent_id="codex-local",
        dispatch_mode="review",
        model="gpt-5.6-sol",
        worktree_root=tmp_path,
        agents_path=agents,
    )

    assert context.isolation == "sandbox"
    assert context.agent_id == "codex-local"
    assert context.api_key_env == "OPENAI_API_KEY"
    assert context.state_env_keys == ("CODEX_HOME",)
    assert context.write_capable is False


@pytest.mark.parametrize(
    ("extra_lane", "state_keys"),
    [
        ("    base_url: https://user:secret@example.test/v1\n", "[CODEX_HOME]"),
        ("    base_url: https://example.test/v1#secret\n", "[CODEX_HOME]"),
        ("    base_url: https://EXAMPLE.test:443/v1\n", "[CODEX_HOME]"),
        ("    base_url: https://example.test/v1/../v1\n", "[CODEX_HOME]"),
        ("    endpoint_kind: totally-unknown\n", "[CODEX_HOME]"),
        ("", "[CODEX_HOME, CODEX_HOME]"),
        ("", "[OPENAI_API_KEY]"),
    ],
)
def test_standalone_context_rejects_noncanonical_lane_configuration(
    tmp_path: Path, extra_lane: str, state_keys: str,
) -> None:
    agents = tmp_path / "agents.yaml"
    endpoint_line = (
        "    endpoint_kind: vendor-cli\n"
        if "endpoint_kind:" not in extra_lane
        else ""
    )
    agents.write_text(
        "agents:\n"
        "  codex-local:\n"
        "    type: codex\n"
        "    location: local\n"
        "    isolation: sandbox\n"
        f"{endpoint_line}"
        f"{extra_lane}"
        "    cli:\n"
        "      command: codex\n"
        "      api_key_env: OPENAI_API_KEY\n"
        f"      state_env_keys: {state_keys}\n"
        "      dispatch_modes:\n"
        "        review:\n"
        "          args: []\n"
        "          enforcement_scope: execution\n"
        "          write_capable: false\n",
        encoding="utf-8",
    )

    with pytest.raises(SandboxActivationError, match="sandbox_(endpoint|state_keys)_invalid"):
        resolve_activation_context(
            agent_id="codex-local",
            dispatch_mode="review",
            model="gpt-5.6-sol",
            worktree_root=tmp_path,
            agents_path=agents,
        )


@pytest.mark.parametrize(
    ("field", "yaml_value", "reason"),
    [
        ("type", "[codex]", "sandbox_vendor_type_invalid"),
        ("policy_vendor", "[openai]", "sandbox_policy_vendor_invalid"),
        ("catalog_vendor", "''", "sandbox_catalog_vendor_invalid"),
    ],
)
def test_standalone_context_rejects_invalid_consumed_vendor_projection(
    tmp_path: Path, field: str, yaml_value: str, reason: str,
) -> None:
    agents = tmp_path / "agents.yaml"
    fields = {
        "type": "codex",
        "policy_vendor": "openai",
        "catalog_vendor": "codex",
    }
    fields[field] = yaml_value
    agents.write_text(
        "agents:\n"
        "  codex-local:\n"
        f"    type: {fields['type']}\n"
        "    location: local\n"
        "    isolation: sandbox\n"
        f"    policy_vendor: {fields['policy_vendor']}\n"
        f"    catalog_vendor: {fields['catalog_vendor']}\n"
        "    endpoint_kind: vendor-cli\n"
        "    cli:\n"
        "      command: codex\n"
        "      api_key_env: OPENAI_API_KEY\n"
        "      state_env_keys: [CODEX_HOME]\n"
        "      dispatch_modes:\n"
        "        review:\n"
        "          args: []\n"
        "          enforcement_scope: execution\n"
        "          write_capable: false\n",
        encoding="utf-8",
    )

    with pytest.raises(SandboxActivationError, match=reason):
        resolve_activation_context(
            agent_id="codex-local",
            dispatch_mode="review",
            model="gpt-5.6-sol",
            worktree_root=tmp_path,
            agents_path=agents,
        )


def _write_discovery_agents(path: Path, *, isolation: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
agents:
  codex-local:
    type: codex
    location: local
    isolation: {isolation}
    endpoint_kind: vendor-cli
    cli:
      command: codex
      api_key_env: OPENAI_API_KEY
      state_env_keys: []
      dispatch_modes:
        alternative:
          args: []
          enforcement_scope: execution
          write_capable: true
""",
        encoding="utf-8",
    )


def test_agents_yaml_is_discovered_upward_from_worktree_not_module_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTS_YAML", raising=False)
    repo = tmp_path / "consumer-repo"
    nested_worktree = repo / ".git-worktrees" / "change" / "agent"
    nested_worktree.mkdir(parents=True)
    _write_discovery_agents(repo / "agent-coordinator" / "agents.yaml", isolation="sandbox")

    isolation = resolve_requested_isolation(
        "codex-local", "alternative", worktree_root=nested_worktree,
    )

    assert isolation == "sandbox"


def test_explicit_agents_path_precedes_environment_and_upward_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    discovered = repo / "agent-coordinator" / "agents.yaml"
    configured = tmp_path / "configured.yaml"
    explicit = tmp_path / "explicit.yaml"
    _write_discovery_agents(discovered, isolation="none")
    _write_discovery_agents(configured, isolation="worktree")
    _write_discovery_agents(explicit, isolation="sandbox")
    monkeypatch.setenv("AGENTS_YAML", str(configured))

    assert resolve_requested_isolation(
        "codex-local", "alternative", worktree_root=repo,
    ) == "worktree"
    assert resolve_requested_isolation(
        "codex-local", "alternative", worktree_root=repo, agents_path=explicit,
    ) == "sandbox"


def test_router_context_is_authoritative_but_uses_exact_lane_credentials(
    tmp_path: Path,
) -> None:
    agents = tmp_path / "agents.yaml"
    agents.write_text(
        """
agents:
  codex-local:
    type: codex
    location: local
    isolation: worktree
    endpoint_kind: vendor-cli
    cli:
      command: codex
      api_key_env: OPENAI_API_KEY
      state_env_keys: []
      dispatch_modes:
        alternative:
          args: []
          enforcement_scope: execution
          write_capable: true
""",
        encoding="utf-8",
    )
    routing = {
        "schema_version": 1,
        "decision_id": "decision-1",
        "item_id": "dg-07",
        "phase": "implementing",
        "attempt": 1,
        "dispatch_work_id": "work-1",
        "assignment": {
            "agent_id": "codex-local",
            "vendor_type": "codex",
            "location": "local",
            "isolation": "sandbox",
            "dispatch_mode": "alternative",
            "model": "gpt-5.6-sol",
            "endpoint_kind": "vendor-cli",
            "enforcement_scope": "execution",
            "write_capable": True,
            "base_url": None,
        },
    }
    digest = hashlib.sha256(
        json.dumps(routing, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    execution_context = {
        "schema_version": 1,
        "routing_context": routing,
        "workspace_content_digest": None,
        "decision_id": "decision-1",
        "item_id": "dg-07",
        "phase": "implementing",
        "attempt": 1,
        "dispatch_work_id": "work-1",
        "routing_context_digest": digest,
        "agent_id": "codex-local",
        "vendor_type": "codex",
        "policy_vendor": None,
        "catalog_vendor": None,
        "assignment_location": "local",
        "execution_location": "local",
        "dispatch_mode": "alternative",
        "isolation": "sandbox",
        "model": "gpt-5.6-sol",
        "base_url": None,
        "endpoint_kind": "vendor-cli",
        "enforcement_scope": "execution",
        "write_capable": True,
        "source": "router",
        "worktree_root": str(tmp_path),
    }

    context = resolve_activation_context(
        agent_id="codex-local",
        dispatch_mode="alternative",
        model="gpt-5.6-sol",
        worktree_root=tmp_path,
        execution_context=execution_context,
        agents_path=agents,
    )

    assert isinstance(context, SandboxActivationContext)
    assert context.source == "router"
    assert context.routing_context_digest == digest
    assert context.api_key_env == "OPENAI_API_KEY"


def test_router_context_recomputes_digest_and_rejects_root_mismatch(
    tmp_path: Path,
) -> None:
    agents = tmp_path / "agents.yaml"
    agents.write_text(
        """
agents:
  codex-local:
    type: codex
    location: local
    isolation: worktree
    endpoint_kind: vendor-cli
    cli:
      command: codex
      api_key_env: OPENAI_API_KEY
      state_env_keys: []
      dispatch_modes:
        alternative:
          args: []
          enforcement_scope: execution
          write_capable: true
""",
        encoding="utf-8",
    )
    routing = {
        "schema_version": 1,
        "decision_id": "decision-1",
        "item_id": "dg-07",
        "phase": "implementing",
        "attempt": 1,
        "dispatch_work_id": "work-1",
        "assignment": {
            "agent_id": "codex-local",
            "vendor_type": "codex",
            "policy_vendor": None,
            "catalog_vendor": None,
            "location": "local",
            "isolation": "sandbox",
            "dispatch_mode": "alternative",
            "model": "gpt-5.6-sol",
            "endpoint_kind": "vendor-cli",
            "base_url": None,
            "enforcement_scope": "execution",
            "write_capable": True,
        },
    }
    context = {
        "schema_version": 1,
        "routing_context": routing,
        "workspace_content_digest": None,
        "decision_id": "decision-1",
        "item_id": "dg-07",
        "phase": "implementing",
        "attempt": 1,
        "dispatch_work_id": "work-1",
        "routing_context_digest": "0" * 64,
        "agent_id": "codex-local",
        "vendor_type": "codex",
        "policy_vendor": None,
        "catalog_vendor": None,
        "assignment_location": "local",
        "execution_location": "local",
        "dispatch_mode": "alternative",
        "isolation": "sandbox",
        "model": "gpt-5.6-sol",
        "base_url": None,
        "endpoint_kind": "vendor-cli",
        "enforcement_scope": "execution",
        "write_capable": True,
        "source": "router",
        "worktree_root": str(tmp_path / "routed-root"),
    }

    with pytest.raises(SandboxActivationError, match="digest_mismatch"):
        resolve_activation_context(
            agent_id="codex-local",
            dispatch_mode="alternative",
            model="gpt-5.6-sol",
            worktree_root=tmp_path / "other-root",
            execution_context=context,
            agents_path=agents,
        )

    context["routing_context_digest"] = hashlib.sha256(
        json.dumps(routing, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(SandboxActivationError, match="worktree_root_mismatch"):
        resolve_activation_context(
            agent_id="codex-local",
            dispatch_mode="alternative",
            model="gpt-5.6-sol",
            worktree_root=tmp_path / "other-root",
            execution_context=context,
            agents_path=agents,
        )


def _activation_context(tmp_path: Path) -> SandboxActivationContext:
    return SandboxActivationContext(
        agent_id="codex-local",
        vendor_type="codex",
        dispatch_mode="alternative",
        model="gpt-5.6-sol",
        isolation="sandbox",
        policy_vendor="openai",
        catalog_vendor="codex",
        assignment_location="local",
        endpoint_kind="vendor-cli",
        base_url=None,
        enforcement_scope="execution",
        write_capable=True,
        source="agents_yaml",
        worktree_root=tmp_path / "repo" / "worktree",
        api_key_env="OPENAI_API_KEY",
        state_env_keys=(),
    )


def _runtime(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths(
        node=Path("/bin/true"),
        entrypoint=Path("/bin/true"),
        runtime_dir=tmp_path / "runtime",
        primary_checkout=tmp_path / "repo",
        common_git_dir=tmp_path / "repo" / ".git",
        version="0.0.77",
        bwrap=None,
        socat=None,
        rg=None,
    )


def test_activation_constructs_exact_agent_launch_runtime_and_audit_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _activation_context(tmp_path)
    context.worktree_root.mkdir(parents=True)

    def git_path(_cwd: Path, flag: str) -> Path:
        if flag == "--git-common-dir":
            return tmp_path / "repo" / ".git"
        return context.worktree_root

    monkeypatch.setattr("shared.sandbox_activation._git_path", git_path)
    policy = {
        "schema_version": 1,
        "agent_id": "codex-local",
        "policy_revision": 3,
        "policy_digest": "a" * 64,
        "rules": [],
    }

    activation = activate_sandbox(
        context=context,
        vendor_executable=Path("/bin/true"),
        env={"OPENAI_API_KEY": "secret"},
        policy_fetcher=lambda agent_id: policy,
        runtime_discoverer=lambda _cwd: _runtime(tmp_path),
        runtime_preflight=lambda _runtime: PreflightResult(True, "passed"),
        audit_state_root=tmp_path / "audit",
    )

    assert isinstance(activation, SandboxActivation)
    assert activation.launch.agent_id == "codex-local"
    assert activation.launch.policy is policy
    assert activation.audit_event["agent_id"] == "codex-local"
    assert activation.audit_event["requested_isolation"] == "sandbox"


@pytest.mark.parametrize(
    ("reason", "status"),
    [
        ("runtime_lock_missing", "runtime_missing"),
        ("runtime_version_or_integrity_mismatch", "runtime_incompatible"),
    ],
)
def test_only_permitted_runtime_discovery_failures_degrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    status: str,
) -> None:
    context = _activation_context(tmp_path)
    context.worktree_root.mkdir(parents=True)
    monkeypatch.setattr(
        "shared.sandbox_activation._git_path",
        lambda _cwd, flag: (
            tmp_path / "repo" / ".git"
            if flag == "--git-common-dir"
            else context.worktree_root
        ),
    )

    def fail(_cwd: Path) -> RuntimePaths:
        raise SandboxProfileError(reason, fail_open=True)

    result = activate_sandbox(
        context=context,
        vendor_executable=Path("/bin/true"),
        env={"OPENAI_API_KEY": "secret"},
        runtime_discoverer=fail,
        audit_state_root=tmp_path / "audit",
    )

    assert isinstance(result, SandboxDegradation)
    assert result.reason == status
    assert result.audit_event["preflight_status"] == status
    assert result.audit_event["degradation_reason"] == status


def test_preflight_degradation_uses_typed_event_reason_without_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _activation_context(tmp_path)
    context.worktree_root.mkdir(parents=True)
    monkeypatch.setattr(
        "shared.sandbox_activation._git_path",
        lambda _cwd, flag: (
            tmp_path / "repo" / ".git"
            if flag == "--git-common-dir"
            else context.worktree_root
        ),
    )
    accepted = {
        "unsupported_platform", "runtime_missing", "runtime_incompatible",
        "capability_failed", "policy_unavailable", "policy_invalid",
        "authorization_failed",
    }
    sent = []

    def sender(event):
        assert event["degradation_reason"] in accepted
        assert event["degradation_reason"] == event["preflight_status"]
        sent.append(event)
        return 201, {"success": True}

    result = activate_sandbox(
        context=context,
        vendor_executable=Path("/bin/true"),
        env={"OPENAI_API_KEY": "secret"},
        event_sender=sender,
        runtime_discoverer=lambda _cwd: _runtime(tmp_path),
        runtime_preflight=lambda _runtime: PreflightResult(
            False, "capability_failed", ("bwrap:probe failed",),
        ),
        audit_state_root=tmp_path / "audit",
    )

    assert isinstance(result, SandboxDegradation)
    assert result.reason == "capability_failed"
    assert result.audit_event["degradation_reason"] == "capability_failed"
    result.audit_port.record(result.audit_event)
    assert sent == [result.audit_event]


def test_unsafe_runtime_discovery_failure_does_not_degrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _activation_context(tmp_path)
    context.worktree_root.mkdir(parents=True)
    monkeypatch.setattr(
        "shared.sandbox_activation._git_path",
        lambda _cwd, flag: (
            tmp_path / "repo" / ".git"
            if flag == "--git-common-dir"
            else context.worktree_root
        ),
    )

    def fail(_cwd: Path) -> RuntimePaths:
        raise SandboxProfileError("git_runtime_discovery_failed", fail_open=True)

    with pytest.raises(SandboxActivationError, match="git_runtime_discovery_failed"):
        activate_sandbox(
            context=context,
            vendor_executable=Path("/bin/true"),
            env={"OPENAI_API_KEY": "secret"},
            runtime_discoverer=fail,
            audit_state_root=tmp_path / "audit",
        )
