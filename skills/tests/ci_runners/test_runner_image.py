"""Runner image: pinned base, toolchain, non-root user, job-started hook (D4, D6)."""

from __future__ import annotations

import json
import re
import subprocess

import pytest

FROM_RE = re.compile(
    r"^FROM\s+ghcr\.io/actions/actions-runner:(?P<tag>[0-9]+\.[0-9]+\.[0-9]+)@sha256:(?P<digest>[0-9a-f]{64})\s*$",
    re.M,
)


@pytest.fixture(scope="module")
def containerfile(kit_dir):
    return (kit_dir / "Containerfile").read_text()


def test_base_image_is_pinned(containerfile):
    froms = re.findall(r"^FROM\s+.*$", containerfile, flags=re.M)
    assert len(froms) == 1
    assert FROM_RE.match(froms[0]), froms[0]
    assert "latest" not in froms[0]


def test_every_toolchain_package_is_installed(kit_dir, containerfile):
    packages = [
        ln.strip() for ln in (kit_dir / "toolchain.txt").read_text().splitlines() if ln.strip()
    ]
    for required in (
        "git",
        "curl",
        "jq",
        "make",
        "build-essential",
        "unzip",
        "xz-utils",
        "zstd",
        "ca-certificates",
        "python3",
    ):
        assert required in packages, required
    assert "COPY toolchain.txt" in containerfile
    install_lines = [ln for ln in containerfile.splitlines() if "apt-get install" in ln]
    assert install_lines and all("toolchain.txt" in ln or "xargs" in ln for ln in install_lines)


def test_final_user_is_not_root(containerfile):
    users = re.findall(r"^USER\s+(\S+)", containerfile, flags=re.M)
    assert users and users[-1] not in ("root", "0")


def test_no_sudoers_grant_is_added(containerfile):
    assert not re.search(r"(echo|printf|tee|>>|>)\s.*sudoers", containerfile.replace("\\\n", " "))
    assert "usermod -aG sudo" not in containerfile
    assert "sudoers.d" not in containerfile


def test_image_installs_the_hook(containerfile):
    assert re.search(
        r"^COPY\s+job-started-hook\.sh\s+/opt/gx10/job-started-hook\.sh", containerfile, re.M
    )
    assert re.search(
        r"^ENV\s+ACTIONS_RUNNER_HOOK_JOB_STARTED=/opt/gx10/job-started-hook\.sh\s*$",
        containerfile,
        re.M,
    )


def test_image_sets_uv_cache_dir(containerfile):
    assert re.search(r"^ENV\s+UV_CACHE_DIR=/home/runner/\.cache/uv\s*$", containerfile, re.M)


def test_entrypoint_is_the_runner(containerfile):
    assert "/home/runner/run.sh" in containerfile


# ------------------------------------------------------------------------------- the hook

REPO = "owner/repo"


def _run_hook(kit_dir, tmp_path, event, ref="refs/heads/main", payload=None, drop_payload=False):
    path = tmp_path / "event.json"
    if not drop_payload:
        path.write_text(json.dumps(payload if payload is not None else {}))
    env = {
        "PATH": "/usr/bin:/bin",
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_PATH": str(path),
    }
    return subprocess.run(
        ["bash", str(kit_dir / "job-started-hook.sh")], env=env, capture_output=True, text=True
    )


def _pr(head):
    return {"pull_request": {"head": {"repo": {"full_name": head}}}}


@pytest.mark.parametrize(
    "event,ref,payload,ok",
    [
        ("push", "refs/heads/main", {}, True),
        ("push", "refs/heads/feature", {}, False),
        ("push", "refs/tags/v1", {}, False),
        ("workflow_dispatch", "refs/heads/feature", {}, True),
        ("pull_request", "refs/pull/1/merge", _pr(REPO), True),
        ("pull_request", "refs/pull/1/merge", _pr("OWNER/Repo"), True),
        ("pull_request", "refs/pull/1/merge", _pr("fork/repo"), False),
        ("pull_request", "refs/pull/1/merge", {"pull_request": {"head": {"repo": None}}}, False),
        ("pull_request", "refs/pull/1/merge", {}, False),
        ("pull_request_target", "refs/heads/main", _pr(REPO), False),
        ("merge_group", "refs/heads/gh-readonly-queue/main/x", {}, False),
        ("schedule", "refs/heads/main", {}, False),
        ("workflow_run", "refs/heads/main", {}, False),
        ("", "", {}, False),
    ],
)
def test_hook_decisions(kit_dir, tmp_path, event, ref, payload, ok):
    res = _run_hook(kit_dir, tmp_path, event, ref, payload)
    assert (res.returncode == 0) is ok, res.stderr
    if not ok:
        assert res.stderr.strip(), "a refusal must explain itself"


def test_hook_fails_closed_without_a_payload(kit_dir, tmp_path):
    res = _run_hook(kit_dir, tmp_path, "pull_request", "refs/pull/1/merge", drop_payload=True)
    assert res.returncode != 0


def test_hook_fails_closed_on_malformed_payload(kit_dir, tmp_path):
    (tmp_path / "event.json").write_text("{not json")
    env = {
        "PATH": "/usr/bin:/bin",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REF": "refs/pull/1/merge",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_PATH": str(tmp_path / "event.json"),
    }
    res = subprocess.run(
        ["bash", str(kit_dir / "job-started-hook.sh")], env=env, capture_output=True, text=True
    )
    assert res.returncode != 0
