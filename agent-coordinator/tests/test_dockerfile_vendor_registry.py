"""Deployment packaging contract for registry health snapshots."""

from pathlib import Path


def test_runtime_image_contains_vendor_probe_and_explicit_agents_config() -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "Dockerfile"
    ).read_text()

    assert (
        "COPY skills/parallel-infrastructure/scripts/vendor_health.py "
        "/app/skills/parallel-infrastructure/scripts/vendor_health.py"
    ) in dockerfile
    assert "AGENTS_YAML=/app/agents.yaml" in dockerfile
    assert "SKILLS_ROOT=/app/skills" in dockerfile
