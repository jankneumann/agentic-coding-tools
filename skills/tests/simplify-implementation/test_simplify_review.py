"""Behavior tests for simplify/scripts/simplify_review.py.

The simplify review artifact is the contract between the Review role (which
writes it) and the Apply role (which consumes it). Two properties matter and
are pinned here:

1. `validate` accepts a conforming artifact and rejects a non-conforming one
   *naming which finding failed and where* — a reviewer whose artifact is
   silently accepted is worse than no reviewer.
2. `render-ledger` turns the reviewer's `prune` decisions into exactly the
   ledger `check_test_prune.py` already gates, so the implementer cannot
   justify a deletion the reviewer did not make.

The round-trip test drives both scripts against a synthetic git repo rather
than asserting on the ledger's formatting: the ledger's only job is to be
accepted by the gate.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "simplify-implementation" / "scripts"


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "openspec").is_dir():
            return candidate
    raise RuntimeError("could not locate the repo root (no openspec/ ancestor)")


REPO_ROOT = _repo_root()
CONTRACT_DIR = (
    REPO_ROOT / "openspec" / "changes" / "add-autopilot-simplify-phase" / "contracts"
)
CONTRACT_SCHEMA_PATH = CONTRACT_DIR / "events" / "simplify-review.schema.json"
VALID_FIXTURE_PATH = CONTRACT_DIR / "fixtures" / "simplify-review.valid.json"
INVALID_FIXTURE_PATH = CONTRACT_DIR / "fixtures" / "simplify-review.invalid.json"


def _load(module_file: str, name: str):
    path = SCRIPTS / module_file
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def simplify_review():
    return _load("simplify_review.py", "simplify_implementation_simplify_review")


@pytest.fixture(scope="module")
def check_test_prune():
    return _load("check_test_prune.py", "simplify_implementation_check_test_prune_rt")


# --- validate -----------------------------------------------------------


def test_valid_artifact_exits_zero(simplify_review):
    assert simplify_review.main(["validate", str(VALID_FIXTURE_PATH)]) == 0


def test_invalid_artifact_exits_two_and_names_the_finding(simplify_review, capsys):
    code = simplify_review.main(["validate", str(INVALID_FIXTURE_PATH)])
    assert code == 2
    err = capsys.readouterr().err
    assert "findings[0].prune.covered_by" in err, err
    assert "finding 1" in err, err


def test_missing_artifact_is_an_error(simplify_review, tmp_path):
    assert simplify_review.main(["validate", str(tmp_path / "absent.json")]) == 1


def test_json_output_lists_the_failing_finding(simplify_review, capsys):
    code = simplify_review.main(["validate", str(INVALID_FIXTURE_PATH), "--json"])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert [
        (e["finding_id"], e["path"]) for e in payload["errors"]
    ] == [(1, "findings[0].prune.covered_by")], payload


def test_json_output_on_a_valid_artifact_has_no_errors(simplify_review, capsys):
    code = simplify_review.main(["validate", str(VALID_FIXTURE_PATH), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"valid": True, "errors": []}


def test_bundled_contract_matches_the_change_contract():
    """The script's default schema is a copy; a drifted copy validates nothing."""
    bundled = SCRIPTS.parent / "schemas" / "simplify-review.schema.json"
    assert bundled.read_bytes() == CONTRACT_SCHEMA_PATH.read_bytes(), (
        f"{bundled} has drifted from {CONTRACT_SCHEMA_PATH}"
    )


# --- render-ledger round trip -------------------------------------------


THREE_TESTS = """\
from unittest.mock import Mock

from src.client import Client, build_fetcher


def test_fetch_calls_get_on_fetcher():
    client = Client(fetcher=Mock())
    client.fetch("/x")
    assert client.fetcher.get.called


def test_fetch_calls_parse_then_validate():
    assert Client.fetch.__code__.co_names[:2] == ("_parse", "_validate")


def test_fetch_returns_payload():
    assert Client(fetcher=build_fetcher()).fetch("/x") == {"ok": True}
"""

SURVIVING_TEST = """\
from src.client import Client, build_fetcher


def test_fetch_returns_payload():
    assert Client(fetcher=build_fetcher()).fetch("/x") == {"ok": True}
"""


