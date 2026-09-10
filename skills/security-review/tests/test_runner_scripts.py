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
    # These tests are about runtime selection, not the database. Seed a fresh one
    # so they reach the code they are actually asserting on rather than stopping
    # at the freshness gate.
    seeded = tmp_path / "nvd"
    _seed_db(seeded, age_days=0)
    env["DEPENDENCY_CHECK_DATA_DIR"] = str(seeded)

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
    # These tests are about runtime selection, not the database. Seed a fresh one
    # so they reach the code they are actually asserting on rather than stopping
    # at the freshness gate.
    seeded = tmp_path / "nvd"
    _seed_db(seeded, age_days=0)
    env["DEPENDENCY_CHECK_DATA_DIR"] = str(seeded)

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


# ---------------------------------------------------------------------------
# NVD database lifecycle — seeding, freshness, and refusing to fake a scan
# ---------------------------------------------------------------------------


def _depcheck(tmp_path: Path, args: list[str], env_extra: dict[str, str] | None = None,
              runtime_exit: int = 0) -> tuple[dict, int]:
    """Invoke run_dependency_check.sh with a stubbed container runtime."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    # No native dependency-check on PATH, so the container path is taken.
    _write_executable(fake_bin / "docker", "#!/usr/bin/env bash\nexit 1\n")
    _write_executable(
        fake_bin / "podman",
        f"""#!/usr/bin/env bash
if [[ "${{1:-}}" == "info" ]]; then
  exit 0
fi
printf '%s\\n' "$@" > "{tmp_path}/podman-argv"
exit {runtime_exit}
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env.pop("NVD_API_KEY", None)
    env.update(env_extra or {})
    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "run_dependency_check.sh"), *args],
        capture_output=True, text=True, env=env, check=False,
    )
    return json.loads(result.stdout), result.returncode


def _seed_db(data_dir: Path, age_days: int) -> None:
    """A database file whose mtime is `age_days` old."""
    import time

    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "odc.mv.db"
    db.write_text("not a real H2 file", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(db, (stamp, stamp))


def test_a_stale_database_is_not_reported_as_a_clean_scan(tmp_path: Path) -> None:
    """The finding that motivated all of this.

    dependency-check scans with --noupdate. Against an absent or months-old CVE
    database it completes happily and reports nothing, which is byte-identical
    to a genuinely clean scan. Since the aggregate gate turns a scanner error
    into NOT CHECKED and `--allow-degraded-pass` turns NOT CHECKED into a PASS,
    the difference between "no known vulnerabilities" and "no idea" has to be
    made here or it is never made at all.
    """
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=30)

    payload, rc = _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir), "DEPENDENCY_CHECK_MAX_DB_AGE_DAYS": "7"},
    )
    assert payload["status"] == "error"
    assert "30 day(s) old" in payload["message"]
    assert rc == 4
    # And it must not have run a scan at all: a stale scan produces a report
    # file, and a report file is what the parser would happily read as clean.
    assert not (tmp_path / "podman-argv").exists(), "no container should have run"


def test_a_fresh_database_lets_the_scan_proceed(tmp_path: Path) -> None:
    """The floor must not be a blanket refusal — a seeded database scans."""
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=1)

    _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir), "DEPENDENCY_CHECK_MAX_DB_AGE_DAYS": "7"},
    )
    argv = (tmp_path / "podman-argv").read_text(encoding="utf-8")
    assert "--scan" in argv, "a fresh database must reach the scanner"
    assert "--noupdate" in argv, "scanning must never talk to NVD"
    assert f"{data_dir}:/usr/share/dependency-check/data" in argv, (
        "the seeded database must be mounted, or the scan sees an empty one"
    )


def test_an_absent_database_names_its_remedy(tmp_path: Path) -> None:
    payload, rc = _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(tmp_path / "nowhere")},
    )
    assert payload["status"] == "error"
    assert "make security-seed-nvd" in payload["message"]
    assert rc == 4


def test_the_update_is_the_only_mode_that_talks_to_nvd(tmp_path: Path) -> None:
    """--updateonly with a key; and scanning never carries the key at all."""
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=1)

    _depcheck(
        tmp_path, ["--update-nvd"],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir), "NVD_API_KEY": "test-key-not-real"},
    )
    argv = (tmp_path / "podman-argv").read_text(encoding="utf-8")
    assert "--updateonly" in argv
    assert "--nvdApiKey" in argv
    assert "--noupdate" not in argv, "the update must not disable updating"

    (tmp_path / "podman-argv").unlink()
    _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir), "NVD_API_KEY": "test-key-not-real"},
    )
    scan_argv = (tmp_path / "podman-argv").read_text(encoding="utf-8")
    assert "--nvdApiKey" not in scan_argv, (
        "a scan must not carry the credential; only the seeding run needs it"
    )
    assert "test-key-not-real" not in scan_argv


