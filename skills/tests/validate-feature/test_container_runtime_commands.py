"""Guard the detected container runtime through deploy and teardown commands."""

from pathlib import Path


def test_compose_commands_use_detected_runtime() -> None:
    skill_path = Path(__file__).resolve().parents[2] / "validate-feature" / "SKILL.md"
    instructions = skill_path.read_text(encoding="utf-8")

    assert 'docker-compose -f "$COMPOSE_FILE"' not in instructions
    assert instructions.count('$RUNTIME compose -f "$COMPOSE_FILE"') == 5
