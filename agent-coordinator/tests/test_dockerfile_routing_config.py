"""Container packaging contract for the versioned routing policy."""

from pathlib import Path


def test_runtime_image_contains_routing_policy_beside_agents_config() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    copy_line = "COPY agent-coordinator/routing.yaml /app/routing.yaml"

    assert dockerfile.count(copy_line) == 1
    assert "COPY agent-coordinator/agents.yaml /app/agents.yaml" in dockerfile
