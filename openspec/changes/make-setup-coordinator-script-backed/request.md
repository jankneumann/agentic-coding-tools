# Change Request (verbatim operator input)

Convert `setup-coordinator` from a narrated-bash skill into a script-backed skill.

## Scope

1. **Extract the deterministic half** of `skills/setup-coordinator/SKILL.md` into a
   portable `scripts/setup_coordinator.py` with subcommands:
   `detect-harnesses`, `check`, `configure`, `report`.
2. **Add presence-only vendor harness detection** — CLI on PATH plus a home-directory
   config artifact. Explicitly model an `unknown` state for vendors whose auth
   location is not detectable (antigravity keeps credentials outside its dotfile
   dir; there is no `agy login`). Authentication and login remain the user's
   responsibility — detection reports presence, never validity.
3. **Fix the `settings.local.json` permission-allowlist defects** currently at
   `SKILL.md` lines 211-232 (Python source nested in a bash string inside a
   markdown fence):
   - relative path — behavior depends on cwd, but the skill is designed to run
     from consumer repos
   - whole-file reformat — `json.dumps(..., indent=2)` rewrites the entire settings
     file to append one array element
   - non-atomic write — any concurrent writer loses
   - deny-list false positive — the `grep` guard matches `mcp__coordination__*`
     anywhere in the file, so an entry in a `deny` list makes the skill conclude the
     permission is already allowed and silently skip the add
4. **Add tests** under `skills/tests/setup-coordinator/`. The skill currently has
   neither a `scripts/` directory nor a test suite, unlike ~30 other script-backed
   skills in this repo.
5. **Reduce `SKILL.md` to narration + invocation.** At 360 lines it is well past the
   length a model follows reliably. Knowledge content (transport model table,
   when-to-use-HTTP guidance, troubleshooting list) stays; improvised glue goes.

## Hard constraint

The script **must not import `agent-coordinator` `src` modules.** `SKILL.md` states
twice that the skill never assumes `agent-coordinator/` was bundled into a consumer
repository. The entrypoint lives in the skill's own `scripts/` and stays stdlib-only
(pyyaml at most, matching the precedent set by
`skills/parallel-infrastructure/scripts/vendor_health.py`). Profile resolution must be
implemented against the YAML directly, not via `src.config`.

## Context and prior art

- `skills/parallel-infrastructure/scripts/vendor_health.py` already does CLI-on-PATH
  detection and env-var credential resolution, and carries an explicit design
  constraint at lines 99-101: *"D6 still holds: this is env-var resolution, not an
  inference probe."* Presence-only detection is consistent with that stance; reuse
  this module rather than duplicating it.
- Observed home-directory auth artifacts (2026-08-19, macOS): `~/.claude.json` +
  `~/.claude/`, `~/.codex/auth.json`, `~/.grok/auth.json`, `~/.pi/agent/auth.json`.
  `~/.antigravity/` contains no auth/cred/token file at any depth up to 3 —
  this is the `unknown` case.
- `/vendor-status` (`skills/vendor-status/SKILL.md`) is the shape to copy: thin
  SKILL.md, real script elsewhere, tests alongside.
- `setup-coordinator` already claims in its Objectives that it will "read
  `agents.yaml` to determine which agents to configure" but contains no code that
  does so. Folding harness detection into this skill resolves that overlap rather
  than shipping a competing sibling skill.

## Out of scope

- Installing vendor CLIs, or automating any interactive login (`grok login`,
  `codex login` are browser OAuth device flows a skill cannot complete).
- Probing vendors with billed inference calls to verify credential validity.
- Changes to `agent-coordinator/` itself.