def test_the_update_refuses_without_a_key_rather_than_rate_limiting(tmp_path: Path) -> None:
    payload, rc = _depcheck(
        tmp_path, ["--update-nvd"], {"DEPENDENCY_CHECK_DATA_DIR": str(tmp_path / "nvd")}
    )
    assert payload["status"] == "error"
    assert "NVD_API_KEY is not set" in payload["message"]
    assert rc == 4
    assert not (tmp_path / "podman-argv").exists(), "must not attempt the download"


def test_nvd_status_exit_code_can_gate_a_refresh(tmp_path: Path) -> None:
    """--nvd-status exits non-zero when stale, so a cron can act on it."""
    data_dir = tmp_path / "nvd"

    payload, rc = _depcheck(tmp_path, ["--nvd-status"],
                            {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir)})
    assert (payload["status"], rc) == ("error", 4)

    _seed_db(data_dir, age_days=30)
    payload, rc = _depcheck(tmp_path, ["--nvd-status"],
                            {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir),
                             "DEPENDENCY_CHECK_MAX_DB_AGE_DAYS": "7"})
    assert (payload["status"], rc, payload["age_days"]) == ("error", 4, 30)

    _seed_db(data_dir, age_days=2)
    payload, rc = _depcheck(tmp_path, ["--nvd-status"],
                            {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir),
                             "DEPENDENCY_CHECK_MAX_DB_AGE_DAYS": "7"})
    assert (payload["status"], rc, payload["age_days"]) == ("ok", 0, 2)


def test_the_freshness_floor_can_be_disabled_deliberately(tmp_path: Path) -> None:
    """0 means "I know, scan anyway" — an explicit choice, not the default."""
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=400)

    _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir), "DEPENDENCY_CHECK_MAX_DB_AGE_DAYS": "0"},
    )
    assert (tmp_path / "podman-argv").exists(), "floor 0 must let the scan run"


# ---------------------------------------------------------------------------
# Pinned scanner images
# ---------------------------------------------------------------------------

_RUNNERS = ("run_zap_scan.sh", "run_dependency_check.sh")


def test_no_runner_pulls_a_floating_tag(tmp_path: Path) -> None:
    """A scanner on `:stable` or `:latest` makes a verdict a function of *when*.

    The same reason `.openspec-version` is pinned at the repo root: a rule set
    that grew a new check overnight is indistinguishable from a regression you
    introduced, and neither can be bisected against. Matched on the image
    reference itself, so the prose in scanner-images.env explaining the policy
    does not trip it.
    """
    floating = ("ghcr.io/zaproxy/zaproxy:stable", "docker.io/owasp/dependency-check:latest")
    for runner in _RUNNERS:
        body = (SCRIPTS_DIR / runner).read_text(encoding="utf-8")
        for ref in floating:
            assert f"\n    {ref} " not in body and f'"{ref}"' not in body, (
                f"{runner} pulls the floating tag {ref}; use scanner_image <NAME>"
            )
        assert "scanner_image " in body, f"{runner} must resolve through the pin file"


def test_every_pinned_image_carries_a_digest() -> None:
    """A tag with no digest is not a pin.

    The helper warns and falls back rather than failing, so that a half-finished
    bump is visible instead of silently reproducible-looking. This asserts the
    committed state is never that half-finished one.
    """
    env_file = SCRIPTS_DIR.parent / "scanner-images.env"
    pins: dict[str, dict[str, str]] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "_IMAGE_" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        name, _, kind = key.rpartition("_IMAGE_")
        pins.setdefault(name, {})[kind.lower()] = value.strip('"')

    assert pins, "scanner-images.env declares no pins"
    for name, fields in pins.items():
        assert fields.get("tag"), f"{name} has no tag"
        digest = fields.get("digest", "")
        assert digest.startswith("sha256:") and len(digest) == 71, (
            f"{name} has no usable digest ({digest!r}) — a tag alone is not a pin"
        )


