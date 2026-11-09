"""Tests for scripts/contract_gate/fetch_oasdiff.py (design D4, as amended).

Every case injects the command runner, so neither Go nor the network is used.
The invariant under test: nothing is installed (and so no comparison can run)
unless Go's checksum database verification is on for the module and the
module's go.mod hash matches the recorded pin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

GATE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GATE_DIR))
import fetch_oasdiff as fo

RECORDED = "h1:zrOVqxQfWeiPci5XvFhtnCQrJVLov2v8+oEZhAKAHtA="


class FakeRunner:
    def __init__(self, *, go_env=None, download=None, download_rc=0, install_rc=0):
        self.go_env = go_env or {}
        self.download = (
            download
            if download is not None
            else {
                "Path": fo.MODULE,
                "Version": fo.VERSION,
                "Sum": "h1:moduleziphash=",
                "GoModSum": RECORDED,
            }
        )
        self.download_rc = download_rc
        self.install_rc = install_rc
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, cmd: list[str], env: dict[str, str]) -> fo.Result:
        self.calls.append((cmd, env))
        if cmd[:3] == ["go", "env", "-json"]:
            return fo.Result(0, json.dumps(self.go_env), "")
        if cmd[:3] == ["go", "mod", "download"]:
            return fo.Result(self.download_rc, json.dumps(self.download), "boom")
        if cmd[:2] == ["go", "install"]:
            return fo.Result(self.install_rc, "", "")
        raise AssertionError(f"unexpected command {cmd}")

    @property
    def commands(self) -> list[list[str]]:
        return [c for c, _ in self.calls]

    def installed(self) -> bool:
        return any(c[:2] == ["go", "install"] for c in self.commands)


def _sum_file(tmp_path: Path, gomodsum: str = RECORDED) -> Path:
    path = tmp_path / "oasdiff.sum"
    path.write_text(f"{fo.MODULE} {fo.VERSION}/go.mod {gomodsum}\n")
    return path


def _fetch(tmp_path, runner, env=None, sum_file=None):
    return fo.fetch(
        bin_dir=tmp_path / "bin",
        sum_file=sum_file or _sum_file(tmp_path),
        env=env if env is not None else {"PATH": "/usr/bin"},
        runner=runner,
    )


def test_recorded_sum_file_pins_the_expected_hash():
    assert fo.read_recorded_gomodsum(GATE_DIR / "oasdiff.sum") == RECORDED


def test_happy_path_downloads_verifies_then_installs_with_gobin(tmp_path, capsys):
    runner = FakeRunner()

    binary = _fetch(tmp_path, runner)

    cmds = runner.commands
    download_idx = cmds.index(
        ["go", "mod", "download", "-json", f"{fo.MODULE}@{fo.VERSION}"]
    )
    install_idx = cmds.index(["go", "install", f"{fo.MODULE}@{fo.VERSION}"])
    assert download_idx < install_idx
    install_env = runner.calls[install_idx][1]
    assert install_env["GOBIN"] == str(tmp_path / "bin")
    assert binary == tmp_path / "bin" / "oasdiff"


def test_tampered_recorded_gomodsum_refuses_before_install(tmp_path):
    runner = FakeRunner()
    tampered = _sum_file(tmp_path, "h1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

    with pytest.raises(fo.FetchError, match="GoModSum"):
        _fetch(tmp_path, runner, sum_file=tampered)
    assert not runner.installed()


def test_downloaded_gomodsum_mismatch_refuses(tmp_path):
    runner = FakeRunner(
        download={"Sum": "h1:x=", "GoModSum": "h1:different=", "Version": fo.VERSION}
    )
    with pytest.raises(fo.FetchError):
        _fetch(tmp_path, runner)
    assert not runner.installed()


def test_empty_sum_refuses(tmp_path):
    runner = FakeRunner(download={"Sum": "", "GoModSum": RECORDED})
    with pytest.raises(fo.FetchError, match="Sum"):
        _fetch(tmp_path, runner)
    assert not runner.installed()


def test_download_failure_refuses(tmp_path):
    runner = FakeRunner(
        download_rc=1, download={"Error": "verifying module: checksum mismatch"}
    )
    with pytest.raises(fo.FetchError):
        _fetch(tmp_path, runner)
    assert not runner.installed()


def test_install_failure_raises(tmp_path):
    with pytest.raises(fo.FetchError):
        _fetch(tmp_path, FakeRunner(install_rc=1))


@pytest.mark.parametrize(
    "env",
    [
        {"GOSUMDB": "off"},
        {"GOSUMDB": " OFF "},
        {"GOFLAGS": "-mod=mod -insecure"},
        {"GOFLAGS": "-insecure=true"},
        {"GONOSUMDB": "github.com/oasdiff"},
        {"GONOSUMDB": "example.com,github.com/oasdiff/*"},
        {"GONOSUMCHECK": "github.com"},
        {"GOINSECURE": "github.com/*/oasdiff"},
        {"GOPRIVATE": "*.com"},
        {"GOPRIVATE": "github.com/oasdiff/oasdiff"},
    ],
)
def test_process_env_disabling_verification_refuses(tmp_path, env):
    runner = FakeRunner()
    with pytest.raises(fo.FetchError, match="verification"):
        _fetch(tmp_path, runner, env=env)
    assert not runner.installed()
    assert not any(c[:3] == ["go", "mod", "download"] for c in runner.commands)


@pytest.mark.parametrize(
    "go_env",
    [{"GOSUMDB": "off"}, {"GONOSUMDB": "github.com/oasdiff"}, {"GOFLAGS": "-insecure"}],
)
def test_go_env_file_disabling_verification_refuses(tmp_path, go_env):
    """`go env -w` settings are not in the process env; they must be caught too."""
    runner = FakeRunner(go_env=go_env)
    with pytest.raises(fo.FetchError, match="verification"):
        _fetch(tmp_path, runner)
    assert not runner.installed()


@pytest.mark.parametrize(
    "env",
    [
        {"GOSUMDB": "sum.golang.org"},
        {"GONOSUMDB": "github.com/other,gitlab.com"},
        # A prefix of a path element is not a path prefix.
        {"GOPRIVATE": "github.com/oasdif"},
        {"GOFLAGS": "-mod=mod"},
        {"GONOSUMDB": " , "},
    ],
)
def test_unrelated_settings_are_allowed(tmp_path, env):
    runner = FakeRunner()
    _fetch(tmp_path, runner, env=env)
    assert runner.installed()


@pytest.mark.parametrize(
    ("patterns", "target", "expected"),
    [
        ("github.com/oasdiff", "github.com/oasdiff/oasdiff", True),
        ("github.com", "github.com/oasdiff/oasdiff", True),
        ("*", "github.com/oasdiff/oasdiff", True),
        ("github.com/*", "github.com/oasdiff/oasdiff", True),
        ("github.com/oasdiff/oasdiff/sub", "github.com/oasdiff/oasdiff", False),
        ("github.com/oas", "github.com/oasdiff/oasdiff", False),
        ("", "github.com/oasdiff/oasdiff", False),
    ],
)
def test_match_prefix_patterns(patterns, target, expected):
    assert fo.match_prefix_patterns(patterns, target) is expected


def test_main_reports_refusal_with_nonzero_exit(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GOSUMDB", "off")
    code = fo.main(["--bin-dir", str(tmp_path / "bin")], runner=FakeRunner())
    assert code != 0
    assert "GOSUMDB" in capsys.readouterr().err
