"""Pure SRT profile, discovery, environment, and lifecycle tests."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from shared.sandbox_profile import (
    BASELINE_DENIED_RESOLVED_ADDRESSES,
    RuntimePaths,
    SRT_INTEGRITY,
    SRT_RESOLVED,
    SandboxLaunch,
    SandboxProfileError,
    build_child_environment,
    discover_sandbox_runtime,
    prepare_sandbox_command,
    preflight_runtime,
    render_sandbox_settings,
)


def _policy(*, rules=None):
    return {
        "schema_version": 1,
        "agent_id": "codex-local",
        "default_action": "deny",
        "rules": rules
        or [
            {
                "destination_kind": "dns",
                "destination_pattern": "api.example.com",
                "port": 443,
                "action": "allow",
                "priority": 1,
                "scope": "agent_profile",
                "policy_id": "rule-1",
            },
            {
                "destination_kind": "dns",
                "destination_pattern": "*.blocked.example.com",
                "port": None,
                "action": "deny",
                "priority": 2,
                "scope": "global",
                "policy_id": "rule-2",
            },
        ],
        "policy_revision": "v1:now:2",
        "policy_digest": "a" * 64,
    }


def _launch(tmp_path: Path, *, write_capable: bool = False) -> SandboxLaunch:
    repo = tmp_path / "repo"
    root = repo / ".git-worktrees" / "change-a"
    root.mkdir(parents=True)
    common_git = repo / ".git"
    common_git.mkdir()
    (root / ".git").write_text("gitdir: elsewhere\n")
    vendor_root = tmp_path / "vendor"
    vendor_root.mkdir()
    executable = vendor_root / "vendor"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    return SandboxLaunch(
        worktree_root=root,
        common_repo=repo,
        common_git_dir=common_git,
        git_toplevel=root,
        git_common_dir=common_git,
        vendor_executable=executable,
        vendor_install_root=vendor_root,
        policy=_policy(),
        write_capable=write_capable,
        credential_env_key="VENDOR_TOKEN",
        state_env_keys=("VENDOR_HOME",),
    )


def _runtime(tmp_path: Path) -> RuntimePaths:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    node = runtime_dir / "node"
    entry = runtime_dir / "cli.js"
    for path in (node, entry):
        path.write_text("")
        path.chmod(0o755)
    return RuntimePaths(
        node=node,
        entrypoint=entry,
        runtime_dir=runtime_dir,
        primary_checkout=tmp_path,
        common_git_dir=tmp_path / ".git",
        version="0.0.77",
        bwrap=Path("/usr/bin/bwrap"),
        socat=Path("/usr/bin/socat"),
        rg=Path("/usr/bin/rg"),
    )


def test_renderer_is_deterministic_deny_first_and_mode_aware(tmp_path: Path) -> None:
    launch = _launch(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    rendered = render_sandbox_settings(launch, state_root=state, platform="linux")
    again = render_sandbox_settings(launch, state_root=state, platform="linux")

    assert rendered == again
    assert rendered.settings["network"]["allowedDomains"] == ["api.example.com:443"]
    assert rendered.settings["network"]["deniedDomains"] == ["*.blocked.example.com"]
    assert rendered.settings["network"]["deniedResolvedAddresses"] == list(
        BASELINE_DENIED_RESOLVED_ADDRESSES
    )
    assert str(launch.worktree_root) not in rendered.settings["filesystem"]["allowWrite"]
    assert str(state) in rendered.settings["filesystem"]["allowWrite"]
    assert rendered.settings["enableWeakerNestedSandbox"] is False
    assert rendered.settings["enableWeakerNetworkIsolation"] is False
    assert rendered.settings["allowAppleEvents"] is False

    writable = render_sandbox_settings(
        _launch(tmp_path / "write", write_capable=True),
        state_root=state,
        platform="linux",
    )
    assert (
        str((tmp_path / "write/repo/.git-worktrees/change-a").resolve())
        in writable.settings["filesystem"]["allowWrite"]
    )


def test_renderer_rejects_private_literal_allow(tmp_path: Path) -> None:
    launch = _launch(tmp_path)
    launch = launch.with_policy(
        _policy(
            rules=[
                {
                    "destination_kind": "ipv4",
                    "destination_pattern": "127.0.0.1",
                    "port": 443,
                    "action": "allow",
                    "priority": 1,
                    "scope": "global",
                    "policy_id": "private",
                }
            ]
        )
    )
    with pytest.raises(SandboxProfileError, match="private IP literal"):
        render_sandbox_settings(launch, state_root=tmp_path / "state", platform="linux")


def test_positive_child_environment_keeps_only_selected_credential(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    env = build_child_environment(
        parent_env={
            "LANG": "C.UTF-8",
            "LC_TIME": "C",
            "TERM": "xterm",
            "DATABASE_URL": "secret-db",
            "COORDINATION_API_KEY": "secret-coordinator",
            "VENDOR_TOKEN": "selected",
            "OTHER_VENDOR_TOKEN": "not-selected",
            "HTTP_PROXY": "http://ambient",
            "PYTHONPATH": "/escape",
        },
        state_root=state,
        runtime=runtime,
        vendor_executable=tmp_path / "vendor",
        credential_env_key="VENDOR_TOKEN",
        state_env_keys=("VENDOR_HOME",),
        allowed_tool_dirs=(),
    )
    assert env["VENDOR_TOKEN"] == "selected"
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["HOME"].startswith(str(state))
    assert env["VENDOR_HOME"].startswith(str(state))
    assert "DATABASE_URL" not in env
    assert "COORDINATION_API_KEY" not in env
    assert "OTHER_VENDOR_TOKEN" not in env
    assert "HTTP_PROXY" not in env
    assert "PYTHONPATH" not in env


def test_prepared_command_materializes_0600_and_cleans_owned_state(tmp_path: Path) -> None:
    launch = _launch(tmp_path)
    runtime = _runtime(tmp_path)
    temp_parent = tmp_path / "outside"
    temp_parent.mkdir()
    with prepare_sandbox_command(
        runtime=runtime,
        launch=launch,
        vendor_argv=("--version",),
        parent_env={"VENDOR_TOKEN": "selected"},
        temp_parent=temp_parent,
        skip_preflight=True,
    ) as prepared:
        state_root = prepared.state_root
        assert prepared.argv[:4] == (
            str(runtime.node),
            str(runtime.entrypoint),
            "--settings",
            str(prepared.settings_path),
        )
        assert prepared.argv[4:6] == ("--", str(launch.vendor_executable.resolve()))
        assert stat.S_IMODE(prepared.settings_path.stat().st_mode) == 0o600
        document = json.loads(prepared.settings_path.read_text())
        assert document["network"]["allowedDomains"] == ["api.example.com:443"]
    assert not state_root.exists()
    assert prepared.cleanup_status == "succeeded"


def test_discovery_uses_git_common_dir_primary_checkout(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    worktree = primary / ".git-worktrees" / "change-a"
    worktree.mkdir(parents=True)
    runtime_dir = primary / "tools" / "sandbox-runtime"
    package_dir = runtime_dir / "node_modules" / "@anthropic-ai" / "sandbox-runtime"
    package_dir.mkdir(parents=True)
    (package_dir / "dist").mkdir()
    (package_dir / "dist" / "cli.js").write_text("")
    (package_dir / "package.json").write_text(
        json.dumps({"version": "0.0.77", "bin": {"srt": "dist/cli.js"}})
    )
    (runtime_dir / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/@anthropic-ai/sandbox-runtime": {
                        "version": "0.0.77",
                        "resolved": SRT_RESOLVED,
                        "integrity": SRT_INTEGRITY,
                    }
                }
            }
        )
    )

    def git_runner(args, **_kwargs):
        value = str(worktree) if args[-1] == "--show-toplevel" else str(primary / ".git")
        return type("Result", (), {"stdout": value + "\n", "returncode": 0})()

    runtime = discover_sandbox_runtime(
        worktree,
        which=lambda name: f"/usr/bin/{name}",
        git_runner=git_runner,
    )
    assert runtime.primary_checkout == primary
    assert runtime.runtime_dir == runtime_dir
    assert runtime.version == "0.0.77"


def test_preflight_reports_exact_missing_prerequisites(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime = RuntimePaths(**{**runtime.__dict__, "socat": None})
    result = preflight_runtime(runtime, platform="linux", run_probe=False)
    assert result.ok is False
    assert result.status == "capability_failed"
    assert "socat" in result.missing
