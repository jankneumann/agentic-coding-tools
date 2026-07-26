"""Registry integration + determinism (tasks 5.1-5.2).

Exercises all four canonical producers through the shared ``run_producer`` entry
point on one synthetic repository, with no network services, proving discovery,
canonical-result validation, independent execution, and byte-identical repeat
generation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import registry as reg
from _runtime import ProducerStatus
from contract import validate_producer_result

FULL_SHA = "e" * 40

ALL_IDS = (
    reg.API_CONTRACTS,
    reg.DECISIONS_TIMELINE,
    reg.DOCUMENTATION_INVENTORY,
    reg.OPENSPEC_PROJECTION,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # A skill (documentation input).
    sk = tmp_path / "skills/demo"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill\nuser_invocable: true\n---\n# demo\n",
        encoding="utf-8",
    )
    # A contract schema (api.contracts input).
    cd = tmp_path / "openspec/contracts/demo/schemas"
    cd.mkdir(parents=True)
    (cd / "d.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://x.dev/d.schema.json",
                "type": "object",
            }
        ),
        encoding="utf-8",
    )
    # A capability + a tagged decision (decisions input).
    (tmp_path / "openspec/specs/demo").mkdir(parents=True)
    (tmp_path / "openspec/specs/demo/spec.md").write_text(
        "# demo Specification\n\n## Requirements\n### Requirement: Base\n\nSHALL exist.\n",
        encoding="utf-8",
    )
    ch = tmp_path / "openspec/changes/add-demo"
    ch.mkdir(parents=True)
    (ch / "session-log.md").write_text(
        "# Session Log\n\n## Phase: Build (2026-02-01)\n\n### Decisions\n\n"
        "1. **Picked demo** `architectural: demo` — because reasons\n",
        encoding="utf-8",
    )
    return tmp_path


def test_producer_discovery_lists_four_sorted_with_owners():
    specs = reg.list_producers()
    assert [s.producer_id for s in specs] == sorted(ALL_IDS)
    for spec in specs:
        assert spec.owner  # every entry identifies its canonical owner
        assert spec.producer_version


def test_all_producers_run_and_validate_via_registry(repo: Path):
    for pid in ALL_IDS:
        result = reg.run_producer(pid, "generate", repo, FULL_SHA)
        validate_producer_result(result)
        assert result.producer_id == pid
        assert result.status is not ProducerStatus.FAILED


def test_generate_then_check_all_fresh(repo: Path):
    for pid in ALL_IDS:
        reg.run_producer(pid, "generate", repo, FULL_SHA)
    # Deterministic producers that write should now be fresh; openspec projection
    # has no active-vs-canonical drift because its delta was not archived — its
    # canonical spec still lacks the delta, so it legitimately reports pending.
    for pid in (reg.API_CONTRACTS, reg.DECISIONS_TIMELINE, reg.DOCUMENTATION_INVENTORY):
        result = reg.run_producer(pid, "check", repo, FULL_SHA)
        assert result.status is ProducerStatus.FRESH, pid


def test_repeat_generation_is_byte_identical_across_all(repo: Path):
    def snapshot() -> dict[str, bytes]:
        for pid in ALL_IDS:
            reg.run_producer(pid, "generate", repo, FULL_SHA)
        files = {}
        for p in sorted((repo / "docs").rglob("*.md")):
            files[str(p.relative_to(repo))] = p.read_bytes()
        return files

    first = snapshot()
    second = snapshot()
    assert first == second
    assert first  # at least one generated artifact exists


def test_producers_are_independent(repo: Path):
    # Running one producer does not require or perturb another: run decisions
    # alone, then documentation alone; each validates on its own.
    d = reg.run_producer(reg.DECISIONS_TIMELINE, "generate", repo, FULL_SHA)
    validate_producer_result(d)
    doc = reg.run_producer(reg.DOCUMENTATION_INVENTORY, "check", repo, FULL_SHA)
    validate_producer_result(doc)
