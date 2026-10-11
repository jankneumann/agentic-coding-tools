"""Routed jobs must not need tools the runner image lacks (D2, D6, D10)."""

from __future__ import annotations

import re

import pytest

ALWAYS_DISALLOWED = ("docker", "podman", "sudo", "apt-get")
NEEDS_SETUP = {
    "npm": "actions/setup-node",
    "npx": "actions/setup-node",
    "node": "actions/setup-node",
    "java": "actions/setup-java",
    "go": "actions/setup-go",
}
#: (workflow, job, command, justification). Starts empty on purpose (D10).
ALLOWLIST: list[tuple[str, str, str, str]] = []

_SEPARATORS = re.compile(r"&&|\|\||;|\||\$\(|\(")


def commands_in(run_text: str) -> set[str]:
    """Hosted-only commands invoked in command position within a ``run:`` block.

    Command position is the start of a line or the word after ``;``, ``&&``, ``||``,
    ``|``, ``$(``, ``sudo`` or ``env`` (D10). A path such as
    ``scripts/check_docker_imports.py`` is a single word that is not the command name.
    """
    watched = {*ALWAYS_DISALLOWED, *NEEDS_SETUP}
    found: set[str] = set()
    for line in run_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for segment in _SEPARATORS.split(line):
            words = segment.split()
            while words:
                head = words[0]
                if head in watched:
                    found.add(head)
                if head in ("sudo", "env"):
                    words = words[1:]
                    while head == "env" and words and "=" in words[0]:
                        words = words[1:]
                    continue
                break
    return found


def _routed(manifest, load_workflow):
    for wf_name, wf in manifest["workflows"].items():
        jobs = load_workflow(wf_name)["jobs"]
        for job_id, entry in wf["jobs"].items():
            if entry["lane"] == "routed":
                yield wf_name, job_id, jobs[job_id]


def _uses(job) -> list[str]:
    return [str(s.get("uses", "")) for s in job.get("steps", [])]


def test_script_path_is_not_an_invocation():
    text = "uv run python scripts/check_docker_imports.py\n"
    assert commands_in(text) == set()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("docker run --rm x", {"docker"}),
        ("a && sudo apt-get install -y x", {"sudo", "apt-get"}),
        ("x | podman load", {"podman"}),
        ("v=$(npm bin)", {"npm"}),
        ("# docker is not run here", set()),
        ("echo go", set()),
    ],
)
def test_matcher(text, expected):
    assert commands_in(text) == expected


def test_routed_jobs_have_no_services(manifest, load_workflow):
    for wf_name, job_id, job in _routed(manifest, load_workflow):
        assert "services" not in job, f"{wf_name}:{job_id} routed but declares services:"


def test_routed_jobs_do_not_call_container_or_root_tools(manifest, load_workflow):
    allowed = {(w, j, c) for w, j, c, _ in ALLOWLIST}
    for wf_name, job_id, job in _routed(manifest, load_workflow):
        for step in job.get("steps", []):
            for cmd in commands_in(step.get("run", "")) & set(ALWAYS_DISALLOWED):
                assert (wf_name, job_id, cmd) in allowed, (
                    f"{wf_name}:{job_id} invokes {cmd} but is routed"
                )


def test_allowlist_entries_are_justified():
    for entry in ALLOWLIST:
        assert len(entry) == 4 and entry[3].strip()


def test_setup_actions_present_for_runtime_commands(manifest, load_workflow):
    for wf_name, job_id, job in _routed(manifest, load_workflow):
        uses = _uses(job)
        for step in job.get("steps", []):
            for cmd in commands_in(step.get("run", "")) & set(NEEDS_SETUP):
                needed = NEEDS_SETUP[cmd]
                assert any(u.startswith(needed) for u in uses), (
                    f"{wf_name}:{job_id} invokes {cmd} without {needed}"
                )


def test_routed_job_missing_setup_node_is_detected():
    job = {"steps": [{"run": "npm install -g x"}]}
    cmds = commands_in(job["steps"][0]["run"]) & set(NEEDS_SETUP)
    assert cmds == {"npm"}
    assert not any(u.startswith("actions/setup-node") for u in _uses(job))


def test_setup_uv_uses_the_shared_cache_path(manifest, load_workflow):
    n = 0
    for wf_name, job_id, job in _routed(manifest, load_workflow):
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("astral-sh/setup-uv"):
                n += 1
                got = (step.get("with") or {}).get("cache-local-path")
                assert got == "/home/runner/.cache/uv", f"{wf_name}:{job_id}"
    assert n > 0
