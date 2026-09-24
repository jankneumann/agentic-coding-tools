"""Controlled real-runtime smoke probe; incapable hosts skip with exact prerequisites."""

import hashlib
import json
import os
import platform as platform_module
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from shared.local_process_backend import LocalProcessRequest, run_local_process
from shared.sandbox_profile import (
    SandboxLaunch,
    SandboxProfileError,
    discover_sandbox_runtime,
    preflight_runtime,
)


def _git_path(repo: Path, flag: str) -> Path:
    raw = subprocess.run(
        ["git", "rev-parse", flag],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    path = Path(raw)
    return (repo / path).resolve() if not path.is_absolute() else path.resolve()


def _configured_vendor_command(repo: Path, agent_id: str) -> Path:
    panel = yaml.safe_load((repo / "agent-coordinator" / "agents.yaml").read_text())
    try:
        command = panel["agents"][agent_id]["cli"]["command"]
    except (KeyError, TypeError) as exc:
        raise AssertionError(f"vendor panel has no CLI command for {agent_id}") from exc
    if not isinstance(command, str) or not command:
        raise AssertionError(f"vendor panel has an invalid CLI command for {agent_id}")
    resolved = shutil.which(command)
    if resolved is None:
        raise AssertionError(f"configured vendor command is unavailable: {command}")
    return Path(resolved).resolve()


def _deny_all_policy() -> dict:
    policy = {
        "schema_version": 1,
        "agent_id": "fixture",
        "default_action": "deny",
        "rules": [],
        "policy_revision": "v1:none:0",
    }
    policy["policy_digest"] = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return policy


def _allow_policy(hostname: str, port: int) -> dict:
    policy = _deny_all_policy()
    policy["rules"] = [{
        "destination_kind": "dns",
        "destination_pattern": hostname,
        "port": port,
        "action": "allow",
        "priority": 1,
        "scope": "agent_profile",
        "policy_id": f"allow-{hostname}-{port}",
    }]
    policy["policy_revision"] = "v1:fixture:1"
    without_digest = {key: value for key, value in policy.items() if key != "policy_digest"}
    policy["policy_digest"] = hashlib.sha256(
        json.dumps(without_digest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return policy


class _RecordingAudit:
    def __init__(self) -> None:
        self.events = []

    def record(self, event):
        self.events.append(event)


def _build_probe_evidence(
    *,
    platform: str,
    executable: str,
    executable_version: str,
    event: dict,
    network_outcomes: dict[str, str],
) -> dict:
    required_digests = (
        "routing_context_digest", "endpoint_digest", "policy_digest", "settings_digest"
    )
    for key in required_digests:
        value = event.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"missing {key}")
    required_network = {"allowed", "denied", "private", "dns_resolved_private"}
    if set(network_outcomes) != required_network or any(
        value != "passed" for value in network_outcomes.values()
    ):
        raise ValueError("controlled network evidence is incomplete")
    if event.get("sandbox_applied") is not True:
        raise ValueError("sandbox was not applied")
    workspace_digest = event.get("workspace_content_digest")
    if workspace_digest is not None and (
        not isinstance(workspace_digest, str) or len(workspace_digest) != 64
    ):
        raise ValueError("invalid workspace_content_digest")
    if event.get("runtime_version") != "0.0.77":
        raise ValueError("unexpected sandbox runtime version")
    if event.get("cleanup_status") != "succeeded":
        raise ValueError("sandbox cleanup did not succeed")
    return {
        "schema_version": 1,
        "platform": platform,
        "executable": executable,
        "executable_version": executable_version,
        "event_id": event["event_id"],
        "sandbox_applied": True,
        "runtime_version": event["runtime_version"],
        "cleanup_status": event["cleanup_status"],
        "workspace_content_digest": workspace_digest,
        **{key: event[key] for key in required_digests},
        "controlled_network": network_outcomes,
    }


def _audit_event(
    policy: dict, repo: Path, *, event_id: str, executable: Path | None = None
) -> dict:
    routing_context = {
        "schema_version": 1,
        "decision_id": "runtime-evidence",
        "item_id": "dg-07",
        "phase": "validating",
        "attempt": 1,
        "dispatch_work_id": "runtime-evidence",
        "assignment": {"agent_id": "ocr-local", "vendor_type": "ocr"},
    }
    endpoint = {"base_url": None, "endpoint_kind": "vendor-cli"}
    def digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    return {
        "schema_version": 1,
        "event_id": event_id,
        "context_source": "router",
        "decision_id": "runtime-evidence",
        "item_id": "dg-07",
        "phase": "validating",
        "attempt": 1,
        "dispatch_work_id": "runtime-evidence",
        "routing_context_digest": digest(routing_context),
        "workspace_content_digest": None,
        "agent_id": "ocr-local",
        "vendor_type": "ocr",
        "policy_vendor": "ocr",
        "catalog_vendor": None,
        "assignment_location": "local",
        "execution_location": "local",
        "enforcement_scope": "execution",
        "write_capable": False,
        "dispatch_mode": "review",
        "model": "python-fixture",
        "endpoint_kind": "vendor-cli",
        "endpoint_digest": digest(endpoint),
        "requested_isolation": "sandbox",
        "backend": "srt",
        "platform": "darwin" if platform_module.system() == "Darwin" else "linux",
        "preflight_status": "passed",
        "policy_revision": policy["policy_revision"],
        "policy_digest": policy["policy_digest"],
        "worktree_root": str(repo),
        "executable_paths": [str((executable or Path(sys.executable)).resolve())],
        "environment_keys": ["VENDOR_TOKEN"],
        "degradation_reason": None,
    }


def test_probe_evidence_requires_complete_digest_and_network_identity() -> None:
    event = {
        "event_id": "runtime-linux",
        "sandbox_applied": True,
        "runtime_version": "0.0.77",
        "cleanup_status": "succeeded",
        "routing_context_digest": "1" * 64,
        "workspace_content_digest": None,
        "endpoint_digest": "4" * 64,
        "policy_digest": "2" * 64,
        "settings_digest": "3" * 64,
    }
    evidence = _build_probe_evidence(
        platform="linux",
        executable="python3",
        executable_version="Python 3.12.12",
        event=event,
        network_outcomes={
            "allowed": "passed", "denied": "passed", "private": "passed",
            "dns_resolved_private": "passed",
        },
    )
    assert evidence["settings_digest"] == "3" * 64
    assert evidence["endpoint_digest"] == "4" * 64
    assert evidence["runtime_version"] == "0.0.77"
    assert evidence["cleanup_status"] == "succeeded"
    assert evidence["controlled_network"]["dns_resolved_private"] == "passed"


def test_configured_vendor_command_is_resolved_from_vendor_panel() -> None:
    repo = Path(__file__).resolve().parents[3]
    command = _configured_vendor_command(repo, "ocr-local")

    assert command.name.startswith("python3")
    assert command.is_absolute()


def test_real_srt_runtime_capability_or_exact_skip() -> None:
    repo = Path(__file__).resolve().parents[3]
    try:
        runtime = discover_sandbox_runtime(repo)
    except SandboxProfileError as exc:
        pytest.skip(f"sandbox runtime unavailable: {exc.reason}")
    result = preflight_runtime(runtime, run_probe=True)
    if not result.ok:
        pytest.skip("sandbox runtime incapable: " + ", ".join(result.missing))
    assert result.status == "passed"


def test_real_srt_controlled_vendor_enforces_filesystem_and_network(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    try:
        runtime = discover_sandbox_runtime(repo)
    except SandboxProfileError as exc:
        pytest.skip(f"linked-worktree runtime unavailable: {exc.reason}")
    preflight = preflight_runtime(runtime, run_probe=True)
    if not preflight.ok:
        pytest.skip("sandbox runtime incapable: " + ", ".join(preflight.missing))
    common_git = _git_path(repo, "--git-common-dir")
    common_repo = common_git.parent
    fixture = Path(__file__).parent / "fixtures" / "sandbox_vendor.py"
    secret = tmp_path / "credential.txt"
    secret.write_text("do-not-read")
    launch = SandboxLaunch(
        worktree_root=repo,
        common_repo=common_repo,
        common_git_dir=common_git,
        git_toplevel=_git_path(repo, "--show-toplevel"),
        git_common_dir=common_git,
        vendor_executable=Path(sys.executable),
        vendor_install_root=Path(sys.executable).resolve().parent,
        policy=_deny_all_policy(),
        write_capable=False,
        credential_env_key="VENDOR_TOKEN",
        state_env_keys=(),
        credential_paths=(secret,),
        authored_read_paths=(fixture,),
    )
    audit = _RecordingAudit()

    denied_write = repo / "sandbox-runtime-review-write.tmp"
    denied_write.unlink(missing_ok=True)
    result = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, str(fixture), "write", str(denied_write)),
            cwd=repo,
            env={"VENDOR_TOKEN": "fixture-token"},
            timeout_seconds=15,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit,
            audit_event={"event_id": "review-write"},
        )
    )
    assert result.sandbox_applied is True
    assert not denied_write.exists()

    credential = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, str(fixture), "read", str(secret)),
            cwd=repo,
            env={"VENDOR_TOKEN": "fixture-token"},
            timeout_seconds=15,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit,
            audit_event={"event_id": "credential-read"},
        )
    )
    assert credential.returncode != 0
    assert "do-not-read" not in credential.stdout

    private_network = run_local_process(
        LocalProcessRequest(
            argv=(sys.executable, str(fixture), "fetch", "http://127.0.0.1:9"),
            cwd=repo,
            env={"VENDOR_TOKEN": "fixture-token"},
            timeout_seconds=15,
            isolation="sandbox",
            sandbox_launch=launch,
            runtime=runtime,
            audit_port=audit,
            audit_event={"event_id": "private-network"},
        )
    )
    assert private_network.returncode != 0