@pytest.fixture
def pruned_repo(tmp_path: Path) -> dict[str, object]:
    """A repo where B0..B1 removes exactly the two tests the artifact prunes."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    for key, value in (("user.email", "test@example.com"), ("user.name", "Test")):
        subprocess.run(
            ["git", "config", key, value], cwd=repo, check=True, capture_output=True
        )
    (repo / "src" / "client.py").write_text(
        "def build_fetcher():\n    return object()\n\n\n"
        "class Client:\n    def __init__(self, fetcher=None):\n"
        "        self.fetcher = fetcher or build_fetcher()\n\n"
        "    def fetch(self, path):\n        return {'ok': True}\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_client.py").write_text(THREE_TESTS, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    b0 = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (repo / "tests" / "test_client.py").write_text(SURVIVING_TEST, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "test(client): remove implementation-coupled tests"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    b1 = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"repo": repo, "b0": b0, "b1": b1}


def _artifact(b0: str) -> dict:
    """Three findings: two prunes to render, one accepted finding to skip."""
    return {
        "review_type": "simplify",
        "target": "synthetic-client",
        "baseline_b0": b0[:8],
        "scope": {"files": 2, "lines": 40, "rule_of_500": "within"},
        "skipped_reason": None,
        "findings": [
            {
                "id": 1,
                "type": "test_quality",
                "criticality": "low",
                "severity": "optional",
                "axis": "correctness",
                "description": (
                    "Optional: test_fetch_calls_get_on_fetcher mocks Client's own "
                    "fetcher and asserts the mock was called."
                ),
                "disposition": "fix",
                "file_path": "tests/test_client.py",
                "test_id": "tests/test_client.py::test_fetch_calls_get_on_fetcher",
                "line_range": "5-8",
                "pattern": "self-mocking",
                "fence": {
                    "verdict": "remove",
                    "rationale": "Asserts the mocking library, not Client behavior.",
                    "evidence": ["blame 3f2a1c9"],
                },
                "prune": {"reason": "self-mocking", "covered_by": None},
            },
            {
                "id": 2,
                "type": "test_quality",
                "criticality": "low",
                "severity": "optional",
                "axis": "readability",
                "description": (
                    "Optional: test_fetch_calls_parse_then_validate asserts the "
                    "private call order inside Client.fetch."
                ),
                "disposition": "fix",
                "file_path": "tests/test_client.py",
                "test_id": "tests/test_client.py::test_fetch_calls_parse_then_validate",
                "line_range": "11-12",
                "pattern": "change-detector",
                "fence": {
                    "verdict": "remove",
                    "rationale": "Rewritten on every refactor of fetch().",
                    "evidence": ["blame 9c0b114"],
                },
                "prune": {
                    "reason": "change-detector",
                    "covered_by": "tests/test_client.py::test_fetch_returns_payload",
                },
            },
            {
                "id": 3,
                "type": "test_quality",
                "criticality": "low",
                "severity": "fyi",
                "axis": "correctness",
                "description": (
                    "FYI: test_fetch_returns_payload is the surviving state-based pin."
                ),
                "disposition": "accept",
                "file_path": "tests/test_client.py",
                "test_id": "tests/test_client.py::test_fetch_returns_payload",
                "pattern": "duplicative",
                "fence": {
                    "verdict": "keep",
                    "rationale": "Only remaining pin on fetch()'s payload.",
                },
            },
        ],
    }


def test_rendered_ledger_is_accepted_by_the_prune_gate(
    simplify_review, check_test_prune, pruned_repo, tmp_path
):
    """The reviewer's prune decisions, rendered, must clear the gate as written."""
    artifact_path = tmp_path / "simplify-review.json"
    artifact_path.write_text(json.dumps(_artifact(pruned_repo["b0"])), encoding="utf-8")
    assert simplify_review.main(["validate", str(artifact_path)]) == 0

    ledger = tmp_path / "test-prune-ledger.md"
    assert (
        simplify_review.main(
            ["render-ledger", str(artifact_path), "--out", str(ledger)]
        )
        == 0
    )

    entries, errors = check_test_prune.parse_ledger(ledger.read_text(encoding="utf-8"))
    assert errors == []
    assert [e.target for e in entries] == [
        "tests/test_client.py::test_fetch_calls_get_on_fetcher",
        "tests/test_client.py::test_fetch_calls_parse_then_validate",
    ], "accepted findings must not produce a ledger entry"

    result = check_test_prune.evaluate(
        pruned_repo["repo"], pruned_repo["b0"], pruned_repo["b1"], ledger
    )
    assert result.clean is True, result


def test_render_ledger_reports_a_missing_artifact(simplify_review, tmp_path):
    assert (
        simplify_review.main(["render-ledger", str(tmp_path / "absent.json")]) == 1
    )
