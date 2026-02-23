# Validation Matrix: coordinator-skill-integration

## Scope

This report captures implementation-time validation for transport-aware coordinator integration and canonical skill parity across provider runtimes.

## Executed Checks

### Canonical distribution parity

```bash
skills/install.sh --mode rsync --agents claude,codex,gemini --deps none --python-tools none
```

Result: pass (canonical `skills/` synced into `.claude/.codex/.gemini` mirrors).

Mirror consistency spot-check:

```bash
for skill in explore-feature plan-feature implement-feature iterate-on-plan iterate-on-implementation validate-feature cleanup-feature security-review setup-coordinator; do
  diff -u "skills/$skill/SKILL.md" ".claude/skills/$skill/SKILL.md"
  diff -u "skills/$skill/SKILL.md" ".codex/skills/$skill/SKILL.md"
  diff -u "skills/$skill/SKILL.md" ".gemini/skills/$skill/SKILL.md"
done
```

Result: pass.

### MCP matrix proxy checks (Claude/Codex/Gemini CLI mirrors)

Validated capability-gated hook instructions exist in all three runtime mirrors:

- `/implement-feature`: lock, queue, guardrails hooks
- `/plan-feature` + `/iterate-on-plan`: handoff hooks
- `/validate-feature` + `/iterate-on-implementation`: memory hooks

Command result: pass.

### HTTP matrix proxy checks (Claude/Codex/Gemini Web/Cloud mirrors)

Validated all HTTP-capable skills in all runtime mirrors reference bridge-based hook paths:

- `scripts/coordination_bridge.py` references present in integrated skill docs

Command result: pass.

### Bridge behavior tests (HTTP capability and fallback)

```bash
/Users/jankneumann/Coding/agentic-coding-tools/agent-coordinator/.venv/bin/pytest scripts/tests/test_coordination_bridge.py -q
```

Result: pass (`8 passed`).

Key assertions covered:

- HTTP detection with partial capability availability
- Capability-gated operation execution
- graceful `status="skipped"` on unavailability
- handoff endpoint absence fallback behavior

Strict OpenSpec validation:

```bash
openspec validate coordinator-skill-integration --strict
```

Result: pass.

## Runtime Availability Notes

This implementation environment does not execute live end-to-end interactive sessions inside all six external runtime contexts (Claude Codex CLI, Codex CLI, Gemini CLI, Claude Web, Codex Cloud/Web, Gemini Web/Cloud).

To close operational sign-off, run the explicit six-dimension runtime tests documented in `docs/skills-workflow.md` under:

- `Coordinator Integration Model`
- `Explicit Runtime Parity Tests (3 Providers x 2 Transports)`
