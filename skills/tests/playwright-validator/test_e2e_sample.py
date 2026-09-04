"""End-to-end sample fixture test for the Playwright validator.

Exercises the full pipeline against
``packages/gen-eval/tests/fixtures/sample-descriptor.yaml`` per the spec scenario
"Sample frontend exercise validates the full path".

Skipped when ``npx`` is not on PATH so CI without Node stays green; the
unit tests in the sibling files cover the same logic without the CLI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cli import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = REPO_ROOT / "packages" / "gen-eval" / "tests" / "fixtures"
DESCRIPTOR = _FIXTURES / "sample-descriptor.yaml"
SPECS_DIR = _FIXTURES / "sample-frontend" / "specs"


def test_dry_run_emits_test_script(tmp_path: Path):
    """Even without npx installed, --dry-run must produce a .spec.ts file."""
    output = tmp_path / "out"
    test_dir = tmp_path / "tests"
    rc = cli_main(
        [
            "sample-frontend-demo",
            "--descriptor",
            str(DESCRIPTOR),
            "--specs-dir",
            str(SPECS_DIR),
            "--output-dir",
            str(output),
            "--test-dir",
            str(test_dir),
            "--dry-run",
        ]
    )
    assert rc == 0
    spec_files = list(test_dir.glob("*.spec.ts"))
    assert len(spec_files) == 1
    text = spec_files[0].read_text()
    # WHEN steps -> Playwright actions; THEN steps -> assertions.
    assert "page.fill" in text
    assert "page.click" in text
    assert "toBeVisible" in text
    assert "toContainText" in text
    # Selectors expanded via the descriptor's selectors map.
    assert "#username" in text
    assert "#login-button" in text
    assert "#welcome" in text
    # And a playwright.config.ts was written.
    assert (test_dir / "playwright.config.ts").exists()


def test_invalid_change_id_returns_64(tmp_path: Path):
    rc = cli_main(["../bad/id", "--descriptor", str(DESCRIPTOR), "--dry-run"])
    assert rc == 64


def test_missing_descriptor_returns_2(tmp_path: Path):
    rc = cli_main(
        [
            "sample-frontend-demo",
            "--descriptor",
            str(tmp_path / "nope.yaml"),
            "--dry-run",
        ]
    )
    assert rc == 2


@pytest.mark.skipif(
    shutil.which("npx") is None,
    reason="requires npx playwright",
)
def test_full_pipeline_runs_against_sample_frontend(tmp_path: Path):
    """Optional full run; only executes when Node + Playwright are installed.

    Per the spec scenario, this verifies:

    - ``ss -tlnp`` would show 127.0.0.1 binding (we trust the descriptor here).
    - The generated test passes ``--dry-run``.
    - ``findings-playwright.json`` is emitted and schema-valid.
    """
    # Sanity: Playwright CLI version probe.
    #
    # Every failure mode here means the same thing — Playwright is not usable
    # in this environment — so every one of them has to skip, not fail. A bare
    # `returncode != 0` check only covers the case where npx answers quickly.
    # When Playwright is absent, npx instead tries to *fetch* it, so the probe
    # hangs and raises TimeoutExpired, which propagated out and failed the test
    # on a required check for every branch in the repo (main included) whenever
    # the npm registry was slow. OSError covers npx vanishing between the
    # skipif above and this call.
    try:
        probe = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("npx playwright probe timed out — treating Playwright as unavailable")
    except OSError as exc:
        pytest.skip(
            f"npx playwright probe could not run ({exc}) — treating Playwright as unavailable"
        )
    if probe.returncode != 0:
        pytest.skip("npx playwright not available")

    output = tmp_path / "out"
    test_dir = tmp_path / "tests"
    rc = cli_main(
        [
            "sample-frontend-demo",
            "--descriptor",
            str(DESCRIPTOR),
            "--specs-dir",
            str(SPECS_DIR),
            "--output-dir",
            str(output),
            "--test-dir",
            str(test_dir),
        ]
    )
    findings_file = output / "findings-playwright.json"
    # Pipeline emits findings file (rc may be 0 or 1 depending on test outcome).
    if rc == 127:
        pytest.skip("playwright CLI degraded to missing during run")
    assert findings_file.exists(), "expected findings-playwright.json to be emitted"
    schema = json.loads(
        (REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json").read_text()
    )
    import jsonschema

    jsonschema.validate(instance=json.loads(findings_file.read_text()), schema=schema)


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired(cmd=["npx", "playwright", "--version"], timeout=30),
        FileNotFoundError(2, "No such file or directory: 'npx'"),
        PermissionError(13, "Permission denied: 'npx'"),
    ],
    ids=["timeout", "missing", "not-executable"],
)
def test_unusable_playwright_probe_skips_instead_of_failing(monkeypatch, tmp_path, failure):
    """An unusable Playwright probe must skip, never fail.

    Regression guard: the probe used to check only ``returncode``, so a
    ``TimeoutExpired`` — which is exactly what npx raises while trying to fetch
    a Playwright it does not have — escaped as a test failure. Because
    ``test-infra-skills`` is a required status check, that turned a slow npm
    registry into a merge block for every branch in the repository.
    """

    def _raise(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", _raise)
    with pytest.raises(pytest.skip.Exception):
        test_full_pipeline_runs_against_sample_frontend(tmp_path)
