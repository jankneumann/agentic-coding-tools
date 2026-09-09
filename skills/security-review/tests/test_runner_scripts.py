from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_dependency_check_falls_back_to_docker(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_executable(
        fake_bin / "dependency-check",
        "#!/usr/bin/env bash\nexit 9\n",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
if [[ "${1:-}" == "run" ]]; then
  report_dir=""
  prev=""
  for arg in "$@"; do
    if [[ "$prev" == "-v" && "$arg" == *":/report" ]]; then
      report_dir="${arg%:/report}"
    fi
    prev="$arg"
  done
  mkdir -p "$report_dir"
  cat > "$report_dir/dependency-check-report.json" <<'JSON'
{"dependencies":[]}
JSON
  exit 0
fi
exit 1
""",
    )
    _write_executable(
        fake_bin / "podman",
        "#!/usr/bin/env bash\nexit 1\n",
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    out_dir = tmp_path / "out"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [
            str(SCRIPTS_DIR / "run_dependency_check.sh"),
            "--repo",
            str(repo),
            "--out",
            str(out_dir),
            "--project",
            "demo",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["mode"] == "docker-fallback"
    assert "native dependency-check failed" in payload["message"]
    assert (out_dir / "dependency-check-report.json").exists()


def test_dependency_check_uses_podman_when_docker_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _write_executable(
        fake_bin / "docker",
        "#!/usr/bin/env bash\nexit 1\n",
    )
    _write_executable(
        fake_bin / "podman",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
if [[ "${1:-}" == "run" ]]; then
  report_dir=""
  prev=""
  for arg in "$@"; do
    if [[ "$prev" == "-v" && "$arg" == *":/report" ]]; then
      report_dir="${arg%:/report}"
    fi
    prev="$arg"
  done
  mkdir -p "$report_dir"
  cat > "$report_dir/dependency-check-report.json" <<'JSON'
{"dependencies":[]}
JSON
  exit 0
fi
exit 1
""",
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    out_dir = tmp_path / "out"
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [
            str(SCRIPTS_DIR / "run_dependency_check.sh"),
            "--repo",
            str(repo),
            "--out",
            str(out_dir),
            "--project",
            "demo",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["mode"] == "podman"
    assert payload["runtime"] == "podman"
    assert "podman dependency-check completed" in payload["message"]
    assert (out_dir / "dependency-check-report.json").exists()


def test_dependency_check_dry_run_overwrites_report(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "dependency-check", "#!/usr/bin/env bash\nexit 0\n")

    repo = tmp_path / "repo"
    repo.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report_path = out_dir / "dependency-check-report.json"
    report_path.write_text('{"dependencies":[{"fileName":"stale"}]}', encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [
            str(SCRIPTS_DIR / "run_dependency_check.sh"),
            "--repo",
            str(repo),
            "--out",
            str(out_dir),
            "--project",
            "demo",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["scanInfo"]["engineVersion"] == "dry-run"
    assert report_payload["dependencies"] == []


def test_zap_dry_run_overwrites_report(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
exit 1
""",
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report_path = out_dir / "zap-report.json"
    report_path.write_text('{"site":[{"name":"stale","alerts":[{"pluginid":"1"}]}]}', encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [
            str(SCRIPTS_DIR / "run_zap_scan.sh"),
            "--target",
            "http://example.test",
            "--out",
            str(out_dir),
            "--mode",
            "baseline",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload == {"site": [{"name": "dry-run", "alerts": []}]}


def test_zap_dry_run_uses_podman_when_docker_missing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "docker",
        "#!/usr/bin/env bash\nexit 1\n",
    )
    _write_executable(
        fake_bin / "podman",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "info" ]]; then
  exit 0
fi
exit 1
""",
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    result = subprocess.run(
        [
            str(SCRIPTS_DIR / "run_zap_scan.sh"),
            "--target",
            "http://example.test",
            "--out",
            str(out_dir),
            "--mode",
            "baseline",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["runtime"] == "podman"
    assert "podman" in payload["message"]


def _fake_zap_runtime(tmp_path: Path, exit_code: int) -> dict[str, str]:
    """A podman stand-in whose `run` exits with `exit_code`, recording its argv."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _write_executable(fake_bin / "docker", "#!/usr/bin/env bash\nexit 1\n")
    _write_executable(
        fake_bin / "podman",
        f"""#!/usr/bin/env bash
if [[ "${{1:-}}" == "info" ]]; then
  exit 0
fi
printf '%s\\n' "$@" > "{tmp_path}/podman-argv"
exit {exit_code}
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    return env


def _run_zap(tmp_path: Path, env: dict[str, str], target: str) -> dict:
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            str(SCRIPTS_DIR / "run_zap_scan.sh"),
            "--target", target,
            "--out", str(out_dir),
            "--mode", "baseline",
        ],
        capture_output=True, text=True, env=env, check=False,
    )
    return json.loads(result.stdout)


def test_zap_findings_are_not_reported_as_a_scanner_failure(tmp_path: Path) -> None:
    """zap-baseline exits 1 on FAIL alerts and 2 on WARN alerts.

    Mapping those to `status: error` made the aggregate gate report the scanner
    as NOT CHECKED, which `--allow-degraded-pass` then turns into a PASS — so a
    scan that found real vulnerabilities surfaced as a clean degraded pass with
    zero findings. Only exit 3 means the scan did not run.
    """
    for rc in (0, 1, 2):
        payload = _run_zap(
            tmp_path, _fake_zap_runtime(tmp_path, rc), "http://example.test"
        )
        assert payload["status"] == "ok", f"exit {rc} must count as a completed scan"

    payload = _run_zap(tmp_path, _fake_zap_runtime(tmp_path, 3), "http://example.test")
    assert payload["status"] == "error", "exit 3 means the scan never ran"
    assert "failed to run" in payload["message"]


def test_zap_gets_host_networking_only_for_loopback_targets(tmp_path: Path) -> None:
    """A bridged container resolves `localhost` to itself, so a loopback target
    is unreachable without the host network namespace — measured as HTTP 000 via
    host-gateway versus 200 with --network=host. A remote target keeps its own
    namespace: sharing the host's loopback is the cost of scanning it, not a
    default.
    """
    argv_file = tmp_path / "podman-argv"

    for target in ("http://localhost:8080", "http://127.0.0.1:8080/x", "https://[::1]:9"):
        _run_zap(tmp_path, _fake_zap_runtime(tmp_path, 0), target)
        argv = argv_file.read_text(encoding="utf-8")
        assert "--network=host" in argv, f"{target} is loopback and needs host networking"

    _run_zap(tmp_path, _fake_zap_runtime(tmp_path, 0), "https://scan.example.com/app")
    argv = argv_file.read_text(encoding="utf-8")
    assert "--network=host" not in argv, "a remote target must stay isolated"


def test_zap_keeps_the_invoking_uid_under_podman(tmp_path: Path) -> None:
    """Rootless podman maps the image's `zap` user to a subuid that cannot write
    the bind mount, so the report job died with AccessDeniedException and left
    nothing to parse. Docker's default mapping already writes as the host user.
    """
    _run_zap(tmp_path, _fake_zap_runtime(tmp_path, 0), "http://example.test")
    argv = (tmp_path / "podman-argv").read_text(encoding="utf-8")
    assert "--userns=keep-id" in argv


def test_main_dry_run_does_not_overwrite_change_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    openspec_root = repo / "openspec"
    change_dir = openspec_root / "changes" / "demo-change"
    change_dir.mkdir(parents=True)
    change_report = change_dir / "security-review-report.md"
    original = "original artifact content\n"
    change_report.write_text(original, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "main.py"),
            "--repo",
            str(repo),
            "--change",
            "demo-change",
            "--openspec-root",
            str(openspec_root),
            "--profile-override",
            "docker-api",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 11, result.stderr
    payload = json.loads(result.stdout)
    assert payload["change_artifact"] == "skipped (dry-run)"
    assert change_report.read_text(encoding="utf-8") == original
