"""Tests for scripts/run_architecture.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import run_architecture


def _refresh_script_path() -> str:
    return str((Path(__file__).resolve().parents[1] / "refresh_architecture.sh").resolve())


def test_main_passes_target_env_and_overrides(tmp_path: Path) -> None:
    """Wrapper should run refresh script in target dir with expected env vars."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        rc = run_architecture.main([
            "--target-dir", str(target),
            "--python-src-dir", "app",
            "--ts-src-dir", "frontend",
            "--migrations-dir", "db/migrations",
            "--arch-dir", "docs/architecture-analysis",
            "--python", "python3.11",
        ])

    assert rc == 0
    args, kwargs = mock_run.call_args
    assert args[0] == ["bash", _refresh_script_path()]
    assert kwargs["cwd"] == target.resolve()

    env = kwargs["env"]
    assert env["SCRIPTS_DIR"] == str((Path(__file__).resolve().parents[1]).resolve())
    assert env["PYTHON_SRC_DIR"] == "app"
    assert env["TS_SRC_DIR"] == "frontend"
    assert env["MIGRATIONS_DIR"] == "db/migrations"
    assert env["ARCH_DIR"] == "docs/architecture-analysis"
    assert env["PYTHON"] == "python3.11"


def test_main_quick_adds_flag(tmp_path: Path) -> None:
    """--quick should append the quick flag for refresh_architecture.sh."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        rc = run_architecture.main([
            "--target-dir", str(target),
            "--quick",
        ])

    assert rc == 0
    args, _ = mock_run.call_args
    assert args[0] == ["bash", _refresh_script_path(), "--quick"]


def test_main_returns_child_exit_code(tmp_path: Path) -> None:
    """Wrapper should return refresh script exit code."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=17)
        rc = run_architecture.main(["--target-dir", str(target)])

    assert rc == 17


def test_main_missing_target_returns_error_code(tmp_path: Path) -> None:
    """Missing target directory should fail before spawning subprocess."""
    missing = tmp_path / "missing"

    with patch("run_architecture.subprocess.run") as mock_run:
        rc = run_architecture.main(["--target-dir", str(missing)])

    assert rc == 2
    mock_run.assert_not_called()


def test_main_launch_failure_returns_error_code(tmp_path: Path) -> None:
    """Launcher errors should map to non-zero wrapper failure."""
    target = tmp_path / "target"
    target.mkdir()

    with patch("run_architecture.subprocess.run") as mock_run:
        mock_run.side_effect = OSError("exec failed")
        rc = run_architecture.main(["--target-dir", str(target)])

    assert rc == 1


def _init_repo(root: Path) -> None:
    import subprocess

    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "app.py").write_text("print('hi')\n")
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
    ):
        subprocess.run(args, cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=str(root), check=True, capture_output=True
    )


def _fake_pipeline(fail: bool = False):
    """Return a ``_run_pipeline`` stand-in that writes staged artifacts."""

    def _runner(target_dir: Path, env: dict, quick: bool) -> int:
        if fail:
            return 3
        staging = Path(env["ARCH_DIR"])
        (staging / "views").mkdir(parents=True, exist_ok=True)
        (staging / "architecture.graph.json").write_text('{"nodes": [], "edges": []}\n')
        (staging / "architecture.summary.json").write_text('{"summary": "ok"}\n')
        (staging / "views" / "overview.md").write_text("# overview\n")
        return 0

    return _runner


