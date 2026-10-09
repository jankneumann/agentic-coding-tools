"""The gen-eval scenario pack (G.1, G.2, G.3; design D3, D8).

gen-eval silently skips a scenario that fails to load, so the pack run also asserts that
every scenario in the pack actually ran and that "Invalid scenario" never appears.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parent
EVALUATION = HARNESS / "evaluation"
SCENARIO_DIR = EVALUATION / "scenarios"
GEN_EVAL = Path(sys.executable).parent / "gen-eval"
EXPECTED_NAMED = {
    "same-requirement-collision",
    "different-requirement-control",
    "memory-store-blocked-dependency",
    "independent-principals-control",
}


def _declared_ids(scenario_dir: Path) -> list[str]:
    ids: list[str] = []
    for path in sorted(scenario_dir.glob("*.yaml")):
        ids.extend(s["id"] for s in yaml.safe_load(path.read_text()))
    return ids


def _run_pack(evaluation: Path, out: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        [str(HARNESS / "bin"), str(Path(sys.executable).parent), env.get("PATH", "")]
    )
    env.pop("COORDINATION_API_URL", None)
    return subprocess.run(
        [str(GEN_EVAL), "--descriptor", str(evaluation / "descriptor.yaml"),
         "--fail-threshold", "1.0", "--output-dir", str(out)],
        cwd=HARNESS, env=env, capture_output=True, text=True,
    )


def _report(out: Path) -> dict:
    return json.loads((out / "gen-eval-report.json").read_text())


def test_pack_declares_the_four_named_scenarios():
    assert EXPECTED_NAMED <= set(_declared_ids(SCENARIO_DIR))
    ids = _declared_ids(SCENARIO_DIR)
    assert len(ids) == len(set(ids))


def test_the_pack_passes_against_the_baseline(tmp_path):
    proc = _run_pack(EVALUATION, tmp_path / "out")
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "Invalid scenario" not in combined
    report = _report(tmp_path / "out")
    declared = _declared_ids(SCENARIO_DIR)
    assert report["total_scenarios"] == len(declared)
    assert report["passed"] == len(declared)
    assert report["failed"] == 0 and report["errors"] == 0 and report["skipped"] == 0
    ran = {v.get("scenario_id") for v in report["verdicts"]}
    assert EXPECTED_NAMED <= ran


def test_a_changed_measurement_fails_the_pack(tmp_path):
    pack = tmp_path / "evaluation"
    shutil.copytree(EVALUATION, pack)
    # The descriptor's contract path is relative to its own location; point the copy home.
    descriptor = yaml.safe_load((pack / "descriptor.yaml").read_text())
    descriptor["contract"] = str(
        (EVALUATION / descriptor["contract"]).resolve()
    )
    (pack / "descriptor.yaml").write_text(yaml.safe_dump(descriptor, sort_keys=False))
    target = pack / "scenarios" / "collision.yaml"
    text = target.read_text()
    flipped = text.replace(
        "          collision_detected: false\n          probes: []",
        "          collision_detected: true\n          probes: []",
        1,
    )
    assert flipped != text
    target.write_text(flipped)

    proc = _run_pack(pack, tmp_path / "out")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    report = _report(tmp_path / "out")
    failed = [v for v in report["verdicts"] if v.get("status") != "pass"]
    assert [v["scenario_id"] for v in failed] == ["same-requirement-collision"]


def test_every_pinned_baseline_names_the_item_that_flips_it():
    pins = {"collision_detected": "ri-06", "blocked_ticks": "ri-11"}
    checked = 0
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        text = path.read_text()
        comments = "\n".join(re.findall(r"#.*", text))
        for key, item in pins.items():
            if re.search(rf"^\s*{key}:", text, re.MULTILINE):
                checked += 1
                assert item in comments, f"{path.name} pins {key} without naming {item}"
    assert checked >= 2
