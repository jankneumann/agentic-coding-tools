# Installed skill path resolution

`skills/install.sh` installs the same payload under either
`.claude/skills/` or `.agents/skills/`. Runtime instructions therefore cannot
assume that the consumer has this source repository's top-level `skills/`,
`scripts/`, `agent-coordinator/`, Makefile, or Python virtual environment.

## Placeholder contract

`<skill-base-dir>` is the directory containing the `SKILL.md` currently being
executed. The host agent resolves it from the loaded skill artifact before
running a command.

```text
<skill-base-dir>/scripts/tool.py
<skill-base-dir>/references/topic.md
<skill-base-dir>/../shared/helper.py
<skill-base-dir>/../another-skill/scripts/tool.py
```

These forms work unchanged in all supported layouts:

```text
skills/<name>/                 # canonical source checkout
.claude/skills/<name>/         # Claude consumer install
.agents/skills/<name>/         # Codex/agents consumer install
```

## Language-specific resolution

- Skill instructions use the literal `<skill-base-dir>` placeholder.
- Python derives owned paths from `Path(__file__).resolve()`.
- Shell derives owned paths from `${BASH_SOURCE[0]}`.
- Installed hooks persist the concrete `.claude/skills/...` or
  `.agents/skills/...` path discovered at installation time.

Use the consumer's selected `python3` unless a skill documents a separate
dependency environment. An installed skill must not invoke `skills/.venv`;
that environment belongs only to contributors in this source checkout.

## Consumer-owned and source-only paths

A relative path such as `src/`, `docs/architecture-analysis/`, or
`scripts/deploy.py` may intentionally name a file in the consumer project.
Label it **consumer-project-relative** next to the command. Do not leave bare
`scripts/...` ambiguous.

Commands used only while contributing to this repository may retain canonical
source paths only when labelled **source-contribution-only**. They are not part
of the installed skill's baseline workflow and portability checks may classify
them separately.

## External integrations

Optional integrations outside the install payload require an explicit path or
public endpoint, for example `COORDINATOR_DIR`, `AGENTS_YAML`, or
`COORDINATION_API_URL`. Missing optional configuration must produce an
actionable diagnostic or disable that feature; it must not fabricate a path
back into the source repository.
