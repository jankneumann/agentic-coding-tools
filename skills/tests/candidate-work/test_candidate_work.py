"""Contract tests for the shared candidate-work runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED = REPO_ROOT / "skills" / "shared"
FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(SHARED))

from candidate_work import (  # noqa: E402
    CandidateWorkCollisionError,
    CandidateWorkValidationError,
    canonical_candidate_work_bytes,
    load_candidate_work_files,
    validate_candidate_work_batch,
    write_candidate_work,
)


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture",
    ["bug-scrub.json", "improve-harness.json", "explore-feature.json", "mixed.json"],
)
def test_representative_batches_validate_against_the_canonical_schema(fixture: str) -> None:
    batch = _load(fixture)

    assert validate_candidate_work_batch(batch) == batch


def test_canonical_bytes_are_sorted_and_byte_stable() -> None:
    batch = list(reversed(_load("mixed.json")))

    first = canonical_candidate_work_bytes(batch)
    second = canonical_candidate_work_bytes(list(reversed(batch)))

    assert first == second
    assert first.endswith(b"\n")
    assert [item["suggested_change_id"] for item in json.loads(first)] == [
        "add-opportunity-3-c3d4e5f6",
        "update-type-src-worker-py-12-a1b2c3d4",
        "update-dispatch-retry-guidance-b2c3d4e5",
    ]


def test_duplicate_final_ids_fail_the_complete_batch() -> None:
    batch = _load("bug-scrub.json") * 2

    with pytest.raises(CandidateWorkValidationError, match="duplicate suggested_change_id"):
        validate_candidate_work_batch(batch)


def test_invalid_batch_preserves_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "candidate-work.json"
    before = b'{"old": true}\n'
    destination.write_bytes(before)
    malformed = _load("bug-scrub.json")
    del malformed[0]["rationale"]

    with pytest.raises(CandidateWorkValidationError):
        write_candidate_work(destination, malformed, generator="bug-scrub")

    assert destination.read_bytes() == before


def test_writer_atomically_replaces_with_sorted_canonical_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "candidate-work.json"
    second = dict(_load("bug-scrub.json")[0])
    second["suggested_change_id"] = "update-another-bug-d4e5f6a7"
    batch = [second, *_load("bug-scrub.json")]

    written = write_candidate_work(destination, batch, generator="bug-scrub")

    assert written == destination
    assert destination.read_bytes() == canonical_candidate_work_bytes(batch)
    assert not list(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_writer_rejects_an_incoming_batch_owned_by_another_generator(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "candidate-work.json"

    with pytest.raises(CandidateWorkCollisionError, match="improve-harness"):
        write_candidate_work(
            destination, _load("improve-harness.json"), generator="bug-scrub"
        )

    assert not destination.exists()


def test_successful_empty_discovery_clears_stale_same_generator_batch(tmp_path: Path) -> None:
    destination = tmp_path / "candidate-work.json"
    write_candidate_work(destination, _load("bug-scrub.json"), generator="bug-scrub")

    write_candidate_work(destination, [], generator="bug-scrub")

    assert destination.read_bytes() == b"[]\n"


def test_explicit_destination_collision_preserves_other_generator_batch(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "candidate-work.json"
    write_candidate_work(
        destination, _load("improve-harness.json"), generator="improve-harness"
    )
    before = destination.read_bytes()

    with pytest.raises(CandidateWorkCollisionError, match="improve-harness"):
        write_candidate_work(destination, _load("bug-scrub.json"), generator="bug-scrub")

    assert destination.read_bytes() == before


def test_multi_file_loader_preserves_file_and_item_order(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(_load("improve-harness.json")), encoding="utf-8")
    second.write_text(json.dumps(_load("bug-scrub.json")), encoding="utf-8")

    loaded = load_candidate_work_files([first, second])

    assert [item["provenance"]["generator"] for item in loaded] == [
        "improve-harness",
        "bug-scrub",
    ]


def test_multi_file_loader_rejects_duplicates_across_the_union(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload = json.dumps(_load("bug-scrub.json"))
    first.write_text(payload, encoding="utf-8")
    second.write_text(payload, encoding="utf-8")

    with pytest.raises(CandidateWorkValidationError, match="duplicate suggested_change_id"):
        load_candidate_work_files([first, second])


def test_collision_probe_uses_the_writer_supplied_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import candidate_work as runtime

    destination = tmp_path / "candidate-work.json"
    destination.write_text(
        json.dumps(_load("improve-harness.json")), encoding="utf-8"
    )
    before = destination.read_bytes()
    supplied_schema = json.loads(
        (REPO_ROOT / "openspec/schemas/candidate-work.schema.json").read_text(
            encoding="utf-8"
        )
    )

    def unavailable_schema(*_args: object, **_kwargs: object) -> Path:
        raise FileNotFoundError("canonical schema intentionally unavailable")

    monkeypatch.setattr(runtime, "find_schema_path", unavailable_schema)

    with pytest.raises(CandidateWorkCollisionError, match="improve-harness"):
        write_candidate_work(
            destination,
            _load("bug-scrub.json"),
            generator="bug-scrub",
            schema=supplied_schema,
        )

    assert destination.read_bytes() == before
