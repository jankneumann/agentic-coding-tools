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


def _nft_block(runbook: str) -> str:
    m = re.search(r"<<'NFT'\n(.*?)\nNFT\n", runbook, flags=re.S)
    assert m, "runbook has no NFT ruleset heredoc"
    return m.group(1)


def test_nft_ruleset_is_ordered_persistent_and_dual_stack(runbook):
    rules = _nft_block(runbook)
    assert "table inet gx10_runner_isolation {" in rules
    assert "hook output" in rules and "policy accept" in rules
    lines = [ln.strip() for ln in rules.splitlines()]
    dns_udp = next(i for i, ln in enumerate(lines) if "127.0.0.53 udp dport 53 accept" in ln)
    dns_tcp = next(i for i, ln in enumerate(lines) if "127.0.0.53 tcp dport 53 accept" in ln)
    local_drop = next(i for i, ln in enumerate(lines) if "fib daddr type local drop" in ln)
    assert max(dns_udp, dns_tcp) < local_drop, "DNS exemption must precede the local drop"
    for needle in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
                   "169.254.0.0/16", "fc00::/7", "fe80::/10", 'oifname "tailscale0"'):
        assert needle in rules, needle
    assert all("meta skuid ghrunner" in ln for ln in lines if ln.endswith(("accept", "drop")))
    # persistence and re-check after reboot
    assert 'include "/etc/nftables.d/gx10-runner.nft"' in runbook
    assert "systemctl enable --now nftables" in runbook
    # The table is loaded explicitly: `enable --now` does not reload an active service.
    assert "sudo nft -f /etc/nftables.d/gx10-runner.nft" in runbook


def test_ghrunner_commands_use_the_units_runtime_dir(runbook):
    """Rootless podman/systemctl as ghrunner must share the units' XDG_RUNTIME_DIR."""
    for line in runbook.splitlines():
        if "sudo -u ghrunner podman" in line or "sudo -u ghrunner systemctl" in line:
            raise AssertionError(f"ghrunner command without XDG_RUNTIME_DIR: {line}")
    assert "journalctl --user -u" not in runbook  # would read the operator's own journal
    assert "nft list ruleset | grep skuid" in sections(runbook)["O10"]