class TestCheckMode:
    def test_check_missing_provenance_returns_nonzero(self, tmp_path: Path, capsys) -> None:
        _init_repo(tmp_path)
        rc = run_architecture.main(["--target-dir", str(tmp_path), "--check"])
        assert rc == 1
        report = json.loads(capsys.readouterr().out)
        assert report["status"] == "invalid"

    def test_check_is_read_only_and_reports_fresh(self, tmp_path: Path, capsys) -> None:
        _init_repo(tmp_path)
        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            assert run_architecture.main(["--target-dir", str(tmp_path), "--staged"]) == 0
        capsys.readouterr()
        rc = run_architecture.main(["--target-dir", str(tmp_path), "--check"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["status"] == "fresh"


class TestStagedGeneration:
    def test_staged_promotes_and_writes_provenance(self, tmp_path: Path, capsys) -> None:
        _init_repo(tmp_path)
        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            rc = run_architecture.main(["--target-dir", str(tmp_path), "--staged"])
        assert rc == 0
        arch = tmp_path / "docs/architecture-analysis"
        assert (arch / "architecture.graph.json").is_file()
        assert (arch / "architecture.provenance.json").is_file()
        # Staging directory is cleaned up.
        assert not (tmp_path / ".architecture-staging").exists()
        report = json.loads(capsys.readouterr().out)
        assert report["status"] == "generated"

    def test_repeat_staged_refresh_is_byte_identical(self, tmp_path: Path) -> None:
        # Scenario architecture-refresh.9
        _init_repo(tmp_path)
        prov_path = tmp_path / "docs/architecture-analysis/architecture.provenance.json"
        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            run_architecture.main(["--target-dir", str(tmp_path), "--staged"])
            first = prov_path.read_bytes()
            graph_first = (tmp_path / "docs/architecture-analysis/architecture.graph.json").read_bytes()
            run_architecture.main(["--target-dir", str(tmp_path), "--staged"])
        assert prov_path.read_bytes() == first
        assert (
            tmp_path / "docs/architecture-analysis/architecture.graph.json"
        ).read_bytes() == graph_first

    def test_staged_flags_artifacts_it_did_not_regenerate(self, tmp_path: Path, capsys) -> None:
        """Issue #382: promotion copies but never deletes.

        An artifact an optional stage failed to produce survives in the output
        directory at its old bytes. Provenance is built by scanning that
        directory, so it recorded the leftover as though this revision had
        generated it — a stale artifact under a fresh ``source_revision``, which
        no downstream digest check can detect.
        """
        _init_repo(tmp_path)
        arch = tmp_path / "docs/architecture-analysis"
        (arch / "views").mkdir(parents=True, exist_ok=True)
        leftover = arch / "treesitter_enrichment.json"
        leftover.write_text('{"from": "an older revision"}\n')
        gitkeep = arch / "views" / ".gitkeep"
        gitkeep.write_text("")

        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            assert run_architecture.main(["--target-dir", str(tmp_path), "--staged"]) == 0

        doc = json.loads((arch / "architecture.provenance.json").read_text())
        flags = {a["path"]: a["carried_over"] for a in doc["artifacts"]}
        assert flags["docs/architecture-analysis/architecture.graph.json"] is False
        assert flags["docs/architecture-analysis/views/overview.md"] is False
        assert flags["docs/architecture-analysis/treesitter_enrichment.json"] is True
        assert flags["docs/architecture-analysis/views/.gitkeep"] is True

        # Flagging, not deleting: an optional stage that skipped must not cost
        # the repository its last good copy, and .gitkeep only ever lives here.
        assert leftover.read_text() == '{"from": "an older revision"}\n'
        assert gitkeep.is_file()

        report = json.loads(capsys.readouterr().out)
        assert report["carried_over"] == [
            "docs/architecture-analysis/treesitter_enrichment.json",
            "docs/architecture-analysis/views/.gitkeep",
        ]

    def test_pipeline_failure_preserves_last_known_good(self, tmp_path: Path) -> None:
        # Scenario architecture-refresh.8
        _init_repo(tmp_path)
        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            run_architecture.main(["--target-dir", str(tmp_path), "--staged"])
        arch = tmp_path / "docs/architecture-analysis"
        good_graph = (arch / "architecture.graph.json").read_bytes()
        good_prov = (arch / "architecture.provenance.json").read_bytes()
        # A later failing refresh must not replace the committed set.
        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline(fail=True)):
            rc = run_architecture.main(["--target-dir", str(tmp_path), "--staged"])
        assert rc == 3
        assert (arch / "architecture.graph.json").read_bytes() == good_graph
        assert (arch / "architecture.provenance.json").read_bytes() == good_prov
        assert not (tmp_path / ".architecture-staging").exists()


def test_refresh_script_resolves_its_tools_outside_source_checkout(tmp_path: Path) -> None:
    """Direct invocation must find shipped analyzers from an arbitrary consumer cwd."""
    import os
    import subprocess

    for relative in ("src", "web", "database/migrations"):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["AUTO_INSTALL_DEPS"] = "false"
    result = subprocess.run(
        ["bash", _refresh_script_path(), "--quick"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert "Python analyzer script not found" not in output
    assert "Postgres analyzer script not found" not in output


def _tree_digest(root: Path) -> str:
    """Digest every byte under *root*, path-sensitively.

    Ensure mode's "writes nothing" claim is about bytes, not about mtimes or
    about which files a reviewer happened to open, so the assertion compares a
    digest of the whole artifact directory rather than a chosen file.
    """
    import hashlib

    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _forbidden_pipeline(target_dir: Path, env: dict, quick: bool) -> int:
    raise AssertionError("staged refresh ran when the checkout was already fresh")


class TestEnsureMode:
    """Spec: architecture-refresh — Ensure mode composes check and staged refresh."""

    def _make_fresh(self, repo: Path) -> None:
        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            assert run_architecture.main(["--target-dir", str(repo), "--staged"]) == 0

    def test_ensure_leaves_fresh_artifacts_untouched(self, tmp_path: Path, capsys) -> None:
        # Scenario: Fresh artifacts are left untouched
        _init_repo(tmp_path)
        self._make_fresh(tmp_path)
        arch = tmp_path / "docs/architecture-analysis"
        before = _tree_digest(arch)
        capsys.readouterr()

        with patch.object(run_architecture, "_run_pipeline", _forbidden_pipeline):
            rc = run_architecture.main(["--target-dir", str(tmp_path), "--ensure"])

        assert rc == 0
        assert _tree_digest(arch) == before
        assert json.loads(capsys.readouterr().out)["status"] == "fresh"

    def test_ensure_is_idempotent(self, tmp_path: Path) -> None:
        # Scenario: Ensure is idempotent
        _init_repo(tmp_path)
        arch = tmp_path / "docs/architecture-analysis"

        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            assert run_architecture.main(["--target-dir", str(tmp_path), "--ensure"]) == 0
        after_first = _tree_digest(arch)
        prov_first = (arch / "architecture.provenance.json").read_bytes()

        # The second run must do no work at all, not merely reproduce the bytes.
        with patch.object(run_architecture, "_run_pipeline", _forbidden_pipeline):
            assert run_architecture.main(["--target-dir", str(tmp_path), "--ensure"]) == 0

        assert _tree_digest(arch) == after_first
        assert (arch / "architecture.provenance.json").read_bytes() == prov_first

    def test_ensure_regenerates_when_provenance_missing(self, tmp_path: Path, capsys) -> None:
        # Scenario: Stale artifacts are regenerated (missing provenance)
        _init_repo(tmp_path)
        arch = tmp_path / "docs/architecture-analysis"
        assert not arch.exists()

        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            rc = run_architecture.main(["--target-dir", str(tmp_path), "--ensure"])

        assert rc == 0
        assert (arch / "architecture.provenance.json").is_file()
        # One JSON document on stdout either way: when a refresh happens the
        # check report is the reason (stderr) and the staged report is the answer.
        captured = capsys.readouterr()
        assert json.loads(captured.out)["status"] == "generated"
        reason, _ = json.JSONDecoder().raw_decode(captured.err)
        assert reason["status"] == "invalid"

        assert run_architecture.main(["--target-dir", str(tmp_path), "--check"]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "fresh"

    def test_ensure_regenerates_when_inputs_changed(self, tmp_path: Path, capsys) -> None:
        # Scenario: Stale artifacts are regenerated (stale provenance)
        import subprocess

        _init_repo(tmp_path)
        self._make_fresh(tmp_path)
        (tmp_path / "src" / "app.py").write_text("print('a real change')\n")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "change"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )
        capsys.readouterr()
        assert run_architecture.main(["--target-dir", str(tmp_path), "--check"]) == 1
        capsys.readouterr()

        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline()):
            assert run_architecture.main(["--target-dir", str(tmp_path), "--ensure"]) == 0

        capsys.readouterr()
        assert run_architecture.main(["--target-dir", str(tmp_path), "--check"]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "fresh"

    def test_ensure_failed_refresh_preserves_last_known_good(self, tmp_path: Path) -> None:
        # Scenario: Failed regeneration preserves last known-good
        import subprocess

        _init_repo(tmp_path)
        self._make_fresh(tmp_path)
        arch = tmp_path / "docs/architecture-analysis"
        good = _tree_digest(arch)
        good_prov = (arch / "architecture.provenance.json").read_bytes()

        (tmp_path / "src" / "app.py").write_text("print('stale now')\n")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "change"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        with patch.object(run_architecture, "_run_pipeline", _fake_pipeline(fail=True)):
            rc = run_architecture.main(["--target-dir", str(tmp_path), "--ensure"])

        assert rc == 3
        assert _tree_digest(arch) == good
        assert (arch / "architecture.provenance.json").read_bytes() == good_prov
        assert not (tmp_path / ".architecture-staging").exists()
