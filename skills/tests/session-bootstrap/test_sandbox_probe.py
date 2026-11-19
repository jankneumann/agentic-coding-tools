"""The sandbox probe reports whether configured denials are enforced.

The probe is exercised against a temporary tree with injected read, write
and connect functions, so no test touches the real home directory or the
network (design D7, D8).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parents[3]
_PROBE = _REPO / "skills" / "session-bootstrap" / "scripts" / "sandbox_probe.py"

_spec = importlib.util.spec_from_file_location("sandbox_probe", _PROBE)
assert _spec and _spec.loader
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe
_spec.loader.exec_module(probe)

SECRET = "TOP-SECRET-CONTENT-DO-NOT-PRINT"


def _local() -> SimpleNamespace:
    return SimpleNamespace(isolation_provided=False, source="default")


def _cloud() -> SimpleNamespace:
    return SimpleNamespace(isolation_provided=True, source="env_var")


@pytest.fixture
def host(tmp_path: Path) -> SimpleNamespace:
    """A fake home with one credential dir, one credential file and a sibling."""
    home = tmp_path / "home"
    project = home / "work" / "project"
    sibling = home / "work" / "other-checkout"
    (project / ".claude").mkdir(parents=True)
    sibling.mkdir()
    (sibling / "notes.txt").write_text(SECRET)
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_ed25519").write_text(SECRET)
    (home / ".netrc").write_text(SECRET)
    settings = {
        "sandbox": {
            "enabled": True,
            "filesystem": {
                "denyRead": ["~/.ssh", "~/.netrc", "~/.kube", ".."],
                "allowRead": ["."],
            },
        }
    }
    (project / ".claude" / "settings.json").write_text(json.dumps(settings))
    return SimpleNamespace(home=home, project=project, sibling=sibling)


def _denying_reader(denied: set[Path]):
    def read(path: Path) -> None:
        for root in denied:
            if path == root or root in path.parents:
                raise PermissionError(str(path))
        probe.read_path(path)

    return read


def _refuse(*_args: object) -> None:
    raise PermissionError("refused")


def _accept(*_args: object) -> None:
    return None


def _run(host: SimpleNamespace, **overrides: object):
    kwargs: dict = {
        "project_root": host.project,
        "home": host.home,
        "detect": _local,
        "write": _refuse,
        "connect": _refuse,
    }
    kwargs.update(overrides)
    return probe.run_probe(**kwargs)


def _verdicts(report) -> dict[str, str]:
    return {f"{c.check}:{c.target}": c.verdict for c in report.checks}


# --- skipped where isolation is provided ------------------------------------


def test_skipped_when_isolation_is_provided(host: SimpleNamespace) -> None:
    calls: list[Path] = []
    report = _run(host, detect=_cloud, read=calls.append, write=calls.append)
    assert report.status == "skipped"
    assert report.source == "env_var"
    assert report.exit_code == 0
    assert report.checks == []
    assert calls == [], "a skipped probe must not attempt any read or write"


def test_skipped_output_names_the_detection_source(host: SimpleNamespace) -> None:
    text = probe.render(_run(host, detect=_cloud))
    assert "skipped" in text
    assert "env_var" in text


# --- unenforced denial ------------------------------------------------------


def test_readable_denied_path_is_not_enforced(host: SimpleNamespace) -> None:
    report = _run(host)  # default reader: nothing is denied
    verdicts = _verdicts(report)
    assert verdicts[f"deny_read:{host.home / '.ssh'}"] == "not_enforced"
    assert verdicts[f"deny_read:{host.home / '.netrc'}"] == "not_enforced"
    assert report.status == "not_enforced"
    assert report.exit_code != 0


def test_one_unenforced_check_fails_the_run(host: SimpleNamespace) -> None:
    reader = _denying_reader({host.home / ".ssh", host.home / "work"})
    report = _run(host, read=reader)  # .netrc stays readable
    assert _verdicts(report)[f"deny_read:{host.home / '.netrc'}"] == "not_enforced"
    assert report.exit_code != 0


# --- enforced on a sandboxed host (faked) -----------------------------------


def _sandboxed_reader(host: SimpleNamespace):
    """Deny credentials and the parent, re-allow the project, as D3 intends."""
    denied = {host.home / ".ssh", host.home / ".netrc", host.home / "work"}

    def read(path: Path) -> None:
        if path == host.project or host.project in path.parents:
            probe.read_path(path)
            return
        for root in denied:
            if path == root or root in path.parents:
                raise PermissionError(str(path))
        probe.read_path(path)

    return read


def test_sandboxed_host_reports_enforced(host: SimpleNamespace) -> None:
    report = _run(host, read=_sandboxed_reader(host))
    verdicts = _verdicts(report)
    assert verdicts[f"deny_read:{host.home / '.ssh'}"] == "enforced"
    assert verdicts[f"deny_read:{host.home / '.netrc'}"] == "enforced"
    assert verdicts[f"deny_read:{host.home / 'work'}"] == "enforced"
    assert verdicts[f"sibling_read:{host.sibling}"] == "enforced"
    assert verdicts[f"project_readable:{host.project}"] == "enforced"
    assert report.status == "enforced"
    assert report.exit_code == 0


def test_missing_denied_path_is_not_applicable(host: SimpleNamespace) -> None:
    report = _run(host, read=_sandboxed_reader(host))
    assert _verdicts(report)[f"deny_read:{host.home / '.kube'}"] == "not_applicable"
    assert report.exit_code == 0


def test_unreadable_project_is_not_enforced(host: SimpleNamespace) -> None:
    """If allowRead does not win over the denied parent, the design is unmet."""
    report = _run(host, read=_denying_reader({host.home}))
    assert _verdicts(report)[f"project_readable:{host.project}"] == "not_enforced"
    assert report.exit_code != 0


def test_write_and_network_checks(host: SimpleNamespace) -> None:
    reader = _sandboxed_reader(host)
    open_host = _run(host, read=reader, write=_accept, connect=_accept)
    verdicts = _verdicts(open_host)
    assert verdicts[f"write_outside:{host.home}"] == "not_enforced"
    assert verdicts["connect:github.com:443"] == "not_enforced"
    closed = _verdicts(_run(host, read=reader))
    assert closed[f"write_outside:{host.home}"] == "enforced"
    assert closed["connect:github.com:443"] == "enforced"


# --- no content leak --------------------------------------------------------


def test_output_has_no_file_content(host: SimpleNamespace) -> None:
    report = _run(host)
    for text in (probe.render(report), probe.render(report, as_json=True)):
        assert SECRET not in text
        assert "id_ed25519" not in text, "directory entries are content too"
        assert "notes.txt" not in text


def test_json_output_carries_only_documented_fields(host: SimpleNamespace) -> None:
    data = json.loads(probe.render(_run(host), as_json=True))
    assert set(data) == {"status", "source", "checks"}
    for check in data["checks"]:
        assert set(check) == {"check", "target", "verdict"}
        assert check["verdict"] in {"enforced", "not_enforced", "not_applicable"}


# --- targets come from the settings file ------------------------------------


def test_targets_come_from_settings(host: SimpleNamespace) -> None:
    extra = host.home / ".only-in-settings"
    extra.mkdir()
    path = host.project / ".claude" / "settings.json"
    settings = json.loads(path.read_text())
    settings["sandbox"]["filesystem"]["denyRead"] = ["~/.only-in-settings"]
    path.write_text(json.dumps(settings))
    targets = [c.target for c in _run(host).checks if c.check == "deny_read"]
    assert targets == [str(extra)]


def test_module_holds_no_second_path_list() -> None:
    source = _PROBE.read_text(encoding="utf-8")
    for literal in (".ssh", ".aws", ".gnupg", ".netrc", ".kube", ".codex"):
        assert literal not in source, f"{literal} is hard-coded in the probe"


def test_disabled_sandbox_is_reported(host: SimpleNamespace) -> None:
    local = host.project / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"sandbox": {"enabled": False}}))
    report = _run(host)
    assert report.status == "disabled"
    assert report.checks == []
    assert report.exit_code == 0


# --- implementation constraints ---------------------------------------------


def test_probe_uses_only_the_standard_library() -> None:
    import ast

    tree = ast.parse(_PROBE.read_text(encoding="utf-8"))
    stdlib = set(sys.stdlib_module_names) | {"shared"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert name.split(".")[0] in stdlib, name


def test_main_in_this_container_is_skipped(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:
    monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")
    assert probe.main([]) == 0
    assert capsys.readouterr().out.startswith("skipped")