def test_an_explicit_override_wins_over_the_pin(tmp_path: Path) -> None:
    """An operator testing an upstream fix must not have to edit the pin file."""
    script = tmp_path / "probe.sh"
    script.write_text(
        f'#!/usr/bin/env bash\nset -euo pipefail\n'
        f'source "{SCRIPTS_DIR}/scanner_images.sh"\n'
        f'scanner_image ZAP\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["ZAP_IMAGE"] = "localhost/zap:under-test"
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                         env=env, check=True).stdout.strip()
    assert out == "localhost/zap:under-test"

    env.pop("ZAP_IMAGE")
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                         env=env, check=True).stdout.strip()
    assert out.startswith("ghcr.io/zaproxy/zaproxy:stable@sha256:"), out


def _write_report(out_dir: Path, dependencies: list | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dependency-check-report.json").write_text(
        json.dumps({"scanInfo": {}, "dependencies": dependencies or []}), encoding="utf-8"
    )


def test_a_completed_scan_is_not_discarded_because_an_analyzer_failed(tmp_path: Path) -> None:
    """The finding that motivated this.

    On this repo's first real scan, NodeAuditAnalyzer took a 429 from
    registry.npmjs.org. dependency-check exited 14 having written a complete
    1.9 MB report naming 556 dependencies and a real moderate CVE
    (GHSA-82fw-gwwq-j7x9). The wrapper mapped any non-zero exit to `error`, the
    gate turned that into NOT CHECKED, and `--allow-degraded-pass` turned NOT
    CHECKED into a clean PASS. A scan that found a real vulnerability reported as
    a pass with zero findings.
    """
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=1)
    out_dir = tmp_path / "out"

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    _write_executable(fake_bin / "docker", "#!/usr/bin/env bash\nexit 1\n")
    # A runtime that writes a real report and then exits non-zero, exactly as
    # dependency-check does when one analyzer fails.
    _write_executable(
        fake_bin / "podman",
        f"""#!/usr/bin/env bash
if [[ "${{1:-}}" == "info" ]]; then exit 0; fi
mkdir -p "{out_dir}"
cat > "{out_dir}/dependency-check-report.json" <<'JSON'
{{"scanInfo": {{}}, "dependencies": [{{"fileName": "vitest:3.2.7", "vulnerabilities": [{{"name": "GHSA-82fw-gwwq-j7x9", "severity": "moderate"}}]}}]}}
JSON
exit 14
""",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["DEPENDENCY_CHECK_DATA_DIR"] = str(data_dir)

    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "run_dependency_check.sh"),
         "--repo", str(tmp_path), "--out", str(out_dir)],
        capture_output=True, text=True, env=env, check=False,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok", (
        "a scan that wrote a report ran; only a scan that wrote nothing did not"
    )
    assert "exit 14" in payload["message"] and "partial" in payload["message"], (
        "the degraded coverage must be stated, not silently upgraded to a clean pass"
    )


def test_a_scan_that_wrote_nothing_is_still_an_error(tmp_path: Path) -> None:
    """The control. Without it the rule above could pass by calling everything ok."""
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=1)
    payload, _ = _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir)},
        runtime_exit=14,
    )
    assert payload["status"] == "error"
    assert "failed to run" in payload["message"]


def test_the_scan_excludes_install_and_worktree_paths(tmp_path: Path) -> None:
    """`.git-worktrees/` holds duplicate manifests at paths nothing should report.

    On the first real scan, both findings were attributed to a worktree copy
    rather than to `apps/kanban-viz/package-lock.json` where the vulnerable
    dependency actually lives — and the duplicate lockfiles multiplied npm audit
    calls until the registry returned 429, which is what produced the non-zero
    exit in the first place. Excluding install state removed 554 of 556 scanned
    paths (313 .uv-cache wheels, 241 node_modules, 2 worktree copies) and lost
    no findings: those are local build artifacts, not repository content.
    """
    data_dir = tmp_path / "nvd"
    _seed_db(data_dir, age_days=1)
    _depcheck(
        tmp_path,
        ["--repo", str(tmp_path), "--out", str(tmp_path / "out")],
        {"DEPENDENCY_CHECK_DATA_DIR": str(data_dir)},
    )
    argv = (tmp_path / "podman-argv").read_text(encoding="utf-8")
    for pattern in (
        "**/.git-worktrees/**",
        "**/node_modules/**",
        "**/.venv/**",
        "**/.uv-cache/**",
    ):
        assert pattern in argv, f"{pattern} is not excluded from the scan"

