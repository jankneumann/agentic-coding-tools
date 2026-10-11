"""The operator runbook covers O1-O12 with verification blocks and cross-checks the kit."""

from __future__ import annotations

import re

import pytest

STEPS = [f"O{i}" for i in range(1, 13)]


@pytest.fixture(scope="module")
def runbook(repo_root):
    return (repo_root / "docs" / "guides" / "self-hosted-ci-runners.md").read_text()


def sections(text: str) -> dict[str, str]:
    parts = re.split(r"^#{2,4}\s+(O\d+)\b.*$", text, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_every_step_is_a_heading(runbook):
    assert sorted(sections(runbook), key=lambda s: int(s[1:])) == STEPS


@pytest.mark.parametrize("step", STEPS)
def test_each_step_has_a_bash_verification_block(runbook, step):
    body = sections(runbook)[step]
    blocks = re.findall(r"```bash\n(.*?)```", body, flags=re.S)
    assert blocks, f"{step} has no fenced bash block"
    assert any(b.strip() for b in blocks)


def test_hard_boundary_is_stated(runbook):
    low = " ".join(runbook.lower().split())
    assert "hard boundary" in low
    for phrase in ("register runners", "mint", "systemctl", "main"):
        assert phrase in low


def test_rollback_command_is_named(runbook):
    assert "gh variable set CI_RUNNER_LANE --body hosted" in runbook


def test_design_commitments_are_documented(runbook):
    assert "created" in runbook and "queued" in runbook  # D9 queued-run detection
    assert "GitHub App" in runbook  # D5 upgrade path
    assert "GX10_RUNNER_CACHE_ARGS=--volume gx10-runner-uv-cache:/home/runner/.cache/uv" in runbook
    assert "risk" in runbook.lower() and "Dependabot" in runbook  # D6/A10
    assert "pasta" in runbook and "slirp4netns" in runbook  # A11
    assert "table inet" in runbook and "skuid" in runbook  # D6 nftables


def test_runbook_names_only_existing_kit_paths_and_variables(runbook, kit_dir, repo_root):
    env = (kit_dir / "gx10-runner.env.example").read_text()
    for path in set(re.findall(r"deploy/gx10-runner/[\w./@-]+", runbook)):
        assert (repo_root / path.rstrip(".,)")).exists(), path
    for var in set(re.findall(r"\bGX10_[A-Z_]+\b", runbook)):
        assert var in env or var in {
            "GX10_INSTANCES",
            "GX10_MINT_BASE_DELAY",
            "GX10_GITHUB_API",
            "GX10_HOSTNAME",
            "GX10_RUNNER_TOKEN_FILE",
        }, var


def test_runbook_uses_only_flags_the_cli_accepts(runbook, repo_root):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "ci_wallclock_rb", repo_root / "scripts" / "ci" / "ci_wallclock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ci_wallclock_rb"] = mod
    spec.loader.exec_module(mod)
    parser = mod.build_parser()
    sub = next(a for a in parser._actions if a.dest == "cmd").choices
    for m in re.finditer(r"ci_wallclock\.py\s+([a-z-]+)([^\n`]*)", runbook):
        cmd, rest = m.group(1), m.group(2)
        assert cmd in sub, cmd
        accepted = {s for a in sub[cmd]._actions for s in a.option_strings}
        for flag in re.findall(r"--[a-z-]+", rest):
            assert flag in accepted, f"{cmd} does not accept {flag}"
