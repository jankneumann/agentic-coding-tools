"""End-to-end sample fixture test for the Playwright validator.

Exercises the full pipeline against
``packages/gen-eval/tests/fixtures/sample-frontend/`` per the spec scenario
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
_SAMPLE_FIXTURE = (
    REPO_ROOT / "packages" / "gen-eval" / "tests" / "fixtures" / "sample-frontend"
)
DESCRIPTOR = _SAMPLE_FIXTURE / "descriptor.yaml"
SPECS_DIR = _SAMPLE_FIXTURE / "specs"


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
    # `--no-install` matters. A bare `npx playwright` on a machine without
    # Playwright installed silently fetches it from the registry, which can
    # outrun the timeout below and surface as a TimeoutExpired error rather
    # than the intended skip — turning "Playwright isn't installed here" into
    # a red build. With --no-install the probe fails immediately instead.
    try:
        probe = subprocess.run(
            ["npx", "--no-install", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        pytest.skip(f"npx playwright probe failed: {exc}")
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