def test_real_srt_complete_rollout_evidence(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    if not (repo / ".git").is_file():
        pytest.skip("sandbox runtime evidence requires a linked managed worktree")
    try:
        runtime = discover_sandbox_runtime(repo)
    except SandboxProfileError as exc:
        pytest.skip(f"linked-worktree runtime unavailable: {exc.reason}")
    preflight = preflight_runtime(runtime, run_probe=True)
    if not preflight.ok:
        pytest.skip("sandbox runtime incapable: " + ", ".join(preflight.missing))
    common_git = _git_path(repo, "--git-common-dir")
    common_repo = common_git.parent
    assert runtime.primary_checkout == common_repo
    assert runtime.common_git_dir == common_git
    fixture = Path(__file__).parent / "fixtures" / "sandbox_vendor.py"
    configured_executable = _configured_vendor_command(repo, "ocr-local")
    secret = tmp_path / "credential.txt"
    secret.write_text("do-not-read")
    audit = _RecordingAudit()

    def launch(policy: dict, *, write_capable: bool) -> SandboxLaunch:
        return SandboxLaunch(
            worktree_root=repo,
            common_repo=common_repo,
            common_git_dir=common_git,
            git_toplevel=_git_path(repo, "--show-toplevel"),
            git_common_dir=common_git,
            vendor_executable=configured_executable,
            vendor_install_root=configured_executable.parent,
            policy=policy,
            write_capable=write_capable,
            credential_env_key="VENDOR_TOKEN",
            state_env_keys=(),
            credential_paths=(secret,),
            authored_read_paths=(fixture,),
        )

    event_counter = 0

    def run(
        args: tuple[str, ...], policy: dict, *, write_capable: bool = False
    ):
        nonlocal event_counter
        event_counter += 1
        return run_local_process(
            LocalProcessRequest(
                argv=(str(configured_executable), str(fixture), *args),
                cwd=repo,
                env={"VENDOR_TOKEN": "fixture-token", "LANG": "C.UTF-8"},
                timeout_seconds=30,
                isolation="sandbox",
                sandbox_launch=launch(policy, write_capable=write_capable),
                runtime=runtime,
                audit_port=audit,
                audit_event=_audit_event(
                    policy,
                    repo,
                    event_id=f"00000000-0000-4000-8000-{event_counter:012d}",
                    executable=configured_executable,
                ),
            )
        )

    inside = repo / "sandbox-runtime-write-evidence.tmp"
    outside = tmp_path / "sandbox-runtime-escape.tmp"
    inside.unlink(missing_ok=True)
    outside.unlink(missing_ok=True)
    try:
        written = run(("write", str(inside)), _deny_all_policy(), write_capable=True)
        assert written.sandbox_applied is True and written.returncode == 0
        assert inside.read_text() == "sandbox-write\n"
        escaped = run(("write", str(outside)), _deny_all_policy(), write_capable=True)
        assert escaped.returncode != 0
        assert not outside.exists()

        allowed = run(("fetch", "https://example.com"), _allow_policy("example.com", 443))
        assert allowed.returncode == 0
        assert "200" in allowed.stdout
        denied = run(("fetch", "https://example.com"), _deny_all_policy())
        assert denied.returncode != 0
        private = run(("fetch", "http://127.0.0.1:9"), _allow_policy("example.com", 443))
        assert private.returncode != 0
        dns_private = run(
            ("fetch", "http://127.0.0.1.nip.io:9"),
            _allow_policy("127.0.0.1.nip.io", 9),
        )
        assert dns_private.returncode != 0

        version_policy = _deny_all_policy()
        version_result = run_local_process(
            LocalProcessRequest(
                argv=(str(configured_executable), "--version"),
                cwd=repo,
                env={"VENDOR_TOKEN": "fixture-token", "LANG": "C.UTF-8"},
                timeout_seconds=30,
                isolation="sandbox",
                sandbox_launch=launch(version_policy, write_capable=False),
                runtime=runtime,
                audit_port=audit,
                audit_event=_audit_event(
                    version_policy,
                    repo,
                    event_id="00000000-0000-4000-8000-999999999999",
                ),
            )
        )
        assert version_result.sandbox_applied is True
        assert version_result.returncode == 0
        version = (version_result.stdout or version_result.stderr).strip()
        assert version.startswith("Python ")
        final_event = audit.events[-1]
        assert final_event["runtime_version"] == "0.0.77"
        assert len(final_event["settings_digest"]) == 64
        assert final_event["policy_digest"] == version_policy["policy_digest"]
        evidence = _build_probe_evidence(
            platform="darwin" if platform_module.system() == "Darwin" else "linux",
                executable=str(configured_executable),
            executable_version=version,
            event=final_event,
            network_outcomes={
                "allowed": "passed", "denied": "passed", "private": "passed",
                "dns_resolved_private": "passed",
            },
        )
        if output := os.environ.get("SANDBOX_RUNTIME_PROBE_OUTPUT"):
            Path(output).write_text(
                json.dumps(evidence, sort_keys=True, separators=(",", ":"))
            )
    finally:
        inside.unlink(missing_ok=True)
