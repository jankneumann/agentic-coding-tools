"""documentation.inventory producer tests (task 2.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from _runtime import ChangeKind, ProducerStatus
from contract import validate_producer_result
from producer_documentation import DocBlock, DocumentationInventoryProducer

FULL_SHA = "a" * 40


def _mk_skill(repo: Path, name: str, description: str, invocable: bool = True) -> None:
    skill_dir = repo / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"user_invocable: {'true' if invocable else 'false'}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _mk_skill(tmp_path, "bravo", "Second skill does things")
    _mk_skill(tmp_path, "alpha", "First skill does other things", invocable=False)
    return tmp_path


def _producer() -> DocumentationInventoryProducer:
    return DocumentationInventoryProducer()


def _target(repo: Path) -> Path:
    return repo / "docs/architecture-analysis/skills-inventory.md"


def test_generate_creates_sorted_inventory(repo: Path):
    result = _producer().run("generate", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.FRESH
    text = _target(repo).read_text()
    # Rows sorted by folder name: alpha before bravo.
    assert text.index("`alpha`") < text.index("`bravo`")
    assert "First skill does other things" in text
    # invocable flags rendered.
    assert "| `alpha` | no |" in text
    assert "| `bravo` | yes |" in text
    # One ADDED artifact recorded.
    assert [a.change for a in result.artifacts] == [ChangeKind.ADDED]


def test_check_on_missing_file_reports_added_drift(repo: Path):
    result = _producer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.DEGRADED
    assert result.artifacts[0].change is ChangeKind.ADDED
    assert not _target(repo).exists()  # check never writes


def test_generate_then_check_is_fresh(repo: Path):
    _producer().run("generate", repo, FULL_SHA)
    result = _producer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.FRESH
    assert result.artifacts == ()


def test_repeat_generation_is_byte_identical(repo: Path):
    _producer().run("generate", repo, FULL_SHA)
    first = _target(repo).read_bytes()
    _producer().run("generate", repo, FULL_SHA)
    second = _target(repo).read_bytes()
    assert first == second


def test_check_detects_drift_after_input_change(repo: Path):
    _producer().run("generate", repo, FULL_SHA)
    before = _target(repo).read_bytes()
    _mk_skill(repo, "charlie", "A third skill appears")
    result = _producer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.DEGRADED
    assert result.artifacts[0].change is ChangeKind.MODIFIED
    assert result.fallback is not None  # custom check-mode fallback
    # check performed no write.
    assert _target(repo).read_bytes() == before


def test_prose_outside_markers_preserved_on_regeneration(repo: Path):
    _producer().run("generate", repo, FULL_SHA)
    target = _target(repo)
    text = target.read_text()
    # Inject hand-authored prose after the end marker.
    injected = text + "\n## Human notes\n\nDo not delete me.\n"
    target.write_text(injected, encoding="utf-8")
    _mk_skill(repo, "charlie", "A third skill appears")
    _producer().run("generate", repo, FULL_SHA)
    after = target.read_text()
    assert "Do not delete me." in after
    assert "`charlie`" in after


def test_unbalanced_markers_fail_without_writing(repo: Path):
    _producer().run("generate", repo, FULL_SHA)
    target = _target(repo)
    corrupt = target.read_text().replace("<!-- GENERATED: end skills-inventory -->", "")
    target.write_text(corrupt, encoding="utf-8")
    result = _producer().run("generate", repo, FULL_SHA)
    assert result.status is ProducerStatus.FAILED
    assert result.error is not None and result.error.error_class == "MarkerError"
    # The corrupt file was not overwritten.
    assert target.read_text() == corrupt


def test_custom_block_config_via_fixture(tmp_path: Path):
    # A managed target with surrounding prose exercises the marker path directly.
    _mk_skill(tmp_path, "solo", "Only skill")
    target_rel = "docs/custom-inventory.md"
    (tmp_path / "docs").mkdir()
    (tmp_path / target_rel).write_text(
        "# Custom\n\nintro prose\n\n"
        "<!-- GENERATED: begin inv -->\nstale\n<!-- GENERATED: end inv -->\n\ntail prose\n",
        encoding="utf-8",
    )
    producer = DocumentationInventoryProducer(
        blocks=[DocBlock(target_rel, "inv", "skills_inventory", "Custom inventory")]
    )
    result = producer.run("generate", tmp_path, FULL_SHA)
    assert result.status is ProducerStatus.FRESH
    out = (tmp_path / target_rel).read_text()
    assert "intro prose" in out and "tail prose" in out
    assert "`solo`" in out and "stale" not in out
