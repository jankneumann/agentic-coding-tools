"""Guard: plan-feature and implement-feature push a literal ref, not a shell variable.

Bash permission rules match the command text. `.claude/settings.json` pre-approves
`git push -u origin openspec/*` for cloud workers and sends any push containing `$`
to a prompt, so a templated `"$FEATURE_BRANCH"` push stalls an auto-mode worker.
"""
import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2]
PUSH_WITH_VARIABLE = re.compile(r"^\s*git push\b[^\n#]*\$", re.MULTILINE)


@pytest.mark.parametrize("skill", ["plan-feature", "implement-feature"])
def test_push_uses_literal_ref(skill):
    text = (SKILLS / skill / "SKILL.md").read_text()
    offenders = PUSH_WITH_VARIABLE.findall(text)
    assert not offenders, f"{skill} pushes a shell-expanded ref: {offenders}"
    assert "git push -u origin <feature-branch>" in text
